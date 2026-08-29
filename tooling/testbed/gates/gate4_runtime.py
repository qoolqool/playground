"""Gate 4 — Runtime & Integration Verification.

YOU OWN THE QUALITY GATE. This is a mandatory checkpoint you must call yourself
after Gate 3 passes and before claiming HARDEN / runtime-ready.

Gate 4 answers:
  "Does the stack actually boot, stay healthy, and pass automated runtime checks?"

Gates 1–3 are static. They cannot prove boot, health, or integration.
Gate 4 wraps operational truth into structured feedback the agent can act on.

The gate checks:
  1. Lifecycle / readiness — is the stack up? If not, attempt bring-up.
  2. Verify gate — run bootstrap.sh verify (or equivalent), parse pass/fail.
  3. Unhealthy services — if verify names failing services, emit per-service diagnostics.
  4. E2E test suite — run the project's e2e test suite (owned by Gate 4, not
     Gate 2) as the integration gate. Runs via a test-runner container when one
     exists, or directly on the host for small projects.
  5. Failure evidence — attach short, truncated command output in diagnostics.

Hard rule:
  After Gate 3 passes → call validate_runtime() →
  if status != "pass", apply the returned actions, then re-validate.
  Do NOT claim HARDEN / runtime-ready while Gate 4 is failing.

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
    "G4_STACK_NOT_RUNNING": "Stack is not running and --skip-up was set",
    "G4_BOOTSTRAP_FAILED": "bootstrap.sh up failed to bring the stack up",
    "G4_VERIFY_FAILED": "bootstrap.sh verify reported failures",
    "G4_SERVICE_UNHEALTHY": "A specific service is unhealthy",
    "G4_E2E_TEST_FAILED": "E2E happy-flow integration test failed",
    "G4_COMMAND_ERROR": "Tooling or subprocess invocation error",
}

# Maximum lines of output to include in diagnostics
_MAX_OUTPUT_LINES = 50

# Default E2E test timeout (seconds)
_DEFAULT_E2E_TIMEOUT = 300

# Expected container names for the QUIC Edge v2 testbed
_EXPECTED_CONTAINERS = [
    "quic-edge-proxy",
    "caddy",
    "mock-payment-api",
    "quic-client",
    "test-runner",
    "netem-router",
    "cert-gen",
    "anti-replay-cache",
    "prometheus",
    "otel-collector",
    "grafana",
]

# Maximum actions to return
_MAX_ACTIONS = 7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate_output(text: str, max_lines: int = _MAX_OUTPUT_LINES) -> str:
    """Truncate output to max_lines, keeping head and tail if very long."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    head = lines[: max_lines // 2]
    tail = lines[-(max_lines // 2) :]
    return "\n".join(head) + f"\n... ({len(lines) - max_lines} more lines) ...\n" + "\n".join(tail)


def _run_command(
    cmd: list[str],
    cwd: Optional[Path] = None,
    timeout: int = 120,
    env: Optional[dict[str, str]] = None,
) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr).

    Never raises — captures all errors into the return tuple.
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **(env or {})},
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError:
        return -2, "", f"Command not found: {cmd[0]}"
    except OSError as exc:
        return -3, "", f"OS error running {' '.join(cmd)}: {exc}"
    except Exception as exc:
        return -99, "", f"Unexpected error: {exc}"


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


def _find_spec(workspace_root: Path):
    """Locate the testbed spec in the workspace.

    Prefers the legacy hardcoded names for backward compatibility, then falls
    back to any *-spec.json in the workspace root.
    """
    legacy = [
        workspace_root / "quic-edge-v2-spec.json",
        workspace_root / "quic-edge-spec.json",
    ]
    for sp in legacy:
        if sp.exists():
            return sp
    for sp in sorted(workspace_root.glob("*-spec.json")):
        if sp.exists():
            return sp
    return None


def _get_expected_container_count(workspace_root: Path) -> int:
    """Get the expected number of containers from the spec or fallback list."""
    sp = _find_spec(workspace_root)
    if sp is not None:
        try:
            data = json.loads(sp.read_text())
            services = data.get("services", [])
            if services:
                return len(services)
        except (json.JSONDecodeError, OSError):
            pass
    return len(_EXPECTED_CONTAINERS)


