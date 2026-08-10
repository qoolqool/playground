"""Gate 3 — Security & Policy Guardrails.

YOU OWN THE QUALITY GATE. This is a mandatory checkpoint you must call yourself
after Gate 2 passes and before claiming HARDEN / runtime-ready.

Gate 3 answers:
  "Is this testbed allowed to run as specified and implemented, under our
   security and policy constraints?"

Gate 1 certifies the specification.
Gate 2 certifies that artifacts match the spec and are statically coherent.
Gate 3 certifies that the stack is safe to run under policy.

The gate checks:
  1. Privilege & capabilities (privileged containers, risky cap_add)
  2. Dangerous mounts (Docker socket, sensitive host paths)
  3. Secrets hygiene (hardcoded secrets in env/config)
  4. Network / exposure (host network mode, excessive ports)
  5. Guardrail fidelity (spec guardrails vs compose reality)
  6. Declared exceptions (explicit allowlist for known decisions)

Hard rule:
  After Gate 2 passes → call validate_guardrails() →
  if status != "pass", apply the returned actions, then re-validate.
  Do NOT claim HARDEN / runtime-ready while Gate 3 is failing.

Design principle: The gate never crashes — it always returns a GateFeedback.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import yaml

from testbed.contracts.spec import TestbedSpec
from testbed.contracts.feedback import (
    GateFeedback,
    GateStatus,
    Location,
    Severity,
    Diagnostic,
    Action,
    ActionKind,
)
from testbed.gates.policy_allowlist import (
    PolicyAllowlist,
    default_allowlist,
    RISKY_CAPABILITIES,
    SAFE_CAPABILITIES,
    SENSITIVE_HOST_PATHS,
    DOCKER_SOCKET_PATTERNS,
    SECRET_ENV_NAME_PATTERNS,
    SECRET_VALUE_PATTERNS,
)

# ---------------------------------------------------------------------------
# Error code registry
# ---------------------------------------------------------------------------

ERROR_CODES = {
    # Privilege & capabilities
    "G3_PRIVILEGED_CONTAINER": "Service uses privileged: true (full container privilege escalation)",
    "G3_RISKY_CAPABILITY": "Service has risky capability in cap_add",
    # Dangerous mounts
    "G3_DOCKER_SOCKET_MOUNT": "Docker socket mounted into container",
    "G3_HOST_PATH_MOUNT": "Sensitive host path mounted into container",
    # Secrets hygiene
    "G3_SECRET_IN_ENV": "Hardcoded secret detected in environment variable",
    # Network / exposure
    "G3_HOST_NETWORK_MODE": "Service uses host network mode",
    "G3_EXCESSIVE_PORTS": "Service exposes more ports than allowed by policy",
    # Guardrail fidelity
    "G3_GUARDRAIL_VIOLATION": "Spec guardrail violated by compose configuration",
    # Informational
    "G3_HEALTHCHECK_DISABLED": "Healthcheck explicitly disabled on service",
    # npm supply chain
    "G3_NPM_SUPPLY_CHAIN": "Known vulnerable npm package detected in dependencies",
}

# Maximum actions to return
_MAX_ACTIONS = 7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_compose(compose_path: Path) -> tuple[Optional[dict], list[Diagnostic], list[Action]]:
    """Load and parse a Docker Compose file.

    Returns (compose_dict, diagnostics, actions).
    """
    diagnostics: list[Diagnostic] = []
    actions: list[Action] = []

    if not compose_path.exists():
        diagnostics.append(Diagnostic(
            code="G3_MISSING_COMPOSE",
            severity=Severity.critical,
            message=f"Compose file not found: {compose_path}",
            location=Location(field="compose_file", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description=f"Create the Docker Compose file at {compose_path}",
            target_field="compose_file",
            priority=0,
        ))
        return None, diagnostics, actions

    try:
        text = compose_path.read_text(encoding="utf-8", errors="replace")
        compose = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        diagnostics.append(Diagnostic(
            code="G3_COMPOSE_SYNTAX",
            severity=Severity.critical,
            message=f"Compose file has YAML syntax error: {exc}",
            location=Location(field="compose_file", source=str(compose_path)),
            detail=str(exc),
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description=f"Fix YAML syntax error in {compose_path}: {exc}",
            target_field="compose_file",
            priority=0,
        ))
        return None, diagnostics, actions

    if not isinstance(compose, dict):
        diagnostics.append(Diagnostic(
            code="G3_COMPOSE_STRUCTURE",
            severity=Severity.critical,
            message="Compose file root is not a mapping (expected a dict)",
            location=Location(field="compose_file", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description="Ensure the compose file is a valid Docker Compose YAML mapping",
            target_field="compose_file",
            priority=0,
        ))
        return None, diagnostics, actions

    return compose, diagnostics, actions


def _resolve_compose_path(workspace_root: Path) -> Optional[Path]:
    """Auto-detect the Docker Compose file under workspace_root."""
    candidates = [
        workspace_root / "deploy" / "compose" / "root.yml",
        workspace_root / "deploy" / "compose" / "root.yaml",
        workspace_root / "docker-compose.yml",
        workspace_root / "docker-compose.yaml",
        workspace_root / "compose.yml",
        workspace_root / "compose.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _get_compose_services(compose: dict) -> dict[str, dict]:
    """Get the services dict from a compose file, handling empty/missing."""
    return compose.get("services", {}) or {}


def _normalize_volume_source(source: str) -> str:
    """Normalize a volume source path for comparison.

    Strips variable prefixes like ${HOST_PROJECT_DIR}/, leading ./,
    and trailing slashes. Preserves leading / for absolute path matching.
    """
    result = source
    # Strip variable references
    result = re.sub(r'\$\{[^}]+\}/?', '', result)
    # Strip leading ./
    result = re.sub(r'^\./', '', result)
    # Strip trailing slashes (but preserve leading / for root detection)
    if len(result) > 1:
        result = result.rstrip("/")
    return result


def _is_docker_socket_mount(source: str) -> bool:
    """Check if a volume source is a Docker socket path.

    Checks both the original source and the normalized version.
    """
    # Check original source first (handles variable-prefixed paths)
    for pattern in DOCKER_SOCKET_PATTERNS:
        if source == pattern or source.startswith(pattern + "/"):
            return True
        # Also check if the pattern appears anywhere in the source
        if pattern in source:
            return True

    # Then check normalized version
    normalized = _normalize_volume_source(source)
    for pattern in DOCKER_SOCKET_PATTERNS:
        if normalized == pattern or normalized.startswith(pattern + "/"):
            return True
        # Check with leading / restored
        restored = "/" + normalized if not normalized.startswith("/") else normalized
        if restored == pattern or restored.startswith(pattern + "/"):
            return True

    return False


def _is_sensitive_host_path(source: str) -> bool:
    """Check if a volume source is a sensitive host path.

    Checks both the original source and the normalized version.
    """
    # Check original source first
    for path in SENSITIVE_HOST_PATHS:
        if source == path or source.startswith(path + "/"):
            return True
        # Also check if the sensitive path appears anywhere in the source
        if path in source and path != "/":
            return True

    # Then check normalized version
    normalized = _normalize_volume_source(source)
    for path in SENSITIVE_HOST_PATHS:
        if normalized == path or normalized.startswith(path + "/"):
            return True
        # Check with leading / restored
        restored = "/" + normalized if not normalized.startswith("/") else normalized
        if restored == path or restored.startswith(path + "/"):
            return True

    return False


def _is_secret_env_var(name: str, value: str) -> bool:
    """Check if an environment variable looks like a hardcoded secret.

    High-signal patterns only — avoids noisy false positives.

    Strategy:
    1. Check if the env var name suggests a secret (e.g. PASSWORD, TOKEN, API_KEY)
    2. If the name is a strong secret indicator, flag any non-reference value
    3. If the name is a weaker indicator, also check the value for secret patterns
    """
    name_lower = name.lower()
    value_lower = value.lower()

    # Skip empty values, variable references, and paths
    if not value or value.startswith("$") or value.startswith("/"):
        return False

    # Check if the env var name suggests a secret
    is_secret_name = any(pattern in name_lower for pattern in SECRET_ENV_NAME_PATTERNS)

    if not is_secret_name:
        return False

    # Strong secret indicators — if the name contains these, flag any non-reference value
    strong_secret_patterns = ["password", "passwd", "secret", "token", "api_key", "apikey", "credential"]
    is_strong_indicator = any(pattern in name_lower for pattern in strong_secret_patterns)

    if is_strong_indicator:
        # The name alone is sufficient — flag any non-reference value
        return True

    # Weaker indicators — also check the value for secret patterns
    has_secret_value = any(pattern in value_lower for pattern in SECRET_VALUE_PATTERNS)

    # Also flag values that look like API keys/tokens (long alphanumeric strings)
    looks_like_key = (
        len(value) >= 16
        and not value.startswith("$")
        and not value.startswith("/")
        and not value.startswith("{")
    )

    return has_secret_value or looks_like_key


def _count_published_ports(compose_svc: dict) -> int:
    """Count the number of published ports in a compose service."""
    ports = compose_svc.get("ports", [])
    if not isinstance(ports, list):
        return 0
    return len(ports)


# ---------------------------------------------------------------------------
# Check 1: Privilege & capabilities
# ---------------------------------------------------------------------------

def _check_privilege_and_caps(
    compose: dict,
    spec: TestbedSpec,
    allowlist: PolicyAllowlist,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check for privileged containers and risky capabilities."""
    compose_services = _get_compose_services(compose)

    for svc_name, svc_config in compose_services.items():
        if not isinstance(svc_config, dict):
            continue

        # --- Check privileged: true ---
        if svc_config.get("privileged") is True:
            if allowlist.is_privileged_allowed(svc_name):
                # Allowlisted — informational note
                diagnostics.append(Diagnostic(
                    code="G3_PRIVILEGED_CONTAINER",
                    severity=Severity.info,
                    message=f"Service '{svc_name}' uses privileged: true (allowlisted)",
                    location=Location(
                        field=f"compose_file.services.{svc_name}.privileged",
                        source=str(compose_path),
                    ),
                    detail="This service is in the policy allowlist for privileged mode",
                ))
            else:
                # Not allowlisted — error
                diagnostics.append(Diagnostic(
                    code="G3_PRIVILEGED_CONTAINER",
                    severity=Severity.error,
                    message=f"Service '{svc_name}' uses privileged: true. "
                            f"Full container privilege escalation is a security risk. "
                            f"Prefer specific capabilities over full privileged mode.",
                    location=Location(
                        field=f"compose_file.services.{svc_name}.privileged",
                        source=str(compose_path),
                    ),
                ))
                actions.append(Action(
                    kind=ActionKind.fix,
                    description=f"Replace 'privileged: true' on '{svc_name}' with specific "
                                f"cap_add entries, or add to the policy allowlist if truly required",
                    target_field=f"compose_file.services.{svc_name}.privileged",
                    suggested_value=False,
                    priority=1,
                ))

        # --- Check risky cap_add ---
        cap_add = svc_config.get("cap_add", [])
        if not isinstance(cap_add, list):
            continue

        for cap in cap_add:
            cap_upper = str(cap).upper()
            if cap_upper in RISKY_CAPABILITIES:
                if allowlist.is_capability_allowed(svc_name, cap_upper):
                    # Allowlisted — informational note
                    diagnostics.append(Diagnostic(
                        code="G3_RISKY_CAPABILITY",
                        severity=Severity.info,
                        message=f"Service '{svc_name}' has capability '{cap}' (allowlisted)",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.cap_add",
                            source=str(compose_path),
                        ),
                        detail=f"Capability '{cap}' is in the policy allowlist for '{svc_name}'",
                    ))
                else:
                    # Not allowlisted — error
                    diagnostics.append(Diagnostic(
                        code="G3_RISKY_CAPABILITY",
                        severity=Severity.error,
                        message=f"Service '{svc_name}' has risky capability '{cap}' in cap_add. "
                                f"This capability allows privilege escalation or system manipulation.",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.cap_add",
                            source=str(compose_path),
                        ),
                        detail=f"Risky capability: {cap}. "
                               f"Remove it or add to the policy allowlist if truly required.",
                    ))
                    actions.append(Action(
                        kind=ActionKind.fix,
                        description=f"Remove '{cap}' from '{svc_name}' cap_add, or add to "
                                    f"the policy allowlist with justification",
                        target_field=f"compose_file.services.{svc_name}.cap_add",
                        priority=1,
                    ))


