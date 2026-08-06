"""Gate 2 — Code / Artifact Validator.

YOU OWN THE QUALITY GATE. This is a mandatory checkpoint you must call yourself
after implementing code changes under /workspace.

Gate 2 validates that the implementation artifacts (compose files, Dockerfiles,
configs, tests, scripts) under a workspace root are consistent with an approved
TestbedSpec and are statically coherent.

The gate answers:
  "Does what was actually built under /workspace match the approved spec
   and is it free of obvious static problems?"

Without Gate 2 the agent can drift from the approved spec, omit healthchecks
or memory limits, create missing files, or introduce undeclared services.
Gate 2 closes that gap with the same structured feedback style the agent
already understands from Gate 1.

Hard rule:
  After every code change under /workspace → call validate_code() →
  if status != "pass", apply the returned actions, then re-validate.
  Only proceed to runtime testing when status == "pass".

Design principle: The gate never crashes — it always returns a GateFeedback.
"""

from __future__ import annotations

import json
import os
import re
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

# ---------------------------------------------------------------------------
# Error code registry
# ---------------------------------------------------------------------------

ERROR_CODES = {
    # Spec ↔ Artifact consistency
    "G2_MISSING_SERVICE": "Service declared in spec not found in compose file",
    "G2_UNDECLARED_SERVICE": "Service in compose file not declared in approved spec",
    "G2_IMAGE_MISMATCH": "Service image does not match spec",
    "G2_BUILD_MISMATCH": "Service build context does not match spec",
    "G2_PORT_MISMATCH": "Port mapping does not match spec",
    "G2_MEMLIMIT_MISMATCH": "Memory limit missing or does not match spec",
    "G2_HEALTHCHECK_MISMATCH": "Healthcheck missing or does not match spec",
    "G2_NETWORK_MISMATCH": "Network attachment does not match spec",
    "G2_DEPENDS_MISMATCH": "depends_on does not match spec",
    # Required files
    "G2_MISSING_FILE": "Required file not found at expected path",
    "G2_MISSING_DOCKERFILE": "Dockerfile not found for build-context service",
    # Compose / config syntax
    "G2_COMPOSE_SYNTAX": "Compose file has YAML syntax error",
    "G2_COMPOSE_STRUCTURE": "Compose file missing required structural section",
    # Network consistency
    "G2_NETWORK_MISSING": "Network declared in spec not found in compose",
    "G2_NETWORK_UNDECLARED": "Network in compose not declared in spec",
    # Test suite presence
    "G2_MISSING_TEST_SUITE": "Test suite path declared in spec not found on disk",
    # Static hygiene
    "G2_CONFIG_SYNTAX": "Config file has syntax or parse error",
    "G2_ENVOY_CONFIG_SYNTAX": "Envoy config has YAML parse error",
}

# Maximum actions to return
_MAX_ACTIONS = 7