def _get_expected_container_names(workspace_root: Path) -> list[str]:
    """Get expected container names from the spec or fallback list."""
    sp = _find_spec(workspace_root)
    if sp is not None:
        try:
            data = json.loads(sp.read_text())
            services = data.get("services", [])
            if services:
                return [s.get("name", "") for s in services if s.get("name")]
        except (json.JSONDecodeError, OSError):
            pass
    return list(_EXPECTED_CONTAINERS)


# ---------------------------------------------------------------------------
# Check 1: Lifecycle / readiness
# ---------------------------------------------------------------------------

def _check_lifecycle(
    workspace_root: Path,
    compose_path: Path,
    skip_up: bool,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> bool:
    """Check if the stack is running. If not, attempt bring-up unless skip_up.

    Returns True if the stack is (or became) running, False otherwise.
    """
    # Check current state
    rc, stdout, stderr = _run_command(
        ["docker", "compose", "-f", str(compose_path), "ps", "--format", "{{.Name}}"],
        cwd=workspace_root,
        timeout=30,
    )

    if rc != 0:
        diagnostics.append(Diagnostic(
            code="G4_COMMAND_ERROR",
            severity=Severity.error,
            message="Failed to list Docker Compose services",
            location=Location(field="compose_file", source=str(compose_path)),
            detail=_truncate_output(stderr or stdout, 20),
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description="Ensure Docker is running and the compose file is valid",
            target_field="compose_file",
            priority=0,
        ))
        return False

    running_containers = [line.strip() for line in stdout.splitlines() if line.strip()]
    expected_count = _get_expected_container_count(workspace_root)

    if len(running_containers) >= expected_count:
        # Stack is running
        return True

    if skip_up:
        # Stack not running and skip-up is set — fail clearly
        diagnostics.append(Diagnostic(
            code="G4_STACK_NOT_RUNNING",
            severity=Severity.critical,
            message=f"Stack is not running (found {len(running_containers)}/{expected_count} containers) "
                    f"and --skip-up was set. Cannot proceed without a running stack.",
            location=Location(field="compose_file", source=str(compose_path)),
            detail=f"Running: {running_containers}\nExpected: ~{expected_count} containers",
        ))
        actions.append(Action(
            kind=ActionKind.retry,
            description="Run without --skip-up to auto-start the stack, or manually run "
                        "'bootstrap.sh up' from the workspace",
            target_field="compose_file",
            priority=0,
        ))
        return False

    # Attempt bring-up via bootstrap.sh
    bootstrap_script = workspace_root / "scripts" / "bootstrap.sh"
    if not bootstrap_script.exists():
        diagnostics.append(Diagnostic(
            code="G4_COMMAND_ERROR",
            severity=Severity.error,
            message=f"Bootstrap script not found at {bootstrap_script}",
            location=Location(field="bootstrap_script", source=str(bootstrap_script)),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description=f"Create bootstrap script at {bootstrap_script} or ensure the stack is running",
            target_field="bootstrap_script",
            priority=0,
        ))
        return False

    rc, stdout, stderr = _run_command(
        ["bash", str(bootstrap_script), "up"],
        cwd=workspace_root,
        timeout=180,
    )

    if rc != 0:
        diagnostics.append(Diagnostic(
            code="G4_BOOTSTRAP_FAILED",
            severity=Severity.critical,
            message=f"bootstrap.sh up failed (exit code {rc})",
            location=Location(field="bootstrap_script", source=str(bootstrap_script)),
            detail=_truncate_output(stdout + "\n" + stderr, _MAX_OUTPUT_LINES),
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description="Check bootstrap.sh output above for errors. Common issues: "
                        "missing Docker images, port conflicts, or config file errors. "
                        "Run 'bash scripts/bootstrap.sh up' manually to see full output.",
            target_field="bootstrap_script",
            priority=0,
        ))
        return False

    # Verify the stack actually came up
    time.sleep(5)  # Brief settling time
    rc, stdout, stderr = _run_command(
        ["docker", "compose", "-f", str(compose_path), "ps", "--format", "{{.Name}}"],
        cwd=workspace_root,
        timeout=30,
    )
    running_containers = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(running_containers) < expected_count:
        diagnostics.append(Diagnostic(
            code="G4_BOOTSTRAP_FAILED",
            severity=Severity.critical,
            message=f"bootstrap.sh up completed but only {len(running_containers)}/{expected_count} "
                    f"containers are running",
            location=Location(field="compose_file", source=str(compose_path)),
            detail=f"Running: {running_containers}\nExpected: ~{expected_count} containers",
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description="Check 'docker compose ps' for containers that failed to start. "
                        "Inspect logs with 'docker compose logs <service>'",
            target_field="compose_file",
            priority=0,
        ))
        return False

    return True


# ---------------------------------------------------------------------------
# Check 2: Verify gate — run bootstrap.sh verify
# ---------------------------------------------------------------------------

def _run_verify(
    workspace_root: Path,
    compose_path: Path,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> bool:
    """Run bootstrap.sh verify and parse results.

    Returns True if all verification gates pass, False otherwise.
    """
    bootstrap_script = workspace_root / "scripts" / "bootstrap.sh"
    if not bootstrap_script.exists():
        diagnostics.append(Diagnostic(
            code="G4_COMMAND_ERROR",
            severity=Severity.error,
            message=f"Bootstrap script not found at {bootstrap_script}",
            location=Location(field="bootstrap_script", source=str(bootstrap_script)),
        ))
        return False

    rc, stdout, stderr = _run_command(
        ["bash", str(bootstrap_script), "verify"],
        cwd=workspace_root,
        timeout=120,
    )

    output = stdout + "\n" + stderr

    if rc != 0:
        # Parse per-service health from verify output
        fail_lines = []
        ok_lines = []
        for line in output.splitlines():
            if "FAIL:" in line:
                fail_lines.append(line.strip())
            elif "OK:" in line:
                ok_lines.append(line.strip())

        # Extract unhealthy services
        unhealthy_services = []
        for line in fail_lines:
            # Format: "FAIL: container_name health=unhealthy"
            m = re.match(r"FAIL:\s+(\S+)\s+health=(\S+)", line)
            if m:
                unhealthy_services.append((m.group(1), m.group(2)))
            else:
                # Generic FAIL line
                unhealthy_services.append((line, "unknown"))

        # Report verify failure
        diagnostics.append(Diagnostic(
            code="G4_VERIFY_FAILED",
            severity=Severity.error,
            message=f"bootstrap.sh verify reported {len(fail_lines)} failure(s)",
            location=Location(field="bootstrap_script", source=str(bootstrap_script)),
            detail=_truncate_output(output, _MAX_OUTPUT_LINES),
        ))

        # Per-service unhealthy diagnostics
        for svc_name, health_status in unhealthy_services:
            diagnostics.append(Diagnostic(
                code="G4_SERVICE_UNHEALTHY",
                severity=Severity.error,
                message=f"Service '{svc_name}' is unhealthy (health={health_status})",
                location=Location(field=f"services.{svc_name}", source=str(compose_path)),
                detail=f"Health status: {health_status}. "
                       f"Check logs with: docker compose logs {svc_name}",
            ))
            actions.append(Action(
                kind=ActionKind.fix,
                description=f"Inspect '{svc_name}' logs: docker compose logs {svc_name}. "
                            f"Check healthcheck config and service readiness.",
                target_field=f"services.{svc_name}",
                priority=1,
            ))

        # Also check for missing networks
        for line in fail_lines:
            if "missing" in line.lower():
                m = re.match(r"FAIL:\s+(.+)", line)
                if m:
                    diagnostics.append(Diagnostic(
                        code="G4_VERIFY_FAILED",
                        severity=Severity.error,
                        message=f"Network/Infrastructure issue: {m.group(1)}",
                        location=Location(field="infrastructure.networks", source=str(compose_path)),
                        detail=m.group(1),
                    ))

        actions.append(Action(
            kind=ActionKind.fix,
            description="Run 'bash scripts/bootstrap.sh verify' manually to see full output. "
                        "Fix unhealthy services and re-run Gate 4.",
            target_field="bootstrap_script",
            priority=0,
        ))
        return False

    # Verify passed — all OK
    return True


# ---------------------------------------------------------------------------
# Check 3: E2E happy-flow integration test
# ---------------------------------------------------------------------------

def _compose_has_service(compose_path: Path, service_name: str) -> bool:
    """Return True if the compose file declares the given service."""
    rc, stdout, stderr = _run_command(
        ["docker", "compose", "-f", str(compose_path), "config", "--services"],
        timeout=60,
    )
    if rc != 0:
        return False
    return service_name in stdout.split()


def _run_e2e_happy_flow(
    workspace_root: Path,
    compose_path: Path,
    timeout: int,
    diagnostics: list[Diagnostic],
    actions: list[Action],
) -> bool:
    """Run the E2E test suite as the integration gate pass criteria.

    The E2E suite is owned by Gate 4, not Gate 2. It is discovered from the
    spec (a suite named 'e2e' or tagged/marked 'live'). It runs either:
      1. via a test-runner container (docker compose exec test-runner), or
      2. directly on the host with pytest and the suite's markers, when no
         test-runner service exists (small projects).

    Returns True if the test passes, False otherwise.
    """
    # Discover the E2E test suite from the spec
    spec_path = _find_spec(workspace_root)
    e2e_suite = None
    if spec_path is not None:
        try:
            data = json.loads(spec_path.read_text())
            for ts in data.get("test_suites", []):
                name = (ts.get("name") or "").lower()
                tags = {t.lower() for t in (ts.get("tags") or [])}
                markers = {m.lower() for m in (ts.get("markers") or [])}
                if name == "e2e" or bool(tags & {"e2e", "live"}) or bool(markers & {"live"}):
                    e2e_suite = ts
                    break
        except (json.JSONDecodeError, OSError):
            e2e_suite = None

    if e2e_suite is None:
        diagnostics.append(Diagnostic(
            code="G4_COMMAND_ERROR",
            severity=Severity.warning,
            message="No E2E test suite found in the spec (expected a suite named 'e2e' or tagged/marked 'live')",
            location=Location(field="test_suites.e2e", source=str(spec_path) if spec_path else str(workspace_root)),
        ))
        # Not a hard failure — the verify gate already passed
        return True

    test_path = e2e_suite.get("path", "tests/")
    marker_args: list[str] = []
    for m in e2e_suite.get("markers", []):
        marker_args += ["-m", m]

    # Decide how to run: test-runner container (larger projects) or direct host
    # run (small projects). This is an explicit decision, not a guess.
    if _compose_has_service(compose_path, "test-runner"):
        cmd = [
            "docker", "compose", "-f", str(compose_path),
            "exec", "-T", "test-runner",
            "python3", "-m", "pytest",
            test_path, "-v", "-s", "--no-header", "-x",
        ] + marker_args
    else:
        # Small project: run directly on the host, hitting published ports
        cmd = [
            "python3", "-m", "pytest",
            test_path, "-v", "-s", "--no-header", "-x",
        ] + marker_args

    rc, stdout, stderr = _run_command(cmd, cwd=workspace_root, timeout=timeout)
    output = stdout + "\n" + stderr

    if rc != 0:
        # Parse pytest output for failure details
        fail_summary = ""
        for line in output.splitlines():
            if "FAILED" in line or "failed" in line.lower():
                fail_summary += line + "\n"

        diagnostics.append(Diagnostic(
            code="G4_E2E_TEST_FAILED",
            severity=Severity.error,
            message=f"E2E test suite failed (exit code {rc})",
            location=Location(field="test_suites.e2e", source=str(test_path)),
            detail=_truncate_output(
                (fail_summary or output),
                _MAX_OUTPUT_LINES,
            ),
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description=f"Run the E2E test manually to see full output:\n"
                        f"  python3 -m pytest {test_path} -v -s\n"
                        f"Fix the failing test and re-run Gate 4.",
            target_field="test_suites.e2e",
            priority=1,
        ))
        return False

    return True


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

def validate_runtime(
    workspace_root: Path = Path("/workspace"),
    compose_path: Optional[Path] = None,
    skip_up: bool = False,
    e2e_timeout: int = _DEFAULT_E2E_TIMEOUT,
    attempt_number: int = 1,
    previous_summary: Optional[str] = None,
) -> GateFeedback:
    """Validate that the stack is running, healthy, and passes integration tests.

    This is the primary entry point for Gate 4. It checks that the stack
    under workspace_root actually boots, stays healthy, and passes
    automated runtime checks.

    Hard rule: After Gate 3 passes, call this function. If status != "pass",
    apply the returned actions, then re-validate. Do NOT claim HARDEN /
    runtime-ready while Gate 4 is failing.

    Args:
        workspace_root: Root directory of the implementation (default: /workspace).
        compose_path: Path to the Docker Compose file. If None, auto-detect.
        skip_up: If True, skip automatic bring-up when stack is not running.
        e2e_timeout: Timeout in seconds for the E2E happy-flow test.
        attempt_number: Which attempt this is (for tracking iteration).
        previous_summary: One-line summary of the previous feedback attempt.

    Returns:
        GateFeedback with diagnostics and actions.
    """
    start_time = time.time()
    feedback_kwargs = {
        "gate_id": "gate4.runtime",
        "gate_version": "0.1.0",
    }

    diagnostics: list[Diagnostic] = []
    actions: list[Action] = []

    # --- Resolve compose path ---
    if compose_path is None:
        compose_path = _resolve_compose_path(workspace_root)

    if compose_path is None:
        duration_ms = int((time.time() - start_time) * 1000)
        return GateFeedback(
            status=GateStatus.fail,
            diagnostics=[
                Diagnostic(
                    code="G4_COMMAND_ERROR",
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
            duration_ms=duration_ms,
            attempt_number=attempt_number,
            **feedback_kwargs,
        )

    # --- Phase 1: Lifecycle check ---
    stack_running = _check_lifecycle(
        workspace_root, compose_path, skip_up, diagnostics, actions,
    )

    if not stack_running:
        # Stack is not running and we couldn't bring it up
        duration_ms = int((time.time() - start_time) * 1000)
        metadata = {"attempt_number": attempt_number}
        if previous_summary:
            metadata["previous_summary"] = previous_summary

        return GateFeedback(
            status=GateStatus.fail,
            diagnostics=diagnostics,
            actions=_sort_and_cap_actions(actions),
            duration_ms=duration_ms,
            attempt_number=attempt_number,
            metadata=metadata,
            **feedback_kwargs,
        )

    # --- Phase 2: Verify gate ---
    verify_passed = _run_verify(workspace_root, compose_path, diagnostics, actions)

    if not verify_passed:
        duration_ms = int((time.time() - start_time) * 1000)
        metadata = {"attempt_number": attempt_number}
        if previous_summary:
            metadata["previous_summary"] = previous_summary

        return GateFeedback(
            status=GateStatus.fail,
            diagnostics=diagnostics,
            actions=_sort_and_cap_actions(actions),
            duration_ms=duration_ms,
            attempt_number=attempt_number,
            metadata=metadata,
            **feedback_kwargs,
        )

    # --- Phase 3: E2E happy-flow integration test ---
    e2e_passed = _run_e2e_happy_flow(
        workspace_root, compose_path, e2e_timeout, diagnostics, actions,
    )

    if not e2e_passed:
        duration_ms = int((time.time() - start_time) * 1000)
        metadata = {"attempt_number": attempt_number}
        if previous_summary:
            metadata["previous_summary"] = previous_summary

        return GateFeedback(
            status=GateStatus.fail,
            diagnostics=diagnostics,
            actions=_sort_and_cap_actions(actions),
            duration_ms=duration_ms,
            attempt_number=attempt_number,
            metadata=metadata,
            **feedback_kwargs,
        )

    # --- All checks passed ---
    duration_ms = int((time.time() - start_time) * 1000)
    metadata = {"attempt_number": attempt_number}
    if previous_summary:
        metadata["previous_summary"] = previous_summary

    feedback = GateFeedback(
        status=GateStatus.pass_,
        diagnostics=diagnostics,
        actions=actions,
        duration_ms=duration_ms,
        attempt_number=attempt_number,
        metadata=metadata,
        **feedback_kwargs,
    )

    return feedback


# ---------------------------------------------------------------------------
# Convenience: run from CLI with spec file
# ---------------------------------------------------------------------------

def validate_runtime_from_cli(
    workspace_root: Path = Path("/workspace"),
    compose_path: Optional[Path] = None,
    skip_up: bool = False,
    e2e_timeout: int = _DEFAULT_E2E_TIMEOUT,
    attempt_number: int = 1,
    previous_summary: Optional[str] = None,
) -> GateFeedback:
    """CLI-friendly entry point for Gate 4.

    Same as validate_runtime but designed for CLI invocation.
    """
    return validate_runtime(
        workspace_root=workspace_root,
        compose_path=compose_path,
        skip_up=skip_up,
        e2e_timeout=e2e_timeout,
        attempt_number=attempt_number,
        previous_summary=previous_summary,
    )