# ---------------------------------------------------------------------------
# Check 2: Dangerous mounts
# ---------------------------------------------------------------------------

def _check_dangerous_mounts(
    compose: dict,
    allowlist: PolicyAllowlist,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check for Docker socket mounts and sensitive host path mounts."""
    compose_services = _get_compose_services(compose)

    for svc_name, svc_config in compose_services.items():
        if not isinstance(svc_config, dict):
            continue

        volumes = svc_config.get("volumes", [])
        if not isinstance(volumes, list):
            continue

        for vol in volumes:
            # Handle both string format "host:container" and dict format
            if isinstance(vol, str):
                parts = vol.split(":")
                if len(parts) >= 1:
                    source = parts[0]
                else:
                    continue
            elif isinstance(vol, dict):
                source = vol.get("source", "")
            else:
                continue

            if not isinstance(source, str) or not source:
                continue

            # Check for Docker socket
            if _is_docker_socket_mount(source):
                if allowlist.is_host_path_allowed(svc_name, source):
                    diagnostics.append(Diagnostic(
                        code="G3_DOCKER_SOCKET_MOUNT",
                        severity=Severity.info,
                        message=f"Service '{svc_name}' mounts Docker socket '{source}' (allowlisted)",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.volumes",
                            source=str(compose_path),
                        ),
                    ))
                else:
                    diagnostics.append(Diagnostic(
                        code="G3_DOCKER_SOCKET_MOUNT",
                        severity=Severity.critical,
                        message=f"Service '{svc_name}' mounts the Docker socket at '{source}'. "
                                f"This gives the container root-level access to the Docker daemon.",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.volumes",
                            source=str(compose_path),
                        ),
                        detail=f"Mount: {source} → {vol}",
                    ))
                    actions.append(Action(
                        kind=ActionKind.remove,
                        description=f"Remove Docker socket mount from '{svc_name}'. "
                                    f"Use Docker-outside-of-Docker (DooD) patterns instead, "
                                    f"or add to the policy allowlist with justification",
                        target_field=f"compose_file.services.{svc_name}.volumes",
                        priority=0,
                    ))
                continue

            # Check for sensitive host paths
            if _is_sensitive_host_path(source):
                if allowlist.is_host_path_allowed(svc_name, source):
                    diagnostics.append(Diagnostic(
                        code="G3_HOST_PATH_MOUNT",
                        severity=Severity.info,
                        message=f"Service '{svc_name}' mounts host path '{source}' (allowlisted)",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.volumes",
                            source=str(compose_path),
                        ),
                    ))
                else:
                    diagnostics.append(Diagnostic(
                        code="G3_HOST_PATH_MOUNT",
                        severity=Severity.error,
                        message=f"Service '{svc_name}' mounts sensitive host path '{source}'. "
                                f"This can expose host filesystem to the container.",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.volumes",
                            source=str(compose_path),
                        ),
                        detail=f"Mount: {source} → {vol}",
                    ))
                    actions.append(Action(
                        kind=ActionKind.remove,
                        description=f"Remove sensitive host path mount '{source}' from "
                                    f"'{svc_name}', or add to the policy allowlist with justification",
                        target_field=f"compose_file.services.{svc_name}.volumes",
                        priority=1,
                    ))


# ---------------------------------------------------------------------------
# Check 3: Secrets hygiene
# ---------------------------------------------------------------------------

def _check_secrets_hygiene(
    compose: dict,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check for hardcoded secrets in environment variables."""
    compose_services = _get_compose_services(compose)

    for svc_name, svc_config in compose_services.items():
        if not isinstance(svc_config, dict):
            continue

        # Check environment dict format
        env = svc_config.get("environment", {})
        if isinstance(env, dict):
            for env_name, env_value in env.items():
                if isinstance(env_value, str) and _is_secret_env_var(env_name, env_value):
                    diagnostics.append(Diagnostic(
                        code="G3_SECRET_IN_ENV",
                        severity=Severity.error,
                        message=f"Service '{svc_name}' has a hardcoded secret in environment "
                                f"variable '{env_name}'",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.environment.{env_name}",
                            source=str(compose_path),
                        ),
                        detail=f"Environment variable '{env_name}' contains a value that "
                               f"appears to be a hardcoded secret. Use Docker secrets, "
                               f"an .env file, or a secrets manager instead.",
                    ))
                    actions.append(Action(
                        kind=ActionKind.fix,
                        description=f"Replace hardcoded value in '{env_name}' on '{svc_name}' "
                                    f"with a variable reference (e.g. ${{SECRET_NAME}}) or "
                                    f"Docker secret",
                        target_field=f"compose_file.services.{svc_name}.environment.{env_name}",
                        suggested_value="${SECRET_REF}",
                        priority=1,
                    ))

        # Check environment list format (VAR=value)
        elif isinstance(env, list):
            for env_entry in env:
                if isinstance(env_entry, str) and "=" in env_entry:
                    name, _, value = env_entry.partition("=")
                    if _is_secret_env_var(name, value):
                        diagnostics.append(Diagnostic(
                            code="G3_SECRET_IN_ENV",
                            severity=Severity.error,
                            message=f"Service '{svc_name}' has a hardcoded secret in environment "
                                    f"variable '{name}'",
                            location=Location(
                                field=f"compose_file.services.{svc_name}.environment",
                                source=str(compose_path),
                            ),
                            detail=f"Environment variable '{name}' contains a value that "
                                   f"appears to be a hardcoded secret.",
                        ))
                        actions.append(Action(
                            kind=ActionKind.fix,
                            description=f"Replace hardcoded value in '{name}' on '{svc_name}' "
                                        f"with a variable reference",
                            target_field=f"compose_file.services.{svc_name}.environment",
                            priority=1,
                        ))