# Config files to check for basic syntax
_CONFIG_FILES_TO_CHECK = [
    "envoy.yaml",
    "Caddyfile",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_port_str(host: int, container: int, protocol: str = "tcp") -> str:
    """Normalize a port mapping to a comparable string."""
    return f"{host}:{container}/{protocol}"


def _compose_port_to_normalized(port_val: Any) -> Optional[str]:
    """Convert a Docker Compose port string like '443:443/udp' to normalized form."""
    if not isinstance(port_val, str):
        return None
    # Match patterns: "host:container/protocol", "host:container", "container/protocol"
    m = re.match(r"^(\d+):(\d+)(?:/(tcp|udp))?$", port_val)
    if m:
        host = int(m.group(1))
        container = int(m.group(2))
        protocol = m.group(3) or "tcp"
        return _normalize_port_str(host, container, protocol)
    # Short form: just "container/protocol" or "container"
    m = re.match(r"^(\d+)(?:/(tcp|udp))?$", port_val)
    if m:
        container = int(m.group(1))
        protocol = m.group(2) or "tcp"
        return _normalize_port_str(container, container, protocol)
    return None


def _normalize_healthcheck(hc: Any) -> Optional[tuple]:
    """Normalize a healthcheck config to a comparable tuple.

    Handles both Docker Compose format and TestbedSpec format.
    Returns None if no healthcheck, or a tuple of (test_tuple, interval, timeout, retries).
    """
    if not hc:
        return None
    if not isinstance(hc, dict):
        return None

    test = hc.get("test")
    if not test:
        return None

    # Normalize test to a tuple of strings
    if isinstance(test, str):
        # CMD-SHELL format: "curl -f http://localhost/health || exit 1"
        test_tuple = ("CMD-SHELL", test)
    elif isinstance(test, list):
        # CMD format: ["CMD", "curl", "-f", "http://localhost/health"]
        test_tuple = tuple(str(t) for t in test)
    else:
        return None

    interval = hc.get("interval", "30s")
    timeout = hc.get("timeout", "5s")
    retries = hc.get("retries", 3)

    return (test_tuple, str(interval), str(timeout), int(retries))


def _healthchecks_match(spec_hc: Any, compose_hc: Any) -> bool:
    """Compare two healthcheck configs for functional equivalence.

    This is intentionally lenient — we check that both exist and have
    the same test command structure, not byte-for-byte equality.
    """
    spec_norm = _normalize_healthcheck(spec_hc)
    compose_norm = _normalize_healthcheck(compose_hc)

    if spec_norm is None and compose_norm is None:
        return True
    if spec_norm is None or compose_norm is None:
        return False

    # Compare test commands (the most important part)
    spec_test = spec_norm[0]
    compose_test = compose_norm[0]

    # Normalize both test commands for comparison
    def _normalize_test_cmd(cmd: tuple) -> str:
        """Normalize a test command for comparison by stripping whitespace."""
        return " ".join(str(p).strip() for p in cmd).lower()

    spec_test_str = _normalize_test_cmd(spec_test)
    compose_test_str = _normalize_test_cmd(compose_test)

    # Check if they're functionally similar
    # Allow minor differences in quoting, whitespace, etc.
    if spec_test_str == compose_test_str:
        return True

    # More lenient: check if both use the same healthcheck mechanism
    # (e.g., both use curl, both use pg_isready, etc.)
    spec_keywords = set(spec_test_str.split())
    compose_keywords = set(compose_test_str.split())
    # If they share at least 2 significant keywords, consider them matching
    significant = {w for w in spec_keywords & compose_keywords if len(w) > 2}
    if len(significant) >= 2:
        return True

    return False


def _mem_limits_match(spec_limit: Optional[str], compose_limit: Any) -> bool:
    """Compare memory limits, normalizing units."""
    if spec_limit is None and compose_limit is None:
        return True
    if spec_limit is None or compose_limit is None:
        return False

    spec_str = str(spec_limit).strip().lower()
    compose_str = str(compose_limit).strip().lower()

    # Normalize: remove spaces, lowercase
    spec_str = spec_str.replace(" ", "")
    compose_str = compose_str.replace(" ", "")

    return spec_str == compose_str


def _networks_match(spec_nets: list[str], compose_nets: list) -> bool:
    """Compare network lists."""
    spec_set = set(spec_nets)
    compose_set = set()
    for n in compose_nets:
        if isinstance(n, str):
            compose_set.add(n)
        elif isinstance(n, dict):
            # Compose supports long syntax: - network-name: {aliases: [...]}
            for key in n:
                compose_set.add(str(key))
    return spec_set == compose_set


def _depends_on_match(spec_deps: list[str], compose_deps: Any) -> bool:
    """Compare depends_on lists."""
    spec_set = set(spec_deps)
    compose_set = set()
    if not compose_deps:
        return len(spec_set) == 0
    if isinstance(compose_deps, list):
        for d in compose_deps:
            if isinstance(d, str):
                compose_set.add(d)
    elif isinstance(compose_deps, dict):
        # Compose v2.4+ supports long syntax: service_name: {condition: ...}
        compose_set = set(compose_deps.keys())
    return spec_set == compose_set


# ---------------------------------------------------------------------------
# Compose file parsing
# ---------------------------------------------------------------------------

def _load_compose(compose_path: Path) -> tuple[Optional[dict], list[Diagnostic], list[Action]]:
    """Load and parse a Docker Compose file.

    Returns (compose_dict, diagnostics, actions).
    """
    diagnostics: list[Diagnostic] = []
    actions: list[Action] = []

    if not compose_path.exists():
        diagnostics.append(Diagnostic(
            code="G2_MISSING_FILE",
            severity=Severity.critical,
            message=f"Compose file not found: {compose_path}",
            location=Location(field="compose_file", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description=f"Create the Docker Compose file at {compose_path}",
            target_field="compose_file",
            suggested_value=str(compose_path),
            priority=0,
        ))
        return None, diagnostics, actions

    try:
        text = compose_path.read_text(encoding="utf-8", errors="replace")
        compose = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        diagnostics.append(Diagnostic(
            code="G2_COMPOSE_SYNTAX",
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
            code="G2_COMPOSE_STRUCTURE",
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

    # Check for required sections
    if "services" not in compose or not compose.get("services"):
        diagnostics.append(Diagnostic(
            code="G2_COMPOSE_STRUCTURE",
            severity=Severity.critical,
            message="Compose file is missing the 'services' section",
            location=Location(field="compose_file.services", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description="Add a 'services' section to the compose file with at least one service",
            target_field="compose_file.services",
            priority=0,
        ))

    return compose, diagnostics, actions


# ---------------------------------------------------------------------------
# Check 1: Spec ↔ Artifact consistency
# ---------------------------------------------------------------------------

def _check_service_consistency(
    spec: TestbedSpec,
    compose: dict,
    compose_path: Path,
    workspace_root: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check that every spec service exists in compose with matching config."""
    compose_services = compose.get("services", {})
    spec_service_names = {s.name for s in spec.services}
    compose_service_names = set(compose_services.keys())

    # --- Services in spec but missing from compose ---
    for svc_name in spec_service_names - compose_service_names:
        diagnostics.append(Diagnostic(
            code="G2_MISSING_SERVICE",
            severity=Severity.error,
            message=f"Service '{svc_name}' is declared in the spec but not found in compose file",
            location=Location(field=f"services.{svc_name}", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description=f"Add service '{svc_name}' to the compose file with image/config from the spec",
            target_field=f"compose_file.services.{svc_name}",
            priority=1,
        ))

    # --- Services in compose but not in spec (undeclared) ---
    for svc_name in compose_service_names - spec_service_names:
        diagnostics.append(Diagnostic(
            code="G2_UNDECLARED_SERVICE",
            severity=Severity.warning,
            message=f"Service '{svc_name}' exists in compose but is not declared in the approved spec",
            location=Location(field=f"compose_file.services.{svc_name}", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.clarify,
            description=f"Either add '{svc_name}' to the approved spec or remove it from compose",
            target_field=f"services.{svc_name}",
            priority=2,
        ))

    # --- Detailed field checks for services that exist in both ---
    for svc_name in spec_service_names & compose_service_names:
        spec_svc = spec.get_service(svc_name)
        compose_svc = compose_services[svc_name]
        if not spec_svc:
            continue

        _check_image(svc_name, spec_svc, compose_svc, compose_path, diagnostics, actions)
        _check_build(svc_name, spec_svc, compose_svc, compose_path, workspace_root, diagnostics, actions)
        _check_ports(svc_name, spec_svc, compose_svc, compose_path, diagnostics, actions)
        _check_mem_limit(svc_name, spec_svc, compose_svc, compose_path, diagnostics, actions)
        _check_healthcheck(svc_name, spec_svc, compose_svc, compose_path, diagnostics, actions)
        _check_networks(svc_name, spec_svc, compose_svc, compose_path, diagnostics, actions)
        _check_depends_on(svc_name, spec_svc, compose_svc, compose_path, diagnostics, actions)


def _check_image(
    svc_name: str,
    spec_svc: Any,
    compose_svc: dict,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check image matches between spec and compose."""
    spec_image = spec_svc.image
    compose_image = compose_svc.get("image")

    if not compose_image:
        diagnostics.append(Diagnostic(
            code="G2_IMAGE_MISMATCH",
            severity=Severity.error,
            message=f"Service '{svc_name}' in compose is missing 'image' field (spec requires '{spec_image}')",
            location=Location(field=f"compose_file.services.{svc_name}.image", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description=f"Add 'image: {spec_image}' to service '{svc_name}' in compose",
            target_field=f"compose_file.services.{svc_name}.image",
            suggested_value=spec_image,
            priority=1,
        ))
    elif compose_image != spec_image:
        diagnostics.append(Diagnostic(
            code="G2_IMAGE_MISMATCH",
            severity=Severity.error,
            message=f"Service '{svc_name}' image mismatch: compose has '{compose_image}', spec requires '{spec_image}'",
            location=Location(field=f"compose_file.services.{svc_name}.image", source=str(compose_path)),
            detail=f"compose={compose_image}, spec={spec_image}",
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description=f"Set image for '{svc_name}' to '{spec_image}' in compose",
            target_field=f"compose_file.services.{svc_name}.image",
            suggested_value=spec_image,
            priority=1,
        ))


def _check_build(
    svc_name: str,
    spec_svc: Any,
    compose_svc: dict,
    compose_path: Path,
    workspace_root: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check build context matches between spec and compose."""
    spec_build = spec_svc.build
    compose_build_raw = compose_svc.get("build")

    # Normalize compose build to a string path
    compose_build = None
    if compose_build_raw:
        if isinstance(compose_build_raw, str):
            compose_build = compose_build_raw
        elif isinstance(compose_build_raw, dict):
            compose_build = compose_build_raw.get("context", "")

    # If spec has a build, compose should too
    if spec_build and not compose_build:
        diagnostics.append(Diagnostic(
            code="G2_BUILD_MISMATCH",
            severity=Severity.error,
            message=f"Service '{svc_name}' spec requires build context '{spec_build}' but compose has no build section",
            location=Location(field=f"compose_file.services.{svc_name}.build", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description=f"Add build context '{spec_build}' to service '{svc_name}' in compose",
            target_field=f"compose_file.services.{svc_name}.build",
            suggested_value=spec_build,
            priority=1,
        ))
        return

    # If spec has no build but compose does, that's a warning
    if not spec_build and compose_build:
        diagnostics.append(Diagnostic(
            code="G2_BUILD_MISMATCH",
            severity=Severity.info,
            message=f"Service '{svc_name}' has build context '{compose_build}' in compose but spec does not declare a build",
            location=Location(field=f"compose_file.services.{svc_name}.build", source=str(compose_path)),
        ))
        return

    if spec_build and compose_build:
        # Normalize both paths for comparison
        # Strip variable prefixes like ${HOST_PROJECT_DIR}/
        compose_clean = re.sub(r'^\$\{[^}]+\}/', '', compose_build)
        # Strip leading ./ from spec build
        spec_clean = re.sub(r'^\./', '', spec_build)
        # Also strip leading ./ from compose build (for non-variable paths)
        compose_clean = re.sub(r'^\./', '', compose_clean)
        # Strip trailing slashes
        spec_clean = spec_clean.rstrip("/")
        compose_clean = compose_clean.rstrip("/")

        if spec_clean != compose_clean:
            # Also try resolving both to absolute paths (relative to workspace)
            spec_resolved = str((workspace_root / spec_clean).resolve())
            compose_resolved = str(_resolve_build_path(compose_build, compose_path, workspace_root))

            if spec_resolved != compose_resolved:
                diagnostics.append(Diagnostic(
                    code="G2_BUILD_MISMATCH",
                    severity=Severity.warning,
                    message=f"Service '{svc_name}' build context mismatch: compose has '{compose_build}', spec has '{spec_build}'",
                    location=Location(field=f"compose_file.services.{svc_name}.build", source=str(compose_path)),
                    detail=f"compose={compose_build}, spec={spec_build}",
                ))
                actions.append(Action(
                    kind=ActionKind.fix,
                    description=f"Update build context for '{svc_name}' to '{spec_build}' in compose",
                    target_field=f"compose_file.services.{svc_name}.build",
                    suggested_value=spec_build,
                    priority=2,
                ))

        # Check Dockerfile exists at build context
        if compose_build:
            # Resolve the build path relative to workspace
            build_path = _resolve_build_path(compose_build, compose_path, workspace_root)
            dockerfile_path = build_path / "Dockerfile"
            if not dockerfile_path.exists():
                diagnostics.append(Diagnostic(
                    code="G2_MISSING_DOCKERFILE",
                    severity=Severity.error,
                    message=f"Dockerfile not found at expected path: {dockerfile_path}",
                    location=Location(field=f"compose_file.services.{svc_name}.build", source=str(compose_path)),
                    detail=f"Build context '{compose_build}' resolves to {build_path} but no Dockerfile found",
                ))
                actions.append(Action(
                    kind=ActionKind.add,
                    description=f"Create Dockerfile at {dockerfile_path} for service '{svc_name}'",
                    target_field=f"compose_file.services.{svc_name}.build",
                    priority=1,
                ))


def _resolve_build_path(build_str: str, compose_path: Path, workspace_root: Path) -> Path:
    """Resolve a build context path to an absolute path.

    Handles:
    - ${HOST_PROJECT_DIR}/src/... variables (strip the variable, resolve relative to workspace)
    - Relative paths (relative to compose file or workspace)
    - Absolute paths
    """
    # Strip variable references like ${HOST_PROJECT_DIR}
    clean = re.sub(r'\$\{[^}]+\}/?', '', build_str)
    clean = clean.strip()

    if not clean:
        return workspace_root

    p = Path(clean)
    # If the original build_str was an absolute path (not a variable-prefixed one),
    # return it as-is
    if p.is_absolute() and '$' not in build_str:
        return p.resolve()

    # If the path starts with / after variable stripping, it was likely
    # a variable-prefixed path like ${VAR}/src/... — resolve relative to workspace
    if p.is_absolute():
        # Strip the leading / and resolve relative to workspace
        rel = str(p.relative_to(p.anchor)) if p.anchor else str(p)
        return (workspace_root / rel.lstrip("/")).resolve()

    # Try relative to compose file directory
    compose_dir = compose_path.parent
    candidate = (compose_dir / clean).resolve()
    if candidate.exists():
        return candidate

    # Try relative to workspace root
    candidate = (workspace_root / clean).resolve()
    if candidate.exists():
        return candidate

    # Fall back to workspace-relative (even if it doesn't exist yet)
    return (workspace_root / clean).resolve()


def _check_ports(
    svc_name: str,
    spec_svc: Any,
    compose_svc: dict,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check port mappings match between spec and compose."""
    spec_ports = set()
    for p in spec_svc.ports:
        spec_ports.add(_normalize_port_str(p.host, p.container, p.protocol))

    compose_ports_raw = compose_svc.get("ports", [])
    compose_ports = set()
    for p in compose_ports_raw:
        normalized = _compose_port_to_normalized(p)
        if normalized:
            compose_ports.add(normalized)

    if spec_ports != compose_ports:
        missing = spec_ports - compose_ports
        extra = compose_ports - spec_ports
        detail_parts = []
        if missing:
            detail_parts.append(f"missing from compose: {', '.join(sorted(missing))}")
        if extra:
            detail_parts.append(f"extra in compose: {', '.join(sorted(extra))}")

        diagnostics.append(Diagnostic(
            code="G2_PORT_MISMATCH",
            severity=Severity.warning,
            message=f"Service '{svc_name}' port mappings differ between spec and compose",
            location=Location(field=f"compose_file.services.{svc_name}.ports", source=str(compose_path)),
            detail="; ".join(detail_parts) if detail_parts else "ports differ",
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description=f"Update port mappings for '{svc_name}' in compose to match spec: {', '.join(sorted(spec_ports))}",
            target_field=f"compose_file.services.{svc_name}.ports",
            suggested_value=list(spec_ports),
            priority=2,
        ))


def _check_mem_limit(
    svc_name: str,
    spec_svc: Any,
    compose_svc: dict,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check memory limit matches between spec and compose."""
    spec_mem = spec_svc.mem_limit
    compose_mem = compose_svc.get("mem_limit")

    if not _mem_limits_match(spec_mem, compose_mem):
        if spec_mem and not compose_mem:
            diagnostics.append(Diagnostic(
                code="G2_MEMLIMIT_MISMATCH",
                severity=Severity.error,
                message=f"Service '{svc_name}' is missing mem_limit in compose (spec requires '{spec_mem}')",
                location=Location(field=f"compose_file.services.{svc_name}.mem_limit", source=str(compose_path)),
            ))
            actions.append(Action(
                kind=ActionKind.add,
                description=f"Add 'mem_limit: {spec_mem}' to service '{svc_name}' in compose",
                target_field=f"compose_file.services.{svc_name}.mem_limit",
                suggested_value=spec_mem,
                priority=1,
            ))
        elif not spec_mem and compose_mem:
            diagnostics.append(Diagnostic(
                code="G2_MEMLIMIT_MISMATCH",
                severity=Severity.info,
                message=f"Service '{svc_name}' has mem_limit '{compose_mem}' in compose but spec does not declare one",
                location=Location(field=f"compose_file.services.{svc_name}.mem_limit", source=str(compose_path)),
            ))
        else:
            diagnostics.append(Diagnostic(
                code="G2_MEMLIMIT_MISMATCH",
                severity=Severity.error,
                message=f"Service '{svc_name}' mem_limit mismatch: compose has '{compose_mem}', spec requires '{spec_mem}'",
                location=Location(field=f"compose_file.services.{svc_name}.mem_limit", source=str(compose_path)),
                detail=f"compose={compose_mem}, spec={spec_mem}",
            ))
            actions.append(Action(
                kind=ActionKind.fix,
                description=f"Set mem_limit for '{svc_name}' to '{spec_mem}' in compose",
                target_field=f"compose_file.services.{svc_name}.mem_limit",
                suggested_value=spec_mem,
                priority=1,
            ))


def _check_healthcheck(
    svc_name: str,
    spec_svc: Any,
    compose_svc: dict,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check healthcheck matches between spec and compose."""
    spec_hc = spec_svc.healthcheck
    compose_hc = compose_svc.get("healthcheck")

    if not _healthchecks_match(spec_hc, compose_hc):
        if spec_hc and not compose_hc:
            diagnostics.append(Diagnostic(
                code="G2_HEALTHCHECK_MISMATCH",
                severity=Severity.error,
                message=f"Service '{svc_name}' is missing healthcheck in compose (spec requires one)",
                location=Location(field=f"compose_file.services.{svc_name}.healthcheck", source=str(compose_path)),
            ))
            actions.append(Action(
                kind=ActionKind.add,
                description=f"Add healthcheck to service '{svc_name}' in compose matching the spec",
                target_field=f"compose_file.services.{svc_name}.healthcheck",
                suggested_value=spec_hc,
                priority=1,
            ))
        elif not spec_hc and compose_hc:
            diagnostics.append(Diagnostic(
                code="G2_HEALTHCHECK_MISMATCH",
                severity=Severity.info,
                message=f"Service '{svc_name}' has healthcheck in compose but spec does not declare one",
                location=Location(field=f"compose_file.services.{svc_name}.healthcheck", source=str(compose_path)),
            ))
        else:
            diagnostics.append(Diagnostic(
                code="G2_HEALTHCHECK_MISMATCH",
                severity=Severity.warning,
                message=f"Service '{svc_name}' healthcheck differs between spec and compose",
                location=Location(field=f"compose_file.services.{svc_name}.healthcheck", source=str(compose_path)),
                detail="Healthcheck test commands differ",
            ))
            actions.append(Action(
                kind=ActionKind.fix,
                description=f"Update healthcheck for '{svc_name}' in compose to match spec",
                target_field=f"compose_file.services.{svc_name}.healthcheck",
                suggested_value=spec_hc,
                priority=2,
            ))


def _check_networks(
    svc_name: str,
    spec_svc: Any,
    compose_svc: dict,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check network attachments match between spec and compose."""
    spec_nets = spec_svc.networks
    compose_nets = compose_svc.get("networks", [])

    if not _networks_match(spec_nets, compose_nets):
        spec_set = set(spec_nets)
        compose_set = set()
        for n in compose_nets:
            if isinstance(n, str):
                compose_set.add(n)
            elif isinstance(n, dict):
                compose_set.update(n.keys())

        missing = spec_set - compose_set
        extra = compose_set - spec_set
        detail_parts = []
        if missing:
            detail_parts.append(f"missing from compose: {', '.join(sorted(missing))}")
        if extra:
            detail_parts.append(f"extra in compose: {', '.join(sorted(extra))}")

        diagnostics.append(Diagnostic(
            code="G2_NETWORK_MISMATCH",
            severity=Severity.error,
            message=f"Service '{svc_name}' network attachments differ between spec and compose",
            location=Location(field=f"compose_file.services.{svc_name}.networks", source=str(compose_path)),
            detail="; ".join(detail_parts) if detail_parts else "networks differ",
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description=f"Update networks for '{svc_name}' in compose to match spec: {', '.join(sorted(spec_nets))}",
            target_field=f"compose_file.services.{svc_name}.networks",
            suggested_value=list(spec_nets),
            priority=1,
        ))


def _check_depends_on(
    svc_name: str,
    spec_svc: Any,
    compose_svc: dict,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check depends_on matches between spec and compose."""
    spec_deps = spec_svc.depends_on
    compose_deps = compose_svc.get("depends_on")

    if not _depends_on_match(spec_deps, compose_deps):
        spec_set = set(spec_deps)
        compose_set = set()
        if isinstance(compose_deps, list):
            compose_set = {d for d in compose_deps if isinstance(d, str)}
        elif isinstance(compose_deps, dict):
            compose_set = set(compose_deps.keys())

        missing = spec_set - compose_set
        extra = compose_set - spec_set
        detail_parts = []
        if missing:
            detail_parts.append(f"missing from compose: {', '.join(sorted(missing))}")
        if extra:
            detail_parts.append(f"extra in compose: {', '.join(sorted(extra))}")

        diagnostics.append(Diagnostic(
            code="G2_DEPENDS_MISMATCH",
            severity=Severity.warning,
            message=f"Service '{svc_name}' depends_on differs between spec and compose",
            location=Location(field=f"compose_file.services.{svc_name}.depends_on", source=str(compose_path)),
            detail="; ".join(detail_parts) if detail_parts else "depends_on differs",
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description=f"Update depends_on for '{svc_name}' in compose to match spec: {', '.join(sorted(spec_deps))}",
            target_field=f"compose_file.services.{svc_name}.depends_on",
            suggested_value=list(spec_deps),
            priority=2,
        ))


# ---------------------------------------------------------------------------
# Check 2: Required files exist
# ---------------------------------------------------------------------------

def _check_required_files(
    spec: TestbedSpec,
    workspace_root: Path,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check that all required files referenced by the spec exist on disk."""
    # Compose file itself (already checked in _load_compose)
    # Build context Dockerfiles (checked in _check_build)

    # Check test suite paths
    for ts in spec.test_suites:
        test_path = workspace_root / ts.path.lstrip("/")
        if not test_path.exists():
            diagnostics.append(Diagnostic(
                code="G2_MISSING_TEST_SUITE",
                severity=Severity.warning,
                message=f"Test suite '{ts.name}' path not found: {test_path}",
                location=Location(field=f"test_suites.{ts.name}.path", source=str(test_path)),
            ))
            actions.append(Action(
                kind=ActionKind.add,
                description=f"Create test directory at {test_path} for test suite '{ts.name}'",
                target_field=f"test_suites.{ts.name}.path",
                suggested_value=str(test_path),
                priority=3,
            ))

    # Check config files referenced by services
    for svc in spec.services:
        if svc.build:
            build_path = _resolve_build_path(svc.build, compose_path, workspace_root)
            # Check for Dockerfile
            dockerfile = build_path / "Dockerfile"
            if not dockerfile.exists():
                diagnostics.append(Diagnostic(
                    code="G2_MISSING_DOCKERFILE",
                    severity=Severity.error,
                    message=f"Dockerfile not found at {dockerfile} for service '{svc.name}' (build context: {svc.build})",
                    location=Location(field=f"services.{svc.name}.build", source=str(dockerfile)),
                ))
                actions.append(Action(
                    kind=ActionKind.add,
                    description=f"Create Dockerfile at {dockerfile} for service '{svc.name}'",
                    target_field=f"services.{svc.name}.build",
                    priority=1,
                ))


# ---------------------------------------------------------------------------
# Check 3: Network consistency
# ---------------------------------------------------------------------------

def _check_network_consistency(
    spec: TestbedSpec,
    compose: dict,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check that networks declared in spec exist in compose and vice versa."""
    spec_networks = set(spec.infrastructure.networks.keys())
    compose_networks = set(compose.get("networks", {}).keys()) if isinstance(compose.get("networks"), dict) else set()

    # Networks in spec but missing from compose
    for net_name in spec_networks - compose_networks:
        diagnostics.append(Diagnostic(
            code="G2_NETWORK_MISSING",
            severity=Severity.error,
            message=f"Network '{net_name}' is declared in spec but not found in compose networks section",
            location=Location(field=f"infrastructure.networks.{net_name}", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description=f"Add network '{net_name}' to compose file networks section",
            target_field=f"compose_file.networks.{net_name}",
            suggested_value={"driver": "bridge"},
            priority=1,
        ))

    # Networks in compose but not in spec
    for net_name in compose_networks - spec_networks:
        diagnostics.append(Diagnostic(
            code="G2_NETWORK_UNDECLARED",
            severity=Severity.warning,
            message=f"Network '{net_name}' exists in compose but is not declared in the approved spec",
            location=Location(field=f"compose_file.networks.{net_name}", source=str(compose_path)),
        ))
        actions.append(Action(
            kind=ActionKind.clarify,
            description=f"Either add network '{net_name}' to the spec or remove it from compose",
            target_field=f"infrastructure.networks.{net_name}",
            priority=2,
        ))


# ---------------------------------------------------------------------------
# Check 4: Test suite presence
# ---------------------------------------------------------------------------

def _check_test_suite_presence(
    spec: TestbedSpec,
    workspace_root: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check that test suite paths exist on disk."""
    for ts in spec.test_suites:
        test_path = workspace_root / ts.path.lstrip("/")
        if not test_path.exists():
            diagnostics.append(Diagnostic(
                code="G2_MISSING_TEST_SUITE",
                severity=Severity.warning,
                message=f"Test suite '{ts.name}' path not found on disk: {test_path}",
                location=Location(field=f"test_suites.{ts.name}.path", source=str(test_path)),
            ))
            actions.append(Action(
                kind=ActionKind.add,
                description=f"Create test directory and test files at {test_path} for suite '{ts.name}'",
                target_field=f"test_suites.{ts.name}.path",
                priority=3,
            ))
        else:
            # Check for at least one test file
            test_files = list(test_path.rglob("test_*.py"))
            if not test_files:
                diagnostics.append(Diagnostic(
                    code="G2_MISSING_TEST_SUITE",
                    severity=Severity.warning,
                    message=f"Test suite '{ts.name}' path exists ({test_path}) but contains no test_*.py files",
                    location=Location(field=f"test_suites.{ts.name}.path", source=str(test_path)),
                ))
                actions.append(Action(
                    kind=ActionKind.add,
                    description=f"Add at least one test_*.py file to {test_path} for suite '{ts.name}'",
                    target_field=f"test_suites.{ts.name}.path",
                    priority=3,
                ))


# ---------------------------------------------------------------------------
# Check 5: Static hygiene
# ---------------------------------------------------------------------------

def _check_static_hygiene(
    workspace_root: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> None:
    """Check for obvious syntax problems in key config files."""
    # Check envoy.yaml if it exists
    envoy_paths = [
        workspace_root / "src" / "quic-edge-proxy" / "envoy.yaml",
    ]
    for ep in envoy_paths:
        if ep.exists():
            try:
                text = ep.read_text(encoding="utf-8", errors="replace")
                yaml.safe_load(text)
            except yaml.YAMLError as exc:
                diagnostics.append(Diagnostic(
                    code="G2_ENVOY_CONFIG_SYNTAX",
                    severity=Severity.error,
                    message=f"Envoy config has YAML syntax error: {exc}",
                    location=Location(field="config_file", source=str(ep)),
                    detail=str(exc),
                ))
                actions.append(Action(
                    kind=ActionKind.fix,
                    description=f"Fix YAML syntax error in {ep}: {exc}",
                    target_field="config_file",
                    priority=1,
                ))

    # Check Caddyfile if it exists
    caddy_paths = [
        workspace_root / "src" / "caddy" / "Caddyfile",
    ]
    for cp in caddy_paths:
        if cp.exists():
            try:
                text = cp.read_text(encoding="utf-8", errors="replace")
                # Basic check: Caddyfile should have at least one address line
                if not any(line.strip() and not line.strip().startswith("#") for line in text.splitlines()):
                    diagnostics.append(Diagnostic(
                        code="G2_CONFIG_SYNTAX",
                        severity=Severity.warning,
                        message=f"Caddyfile appears empty or has no directives: {cp}",
                        location=Location(field="config_file", source=str(cp)),
                    ))
            except (OSError, PermissionError) as exc:
                diagnostics.append(Diagnostic(
                    code="G2_CONFIG_SYNTAX",
                    severity=Severity.warning,
                    message=f"Cannot read config file {cp}: {exc}",
                    location=Location(field="config_file", source=str(cp)),
                ))

    # Check Dockerfiles for basic syntax
    dockerfile_paths = list(workspace_root.rglob("Dockerfile"))
    for df in dockerfile_paths:
        try:
            text = df.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            # Basic check: Dockerfile should have at least a FROM instruction
            has_from = any(line.strip().upper().startswith("FROM") for line in lines)
            if not has_from:
                diagnostics.append(Diagnostic(
                    code="G2_CONFIG_SYNTAX",
                    severity=Severity.warning,
                    message=f"Dockerfile at {df} has no FROM instruction",
                    location=Location(field="config_file", source=str(df)),
                ))
        except (OSError, PermissionError) as exc:
            diagnostics.append(Diagnostic(
                code="G2_CONFIG_SYNTAX",
                severity=Severity.warning,
                message=f"Cannot read Dockerfile {df}: {exc}",
                location=Location(field="config_file", source=str(df)),
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

def validate_code(
    spec: TestbedSpec,
    workspace_root: Path = Path("/workspace"),
    compose_path: Optional[Path] = None,
    attempt_number: int = 1,
    previous_summary: Optional[str] = None,
) -> GateFeedback:
    """Validate implementation artifacts against an approved TestbedSpec.

    This is the primary entry point for Gate 2. It checks that the code
    under workspace_root is consistent with the spec and statically sound.

    Hard rule: After every code change under /workspace, call this function.
    If status != "pass", apply the returned actions, then re-validate.
    Only proceed to runtime testing when status == "pass".

    Args:
        spec: The approved, validated TestbedSpec.
        workspace_root: Root directory of the implementation (default: /workspace).
        compose_path: Path to the Docker Compose file. If None, auto-detect.
        attempt_number: Which attempt this is (for tracking iteration).
        previous_summary: One-line summary of the previous feedback attempt.

    Returns:
        GateFeedback with diagnostics and actions.
    """
    start_time = time.time()
    feedback_kwargs = {
        "gate_id": "gate2.code_validator",
        "gate_version": "0.1.0",
    }

    diagnostics: list[Diagnostic] = []
    actions: list[Action] = []

    # Guard: spec must be a TestbedSpec instance
    if not isinstance(spec, TestbedSpec):
        return GateFeedback(
            gate_id="gate2.code_validator",
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
        candidates = [
            workspace_root / "deploy" / "compose" / "root.yml",
            workspace_root / "deploy" / "compose" / "root.yaml",
            workspace_root / "docker-compose.yml",
            workspace_root / "docker-compose.yaml",
            workspace_root / "compose.yml",
            workspace_root / "compose.yaml",
        ]
        compose_path = None
        for c in candidates:
            if c.exists():
                compose_path = c
                break

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
                    code="G2_MISSING_FILE",
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
    _check_service_consistency(spec, compose, compose_path, workspace_root, diagnostics, actions)
    _check_required_files(spec, workspace_root, compose_path, diagnostics, actions)
    _check_network_consistency(spec, compose, compose_path, diagnostics, actions)
    _check_test_suite_presence(spec, workspace_root, diagnostics, actions)
    _check_static_hygiene(workspace_root, diagnostics, actions)

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

def validate_code_from_file(
    spec_path: Path,
    workspace_root: Path = Path("/workspace"),
    compose_path: Optional[Path] = None,
    attempt_number: int = 1,
    previous_summary: Optional[str] = None,
) -> GateFeedback:
    """Load a TestbedSpec from a JSON file and validate the implementation.

    This is the CLI-friendly entry point.

    Args:
        spec_path: Path to the approved TestbedSpec JSON file.
        workspace_root: Root directory of the implementation.
        compose_path: Path to the Docker Compose file (auto-detect if None).
        attempt_number: Which attempt this is.
        previous_summary: One-line summary of the previous feedback attempt.

    Returns:
        GateFeedback with diagnostics and actions.
    """
    start_time = time.time()

    if not spec_path.exists():
        return GateFeedback(
            gate_id="gate2.code_validator",
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
            gate_id="gate2.code_validator",
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
            gate_id="gate2.code_validator",
            gate_version="0.1.0",
            status=GateStatus.error,
            diagnostics=[
                Diagnostic(
                    code="GATE_CRASH",
                    severity=Severity.critical,
                    message=f"Spec file is not a valid TestbedSpec: {exc}",
                    location=Location(field="spec_file", source=str(spec_path)),
                    detail=str(exc),
                ),
            ],
            duration_ms=int((time.time() - start_time) * 1000),
            attempt_number=attempt_number,
        )

    return validate_code(
        spec,
        workspace_root=workspace_root,
        compose_path=compose_path,
        attempt_number=attempt_number,
        previous_summary=previous_summary,
    )
