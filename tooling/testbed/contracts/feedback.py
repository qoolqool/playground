"""
GateFeedback — structured, machine-readable feedback from any gate.

Every gate in the pipeline produces a GateFeedback object. This allows:
- Agents to programmatically iterate on failures
- Downstream gates to understand upstream issues
- Humans to quickly grasp what went wrong and why
- The system to track lineage across attempts
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GateStatus(str, Enum):
    """Overall status of a gate evaluation."""
    pass_ = "pass"  # 'pass' is a Python keyword, use trailing underscore
    fail = "fail"
    error = "error"  # Gate itself crashed or had an internal error
    skip = "skip"    # Gate was skipped (e.g. preconditions not met)


class Severity(str, Enum):
    """Severity of a diagnostic issue."""
    critical = "critical"   # Blocks the pipeline entirely
    error = "error"         # Must be fixed before proceeding
    warning = "warning"     # Should be fixed, but doesn't block
    info = "info"           # Informational, no action required
    suggestion = "suggestion"  # Optional improvement


class ActionKind(str, Enum):
    """Category of suggested action."""
    fix = "fix"                    # Direct fix (e.g. "set mem_limit to 512M")
    clarify = "clarify"            # Need more information from user
    restructure = "restructure"    # Reorganize the spec
    add = "add"                    # Add missing component
    remove = "remove"              # Remove problematic component
    research = "research"          # Need to look up something
    retry = "retry"                # Retry with different parameters


# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------

class Location(BaseModel):
    """Points to exactly where an issue was found."""
    field: str = Field(..., description="Dotted field path (e.g. 'services[0].image')")
    line: Optional[int] = Field(None, description="Line number in source text")
    column: Optional[int] = Field(None, description="Column number in source text")
    source: Optional[str] = Field(
        None,
        description="Source identifier (e.g. 'user_spec.md', 'docker-compose.yml')",
    )


class KBRef(BaseModel):
    """Reference to a knowledgebase entry relevant to this diagnostic."""
    path: str = Field(..., description="Relative path to the KB entry (e.g. 'gotchas/network-mode-service-cross-compose.md')")
    title: str = Field(..., description="Title of the KB entry")
    snippet: Optional[str] = Field(None, description="Key excerpt from the entry")
    category: str = Field("gotcha", description="KB category: gotcha, pattern, decision, fact")


class Diagnostic(BaseModel):
    """A single issue found during gate evaluation."""
    code: str = Field(
        ...,
        description="Machine-readable error code (e.g. 'E001', 'W042')",
    )
    severity: Severity = Field(
        Severity.error,
        description="How serious this issue is",
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Human-readable description of the issue",
    )
    location: Optional[Location] = Field(
        None,
        description="Where the issue was found",
    )
    detail: Optional[str] = Field(
        None,
        description="Additional context (e.g. actual vs expected value)",
    )
    rule: Optional[str] = Field(
        None,
        description="Name of the validation rule that was violated",
    )
    kb_refs: list[KBRef] = Field(
        default_factory=list,
        description="Knowledgebase entries relevant to this diagnostic",
    )


class Action(BaseModel):
    """A suggested action to resolve a diagnostic."""
    kind: ActionKind = Field(..., description="Category of action")
    description: str = Field(
        ...,
        min_length=1,
        description="What to do, in natural language",
    )
    target_field: Optional[str] = Field(
        None,
        description="Which field this action applies to",
    )
    suggested_value: Optional[Any] = Field(
        None,
        description="Suggested new value for the field",
    )
    priority: int = Field(
        0,
        ge=0,
        le=10,
        description="Priority (0=urgent, 10=optional)",
    )


# ---------------------------------------------------------------------------
# Main feedback type
# ---------------------------------------------------------------------------

class GateFeedback(BaseModel):
    """Structured feedback from a single gate evaluation.

    This is the universal feedback contract. Every gate produces one of these,
    and the agent (or orchestrator) uses it to decide what to do next.
    """
    # Gate identification
    gate_id: str = Field(
        ...,
        description="Which gate produced this feedback (e.g. 'gate1.spec_parser')",
    )
    gate_version: str = Field(
        "0.1.0",
        description="Version of the gate that produced this feedback",
    )

    # Status
    status: GateStatus = Field(
        ...,
        description="Overall result of the gate evaluation",
    )

    # Diagnostics
    diagnostics: list[Diagnostic] = Field(
        default_factory=list,
        description="Issues found during evaluation, ordered by severity",
    )

    # Suggested actions
    actions: list[Action] = Field(
        default_factory=list,
        description="Suggested actions to resolve issues, ordered by priority",
    )

    # Spec snapshot (what was evaluated)
    spec_snapshot: Optional[dict[str, Any]] = Field(
        None,
        description="The TestbedSpec (or partial spec) at time of evaluation",
    )

    # Raw input
    raw_input: Optional[str] = Field(
        None,
        description="The raw input text that was evaluated",
    )

    # Timing
    evaluated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of evaluation",
    )
    duration_ms: Optional[int] = Field(
        None,
        description="How long the evaluation took, in milliseconds",
    )

    # Lineage
    attempt_number: int = Field(
        1,
        ge=1,
        description="Which attempt this is (for tracking iteration)",
    )
    parent_feedback_id: Optional[str] = Field(
        None,
        description="ID of the feedback that triggered this evaluation",
    )

    # Extensibility
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional data",
    )

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def ok(
        cls,
        gate_id: str,
        spec_snapshot: Optional[dict[str, Any]] = None,
        raw_input: Optional[str] = None,
        **kwargs,
    ) -> "GateFeedback":
        """Create a passing feedback with no diagnostics."""
        return cls(
            gate_id=gate_id,
            status=GateStatus.pass_,
            spec_snapshot=spec_snapshot,
            raw_input=raw_input,
            **kwargs,
        )

    @classmethod
    def fail(
        cls,
        gate_id: str,
        diagnostics: list[Diagnostic],
        actions: Optional[list[Action]] = None,
        spec_snapshot: Optional[dict[str, Any]] = None,
        raw_input: Optional[str] = None,
        **kwargs,
    ) -> "GateFeedback":
        """Create a failing feedback with diagnostics and actions."""
        return cls(
            gate_id=gate_id,
            status=GateStatus.fail,
            diagnostics=diagnostics,
            actions=actions or [],
            spec_snapshot=spec_snapshot,
            raw_input=raw_input,
            **kwargs,
        )

    @classmethod
    def error(
        cls,
        gate_id: str,
        message: str,
        detail: Optional[str] = None,
        **kwargs,
    ) -> "GateFeedback":
        """Create an error feedback (gate itself crashed)."""
        return cls(
            gate_id=gate_id,
            status=GateStatus.error,
            diagnostics=[
                Diagnostic(
                    code="GATE_CRASH",
                    severity=Severity.critical,
                    message=message,
                    detail=detail,
                )
            ],
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_pass(self) -> bool:
        return self.status == GateStatus.pass_

    def is_fail(self) -> bool:
        return self.status == GateStatus.fail

    def is_error(self) -> bool:
        return self.status == GateStatus.error

    def has_critical(self) -> bool:
        return any(d.severity == Severity.critical for d in self.diagnostics)

    def has_errors(self) -> bool:
        return any(d.severity in (Severity.critical, Severity.error) for d in self.diagnostics)

    def by_severity(self, severity: Severity) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == severity]

    def summary(self) -> str:
        """Return a one-line summary of this feedback."""
        n_diag = len(self.diagnostics)
        n_actions = len(self.actions)
        return (
            f"[{self.gate_id}] status={self.status.value} "
            f"diagnostics={n_diag} actions={n_actions} "
            f"attempt={self.attempt_number}"
        )