# ---------------------------------------------------------------------------
# Check 4: Network / exposure
# ---------------------------------------------------------------------------

def _check_network_exposure(
    compose: dict,
    spec: TestbedSpec,
    allowlist: PolicyAllowlist,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check for host network mode and excessive port exposure."""
    compose_services = _get_compose_services(compose)

    for svc_name, svc_config in compose_services.items():
        if not isinstance(svc_config, dict):
            continue

        # --- Check network_mode: host ---
        network_mode = svc_config.get("network_mode")
        if network_mode == "host":
            if allowlist.is_host_network_allowed(svc_name):
                diagnostics.append(Diagnostic(
                    code="G3_HOST_NETWORK_MODE",
                    severity=Severity.info,
                    message=f"Service '{svc_name}' uses network_mode: host (allowlisted)",
                    location=Location(
                        field=f"compose_file.services.{svc_name}.network_mode",
                        source=str(compose_path),
                    ),
                ))
            elif spec.guardrails.no_host_network:
                diagnostics.append(Diagnostic(
                    code="G3_HOST_NETWORK_MODE",
                    severity=Severity.error,
                    message=f"Service '{svc_name}' uses network_mode: host, but the spec's "
                            f"guardrails set no_host_network=true. Host network mode bypasses "
                            f"Docker network isolation.",
                    location=Location(
                        field=f"compose_file.services.{svc_name}.network_mode",
                        source=str(compose_path),
                    ),
                ))
                actions.append(Action(
                    kind=ActionKind.fix,
                    description=f"Remove network_mode: host from '{svc_name}' and use bridge "
                                f"networks instead, or add to the policy allowlist",
                    target_field=f"compose_file.services.{svc_name}.network_mode",
                    suggested_value="bridge",
                    priority=1,
                ))
            else:
                # no_host_network is false — warning only
                diagnostics.append(Diagnostic(
                    code="G3_HOST_NETWORK_MODE",
                    severity=Severity.warning,
                    message=f"Service '{svc_name}' uses network_mode: host. "
                            f"Host network mode bypasses Docker network isolation.",
                    location=Location(
                        field=f"compose_file.services.{svc_name}.network_mode",
                        source=str(compose_path),
                    ),
                ))

        # --- Check excessive ports ---
        max_ports = spec.guardrails.max_exposed_ports
        port_count = _count_published_ports(svc_config)
        if port_count > max_ports:
            diagnostics.append(Diagnostic(
                code="G3_EXCESSIVE_PORTS",
                severity=Severity.warning,
                message=f"Service '{svc_name}' exposes {port_count} ports, "
                        f"exceeding the spec's max_exposed_ports limit of {max_ports}",
                location=Location(
                    field=f"compose_file.services.{svc_name}.ports",
                    source=str(compose_path),
                ),
                detail=f"Published: {port_count}, Limit: {max_ports}",
            ))
            actions.append(Action(
                kind=ActionKind.fix,
                description=f"Reduce exposed ports on '{svc_name}' to {max_ports} or fewer, "
                            f"or increase max_exposed_ports in the spec",
                target_field=f"compose_file.services.{svc_name}.ports",
                priority=3,
            ))


# ---------------------------------------------------------------------------
# Check 5: Guardrail fidelity
# ---------------------------------------------------------------------------

def _check_guardrail_fidelity(
    compose: dict,
    spec: TestbedSpec,
    allowlist: PolicyAllowlist,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check that spec guardrails are respected by the compose configuration."""
    compose_services = _get_compose_services(compose)

    # --- no_privileged guardrail ---
    if spec.guardrails.no_privileged:
        for svc_name, svc_config in compose_services.items():
            if not isinstance(svc_config, dict):
                continue
            if svc_config.get("privileged") is True:
                if not allowlist.is_privileged_allowed(svc_name):
                    diagnostics.append(Diagnostic(
                        code="G3_GUARDRAIL_VIOLATION",
                        severity=Severity.error,
                        message=f"Guardrail violation: spec sets no_privileged=true, but "
                                f"service '{svc_name}' has privileged: true",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.privileged",
                            source=str(compose_path),
                        ),
                        detail="The approved spec explicitly disallows privileged containers. "
                               "Either remove privileged mode or update the spec's guardrails.",
                    ))
                    actions.append(Action(
                        kind=ActionKind.fix,
                        description=f"Remove privileged: true from '{svc_name}' or update "
                                    f"spec.guardrails.no_privileged to false",
                        target_field=f"compose_file.services.{svc_name}.privileged",
                        suggested_value=False,
                        priority=0,
                    ))

    # --- no_host_network guardrail ---
    if spec.guardrails.no_host_network:
        for svc_name, svc_config in compose_services.items():
            if not isinstance(svc_config, dict):
                continue
            if svc_config.get("network_mode") == "host":
                if not allowlist.is_host_network_allowed(svc_name):
                    diagnostics.append(Diagnostic(
                        code="G3_GUARDRAIL_VIOLATION",
                        severity=Severity.error,
                        message=f"Guardrail violation: spec sets no_host_network=true, but "
                                f"service '{svc_name}' uses network_mode: host",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.network_mode",
                            source=str(compose_path),
                        ),
                        detail="The approved spec explicitly disallows host network mode. "
                               "Either remove host network mode or update the spec's guardrails.",
                    ))
                    actions.append(Action(
                        kind=ActionKind.fix,
                        description=f"Remove network_mode: host from '{svc_name}' or update "
                                    f"spec.guardrails.no_host_network to false",
                        target_field=f"compose_file.services.{svc_name}.network_mode",
                        suggested_value="bridge",
                        priority=0,
                    ))

    # --- require_healthcheck guardrail ---
    if spec.guardrails.require_healthcheck:
        for svc_name, svc_config in compose_services.items():
            if not isinstance(svc_config, dict):
                continue
            hc = svc_config.get("healthcheck")
            # Check if healthcheck is explicitly disabled
            if isinstance(hc, dict) and hc.get("disable") is True:
                if allowlist.is_healthcheck_disabled_allowed(svc_name):
                    diagnostics.append(Diagnostic(
                        code="G3_HEALTHCHECK_DISABLED",
                        severity=Severity.info,
                        message=f"Service '{svc_name}' has healthcheck disabled (allowlisted — "
                                f"distroless image or intentional)",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.healthcheck",
                            source=str(compose_path),
                        ),
                    ))
                else:
                    diagnostics.append(Diagnostic(
                        code="G3_GUARDRAIL_VIOLATION",
                        severity=Severity.error,
                        message=f"Guardrail violation: spec sets require_healthcheck=true, but "
                                f"service '{svc_name}' has healthcheck explicitly disabled",
                        location=Location(
                            field=f"compose_file.services.{svc_name}.healthcheck",
                            source=str(compose_path),
                        ),
                        detail="The approved spec requires healthchecks on all services. "
                               "Either add a healthcheck or update the spec's guardrails.",
                    ))
                    actions.append(Action(
                        kind=ActionKind.fix,
                        description=f"Add a healthcheck to '{svc_name}' or add it to the "
                                    f"policy allowlist for healthcheck disable",
                        target_field=f"compose_file.services.{svc_name}.healthcheck",
                        priority=1,
                    ))
            elif hc is None or hc == {}:
                # No healthcheck at all
                diagnostics.append(Diagnostic(
                    code="G3_GUARDRAIL_VIOLATION",
                    severity=Severity.error,
                    message=f"Guardrail violation: spec sets require_healthcheck=true, but "
                            f"service '{svc_name}' has no healthcheck configured",
                    location=Location(
                        field=f"compose_file.services.{svc_name}.healthcheck",
                        source=str(compose_path),
                    ),
                    detail="The approved spec requires healthchecks on all services.",
                ))
                actions.append(Action(
                    kind=ActionKind.add,
                    description=f"Add a healthcheck to '{svc_name}'",
                    target_field=f"compose_file.services.{svc_name}.healthcheck",
                    suggested_value={
                        "test": ["CMD", "curl", "-f", "http://localhost/health"],
                        "interval": "15s",
                        "timeout": "5s",
                        "retries": 3,
                    },
                    priority=1,
                ))

    # --- require_mem_limit guardrail ---
    if spec.guardrails.require_mem_limit:
        for svc_name, svc_config in compose_services.items():
            if not isinstance(svc_config, dict):
                continue
            if not svc_config.get("mem_limit"):
                diagnostics.append(Diagnostic(
                    code="G3_GUARDRAIL_VIOLATION",
                    severity=Severity.error,
                    message=f"Guardrail violation: spec sets require_mem_limit=true, but "
                            f"service '{svc_name}' has no memory limit configured",
                    location=Location(
                        field=f"compose_file.services.{svc_name}.mem_limit",
                        source=str(compose_path),
                    ),
                    detail="The approved spec requires memory limits on all services.",
                ))
                actions.append(Action(
                    kind=ActionKind.add,
                    description=f"Add a memory limit to '{svc_name}'",
                    target_field=f"compose_file.services.{svc_name}.mem_limit",
                    suggested_value="256M",
                    priority=1,
                ))

    # --- required_labels guardrail ---
    required_labels = spec.guardrails.required_labels
    if required_labels:
        for svc_name, svc_config in compose_services.items():
            if not isinstance(svc_config, dict):
                continue
            labels = svc_config.get("labels", {})
            if not isinstance(labels, dict):
                continue
            missing_labels = [lbl for lbl in required_labels if lbl not in labels]
            if missing_labels:
                diagnostics.append(Diagnostic(
                    code="G3_GUARDRAIL_VIOLATION",
                    severity=Severity.warning,
                    message=f"Guardrail violation: service '{svc_name}' is missing required "
                            f"labels: {', '.join(missing_labels)}",
                    location=Location(
                        field=f"compose_file.services.{svc_name}.labels",
                        source=str(compose_path),
                    ),
                    detail=f"Required labels: {', '.join(required_labels)}. "
                           f"Missing: {', '.join(missing_labels)}.",
                ))
                actions.append(Action(
                    kind=ActionKind.add,
                    description=f"Add missing labels to '{svc_name}': {', '.join(missing_labels)}",
                    target_field=f"compose_file.services.{svc_name}.labels",
                    priority=2,
                ))

    # --- blocked_images guardrail ---
    blocked_images = spec.guardrails.blocked_images
    if blocked_images:
        for svc_name, svc_config in compose_services.items():
            if not isinstance(svc_config, dict):
                continue
            image = svc_config.get("image", "")
            if isinstance(image, str):
                for blocked in blocked_images:
                    if image.startswith(blocked):
                        diagnostics.append(Diagnostic(
                            code="G3_GUARDRAIL_VIOLATION",
                            severity=Severity.error,
                            message=f"Guardrail violation: service '{svc_name}' uses image "
                                    f"'{image}' which matches blocked prefix '{blocked}'",
                            location=Location(
                                field=f"compose_file.services.{svc_name}.image",
                                source=str(compose_path),
                            ),
                            detail=f"Image '{image}' is blocked by spec guardrails.",
                        ))
                        actions.append(Action(
                            kind=ActionKind.fix,
                            description=f"Replace image for '{svc_name}' with an allowed image",
                            target_field=f"compose_file.services.{svc_name}.image",
                            priority=1,
                        ))


