"""Testbed — Gated AI Testbed system.

A gated architecture for creating, validating, and iterating on AI-generated
testbed specifications. Each gate produces structured, machine-readable feedback
that enables autonomous iteration.

Usage:
  # Via wrapper script (auto-sets PYTHONPATH):
  ./testbed.sh check
  ./testbed.sh init my-testbed
  ./testbed.sh validate my-spec.json

  # Via python module (requires PYTHONPATH):
  PYTHONPATH=/project/tooling python3 -m testbed.cli check
"""

import sys
from pathlib import Path

# Ensure the package is importable when __init__.py is loaded directly
_pkg_root = str(Path(__file__).resolve().parent)
_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from testbed.contracts import TestbedSpec, GateFeedback
from testbed.gates import gate1_spec_parser, gate2_code_validator

__all__ = [
    "TestbedSpec",
    "GateFeedback",
    "gate1_spec_parser",
    "gate2_code_validator",
]
