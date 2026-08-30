"""Callflow adapters.

Each adapter knows HOW to make one protocol-specific inter-component call
and compare the result against the edge's expected outcome. The static spec
declares WHAT should happen (declare, don't execute); the adapter executes it.

Dispatch is by the edge's ``protocol`` field. Adding support for a new app
type means registering a new adapter here, never changing the spec schema
or the Gate 4 phase.
"""

from __future__ import annotations

from typing import Any, Optional

# Built-in adapter protocols. New protocols register here.
_REGISTRY = {
    "http": "testbed.adapters.http",
    "verify-hook": "testbed.adapters.verify",
}


class AdapterResult:
    """Outcome of one adapter call attempt."""

    def __init__(
        self,
        passed: bool,
        actual: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> None:
        self.passed = passed
        self.actual = actual
        self.error = error

    def __repr__(self) -> str:
        return (
            f"AdapterResult(passed={self.passed}, "
            f"actual={self.actual!r}, error={self.error!r})"
        )


def known_protocols() -> list[str]:
    """Return the list of registered adapter protocols."""
    return sorted(_REGISTRY)


def _load_adapter(protocol: str):
    """Dynamically import an adapter module."""
    module_name = _REGISTRY.get(protocol)
    if module_name is None:
        return None
    import importlib

    return importlib.import_module(module_name)


def run_edge(
    edge: Any,
    target_service: Any,
    base_host: str,
    workspace_root: Any,
    timeout: Optional[int] = None,
) -> AdapterResult:
    """Execute one callflow edge via its protocol adapter.

    Args:
        edge: The ContractEdge to execute.
        target_service: The ServiceSpec of the target (for port resolution).
        base_host: Host where published ports are reachable.
        workspace_root: Workspace root, for verify hooks and relative resolution.
        timeout: Optional timeout override (seconds).

    Returns:
        AdapterResult with passed, actual, and error fields.
    """
    protocol = getattr(edge, "protocol", "http")
    adapter = _load_adapter(protocol)
    if adapter is None:
        return AdapterResult(
            passed=False,
            error=(
                f"No adapter registered for callflow protocol '{protocol}'. "
                f"Known protocols: {known_protocols()}"
            ),
        )
    timeout = timeout or 15
    return adapter.run(
        edge=edge,
        target_service=target_service,
        base_host=base_host,
        workspace_root=workspace_root,
        timeout=timeout,
    )