# ---------------------------------------------------------------------------
# Check 6: npm supply chain security
# ---------------------------------------------------------------------------

# Known vulnerable npm packages (supply chain attacks, malware, etc.)
# Format: {package_name: {reason, advisory_url, severity}}
# Source: https://www.wiz.io/blog/keyv-and-cacheable-npm-supply-chain-attack
NPM_VULNERABLE_PACKAGES: dict[str, dict[str, str]] = {
    # Keyv supply chain attack (2023-11) — malicious versions published
    # that exfiltrated environment variables and secrets
    "keyv": {
        "reason": "Compromised via npm account takeover (2023-11). Malicious versions exfiltrated env vars and secrets. See https://www.wiz.io/blog/keyv-and-cacheable-npm-supply-chain-attack",
        "advisory_url": "https://www.wiz.io/blog/keyv-and-cacheable-npm-supply-chain-attack",
        "severity": "critical",
    },
    "cacheable-request": {
        "reason": "Compromised via npm account takeover (2023-11). Malicious versions exfiltrated env vars and secrets. See https://www.wiz.io/blog/keyv-and-cacheable-npm-supply-chain-attack",
        "advisory_url": "https://www.wiz.io/blog/keyv-and-cacheable-npm-supply-chain-attack",
        "severity": "critical",
    },
    "cacheable-lookup": {
        "reason": "Compromised via npm account takeover (2023-11). Malicious versions exfiltrated env vars and secrets. See https://www.wiz.io/blog/keyv-and-cacheable-npm-supply-chain-attack",
        "advisory_url": "https://www.wiz.io/blog/keyv-and-cacheable-npm-supply-chain-attack",
        "severity": "critical",
    },
    # Add other known npm supply chain vulnerabilities here as they are discovered
}


