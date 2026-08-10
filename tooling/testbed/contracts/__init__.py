"""Shared contracts for the Gated AI Testbed system.

All gates produce and consume these types, ensuring a consistent
machine-readable feedback loop across the entire pipeline.
"""

from .spec import TestbedSpec, ServiceSpec, TestSuite, InfrastructureSpec, ConstraintSpec, GuardrailSpec
from .feedback import (
    GateFeedback,
    GateStatus,
    Location,
    Severity,
    Diagnostic,
    KBRef,
    Action,
    ActionKind,
)

__all__ = [
    "TestbedSpec",
    "ServiceSpec",
    "TestSuite",
    "InfrastructureSpec",
    "ConstraintSpec",
    "GuardrailSpec",
    "GateFeedback",
    "GateStatus",
    "Location",
    "Severity",
    "Diagnostic",
    "Action",
    "ActionKind",
]
