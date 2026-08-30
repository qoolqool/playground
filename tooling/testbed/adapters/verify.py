"""Verify-hook callflow adapter.

For flows that cannot be expressed as a single request/response call: async
events, eventual consistency, DLT state transitions, side effects. The spec
declares the edge with ``expect.mode: verify_hook`` and points at a
project-owned checker script.

Dispatch contract:
    - The checker script is resolved relative to the workspace root.
    - ``.sh`` files run via bash, ``.py`` files via python3, anything else
      executes directly.
    - The edge's JSON is exported to the env var ``CALLFLOW_EDGE_JSON`` and
      passed as the first argument.
    - Exit code 0 means the check passed; anything else and the last line of
      stderr/stdout becomes the failure reason.

The project owns the actual logic; the gate only runs it and reads the verdict.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _resolve_script(workspace_root: Path, hook: str) -> Path:
    p = Path(hook)
    if not p.is_absolute():
        p = workspace_root / p
    return p.resolve()


def _run_script(script: Path, edge_json: str, timeout: int) -> tuple[int, str, str]:
    cmd: list[str]
    suffix = script.suffix.lower()
    if suffix == ".sh":
        cmd = ["bash", str(script)]
    elif suffix == ".py":
        cmd = ["python3", str(script)]
    else:
        cmd = [str(script)]

    env = {**os.environ, "CALLFLOW_EDGE_JSON": edge_json}
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(script.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"verify hook timed out after {timeout}s: {script}"
    except FileNotFoundError:
        return -2, "", f"verify hook not found or not runnable: {script}"
    except OSError as exc:
        return -3, "", f"OS error running verify hook: {exc}"


def run(edge, target_service, base_host, workspace_root, timeout=60):
    """Execute the edge via its project-owned verify hook. Never raises."""
    from testbed.adapters import AdapterResult

    hook = edge.expect.verify_hook
    if not hook:
        return AdapterResult(
            passed=False,
            error=(
                f"edge '{edge.id}' uses verify_hook mode but no "
                f"'expect.verify_hook' path was declared"
            ),
        )

    script = _resolve_script(Path(workspace_root), hook)
    edge_json = json.dumps(
        edge.model_dump(mode="json"),
        sort_keys=True,
        default=str,
    )

    rc, stdout, stderr = _run_script(script, edge_json, timeout)

    if rc != 0:
        tail = (stderr.strip() or stdout.strip()).splitlines()
        reason = tail[-1] if tail else f"exit code {rc}"
        return AdapterResult(
            passed=False,
            actual={"exit_code": rc, "stdout": stdout, "stderr": stderr},
            error=f"verify hook '{hook}' failed: {reason}",
        )

    return AdapterResult(
        passed=True,
        actual={"exit_code": 0, "stdout": stdout, "stderr": stderr},
        error=None,
    )