def _find_package_json_files(workspace_root: Path) -> list[Path]:
    """Find all package.json files under workspace_root, excluding node_modules."""
    results: list[Path] = []
    for root, dirs, files in os.walk(str(workspace_root)):
        # Skip node_modules directories
        if "node_modules" in root.split(os.sep):
            continue
        if "package.json" in files:
            results.append(Path(root) / "package.json")
    return results


def _parse_package_json(path: Path) -> Optional[dict]:
    """Parse a package.json file and return its contents as a dict."""
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return None


def _get_all_dependencies(pkg: dict) -> dict[str, str]:
    """Collect all dependencies from a package.json into a single dict.

    Includes: dependencies, devDependencies, peerDependencies, optionalDependencies.
    Returns {package_name: version_spec}.
    """
    deps: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section_deps = pkg.get(section, {})
        if isinstance(section_deps, dict):
            deps.update(section_deps)
    return deps


def _check_npm_supply_chain(
    workspace_root: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check for known vulnerable npm packages in package.json files.

    Scans all package.json files under workspace_root (excluding node_modules)
    and flags any dependencies that match known vulnerable packages.

    Reference: https://www.wiz.io/blog/keyv-and-cacheable-npm-supply-chain-attack
    """
    package_json_files = _find_package_json_files(workspace_root)

    if not package_json_files:
        return  # No npm packages to check

    for pkg_path in package_json_files:
        pkg = _parse_package_json(pkg_path)
        if pkg is None:
            diagnostics.append(Diagnostic(
                code="G3_NPM_SUPPLY_CHAIN",
                severity=Severity.warning,
                message=f"Could not parse package.json at {pkg_path}",
                location=Location(field="npm_package", source=str(pkg_path)),
            ))
            continue

        all_deps = _get_all_dependencies(pkg)
        if not all_deps:
            continue

        for dep_name, dep_version in all_deps.items():
            if dep_name.lower() in NPM_VULNERABLE_PACKAGES:
                vuln = NPM_VULNERABLE_PACKAGES[dep_name.lower()]
                severity = Severity.critical if vuln["severity"] == "critical" else Severity.error

                diagnostics.append(Diagnostic(
                    code="G3_NPM_SUPPLY_CHAIN",
                    severity=severity,
                    message=f"Known vulnerable npm package '{dep_name}' (version: {dep_version}) "
                            f"found in {pkg_path.relative_to(workspace_root) if pkg_path.is_relative_to(workspace_root) else pkg_path}. "
                            f"{vuln['reason']}",
                    location=Location(
                        field=f"npm_package.{dep_name}",
                        source=str(pkg_path),
                    ),
                    detail=f"Package: {dep_name}@{dep_version}\n"
                            f"Advisory: {vuln['advisory_url']}\n"
                            f"Severity: {vuln['severity']}",
                ))
                actions.append(Action(
                    kind=ActionKind.fix,
                    description=f"Remove or replace vulnerable npm package '{dep_name}' from "
                                f"{pkg_path.relative_to(workspace_root) if pkg_path.is_relative_to(workspace_root) else pkg_path}. "
                                f"{vuln['reason']} Advisory: {vuln['advisory_url']}",
                    target_field=f"npm_package.{dep_name}",
                    priority=0,
                ))


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------

def _sort_and_cap_actions(actions: list[Action]) -> list[Action]:
    """Sort actions by priority (ascending) and cap at _MAX_ACTIONS."""
    actions.sort(key=lambda a: a.priority)
    return actions[:_MAX_ACTIONS]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def validate_guardrails(
    spec: TestbedSpec,
    workspace_root: Path = Path("/workspace"),
    compose_path: Optional[Path] = None,
    allowlist: Optional[PolicyAllowlist] = None,
    attempt_number: int = 1,
    previous_summary: Optional[str] = None,
) -> GateFeedback:
    """Validate security and policy guardrails against an approved TestbedSpec.

    This is the primary entry point for Gate 3. It checks that the
    implementation under workspace_root is safe to run under policy.

    Hard rule: After Gate 2 passes, call this function. If status != "pass",
    apply the returned actions, then re-validate. Do NOT claim HARDEN /
    runtime-ready while Gate 3 is failing.

    Args:
        spec: The approved, validated TestbedSpec.
        workspace_root: Root directory of the implementation (default: /workspace).
        compose_path: Path to the Docker Compose file. If None, auto-detect.
        allowlist: Policy allowlist for known exceptions. If None, uses default.
        attempt_number: Which attempt this is (for tracking iteration).
        previous_summary: One-line summary of the previous feedback attempt.

    Returns:
        GateFeedback with diagnostics and actions.
    """
    start_time = time.time()
    feedback_kwargs = {
        "gate_id": "gate3.guardrails",
        "gate_version": "0.1.0",
    }

    diagnostics: list[Diagnostic] = []
    actions: list[Action] = []

    # Use default allowlist if none provided
    if allowlist is None:
        allowlist = default_allowlist()

    # Guard: spec must be a TestbedSpec instance
    if not isinstance(spec, TestbedSpec):
        return GateFeedback(
            gate_id="gate3.guardrails",
            gate_version="0.1.0",
            status=GateStatus.error,
            diagnostics=[
                Diagnostic(
                    code="GATE_CRASH",
                    severity=Severity.critical,
                    message=f"Expected a TestbedSpec instance, got {type(spec).__name__}",
                ),
            ],
            duration_ms=int((time.time() - start_time) * 1000),
            attempt_number=attempt_number,
        )

    # --- Resolve compose path ---
    if compose_path is None:
        compose_path = _resolve_compose_path(workspace_root)

    if compose_path is None:
        # No compose file found — critical failure
        duration_ms = int((time.time() - start_time) * 1000)
        metadata = {"attempt_number": attempt_number}
        if previous_summary:
            metadata["previous_summary"] = previous_summary

        return GateFeedback(
            status=GateStatus.fail,
            diagnostics=[
                Diagnostic(
                    code="G3_MISSING_COMPOSE",
                    severity=Severity.critical,
                    message="No Docker Compose file found under workspace. "
                            "Expected at deploy/compose/root.yml, docker-compose.yml, or compose.yml",
                    location=Location(field="compose_file", source=str(workspace_root)),
                ),
            ],
            actions=[
                Action(
                    kind=ActionKind.add,
                    description="Create a Docker Compose file for the testbed services",
                    target_field="compose_file",
                    priority=0,
                ),
            ],
            spec_snapshot=spec.model_dump(mode="json"),
            duration_ms=duration_ms,
            attempt_number=attempt_number,
            metadata=metadata,
            **feedback_kwargs,
        )

    # --- Phase 1: Load and parse compose ---
    compose, parse_diags, parse_actions = _load_compose(compose_path)
    diagnostics.extend(parse_diags)
    actions.extend(parse_actions)

    if compose is None:
        # Compose file couldn't be parsed — critical failure
        duration_ms = int((time.time() - start_time) * 1000)
        metadata = {"attempt_number": attempt_number}
        if previous_summary:
            metadata["previous_summary"] = previous_summary

        return GateFeedback(
            status=GateStatus.fail,
            diagnostics=diagnostics,
            actions=_sort_and_cap_actions(actions),
            spec_snapshot=spec.model_dump(mode="json"),
            duration_ms=duration_ms,
            attempt_number=attempt_number,
            metadata=metadata,
            **feedback_kwargs,
        )

    # --- Phase 2: Run all checks ---
    _check_privilege_and_caps(compose, spec, allowlist, compose_path, diagnostics, actions)
    _check_dangerous_mounts(compose, allowlist, compose_path, diagnostics, actions)
    _check_secrets_hygiene(compose, compose_path, diagnostics, actions)
    _check_network_exposure(compose, spec, allowlist, compose_path, diagnostics, actions)
    _check_guardrail_fidelity(compose, spec, allowlist, compose_path, diagnostics, actions)
    _check_npm_supply_chain(workspace_root, diagnostics, actions)

    # --- Phase 3: Build feedback ---
    actions = _sort_and_cap_actions(actions)

    duration_ms = int((time.time() - start_time) * 1000)
    metadata = {"attempt_number": attempt_number}
    if previous_summary:
        metadata["previous_summary"] = previous_summary

    has_blockers = any(
        d.severity in (Severity.critical, Severity.error) for d in diagnostics
    )

    feedback = GateFeedback(
        status=GateStatus.fail if has_blockers else GateStatus.pass_,
        diagnostics=diagnostics,
        actions=actions,
        spec_snapshot=spec.model_dump(mode="json"),
        duration_ms=duration_ms,
        attempt_number=attempt_number,
        metadata=metadata,
        **feedback_kwargs,
    )

    return feedback


# ---------------------------------------------------------------------------
# Convenience: load spec from file
# ---------------------------------------------------------------------------

def validate_guardrails_from_file(
    spec_path: Path,
    workspace_root: Path = Path("/workspace"),
    compose_path: Optional[Path] = None,
    allowlist: Optional[PolicyAllowlist] = None,
    attempt_number: int = 1,
    previous_summary: Optional[str] = None,
) -> GateFeedback:
    """Load a TestbedSpec from a JSON file and validate guardrails.

    This is the CLI-friendly entry point.

    Args:
        spec_path: Path to the approved TestbedSpec JSON file.
        workspace_root: Root directory of the implementation.
        compose_path: Path to the Docker Compose file (auto-detect if None).
        allowlist: Policy allowlist for known exceptions. If None, uses default.
        attempt_number: Which attempt this is.
        previous_summary: One-line summary of the previous feedback attempt.

    Returns:
        GateFeedback with diagnostics and actions.
    """
    start_time = time.time()

    if not spec_path.exists():
        return GateFeedback(
            gate_id="gate3.guardrails",
            gate_version="0.1.0",
            status=GateStatus.error,
            diagnostics=[
                Diagnostic(
                    code="GATE_CRASH",
                    severity=Severity.critical,
                    message=f"Spec file not found: {spec_path}",
                    location=Location(field="spec_file", source=str(spec_path)),
                ),
            ],
            duration_ms=int((time.time() - start_time) * 1000),
            attempt_number=attempt_number,
        )

    try:
        spec_dict = json.loads(spec_path.read_text())
        spec = TestbedSpec(**spec_dict)
    except json.JSONDecodeError as exc:
        return GateFeedback(
            gate_id="gate3.guardrails",
            gate_version="0.1.0",
            status=GateStatus.error,
            diagnostics=[
                Diagnostic(
                    code="GATE_CRASH",
                    severity=Severity.critical,
                    message=f"Spec file is not valid JSON: {exc}",
                    location=Location(field="spec_file", source=str(spec_path)),
                    detail=str(exc),
                ),
            ],
            duration_ms=int((time.time() - start_time) * 1000),
            attempt_number=attempt_number,
        )
    except Exception as exc:
        return GateFeedback(
            gate_id="gate3.guardrails",
            gate_version="0.1.0",
            status=GateStatus.error,
            diagnostics=[
                Diagnostic(
                    code="GATE_CRASH",
                    severity=Severity.critical,
                    message=f"Spec file could not be parsed: {exc}",
                    location=Location(field="spec_file", source=str(spec_path)),
                    detail=str(exc),
                ),
            ],
            duration_ms=int((time.time() - start_time) * 1000),
            attempt_number=attempt_number,
        )

    return validate_guardrails(
        spec=spec,
        workspace_root=workspace_root,
        compose_path=compose_path,
        allowlist=allowlist,
        attempt_number=attempt_number,
        previous_summary=previous_summary,
    )
