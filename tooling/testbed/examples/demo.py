#!/usr/bin/env python3
"""
Demonstration: Gated AI Testbed MVP — Success and Failure paths.

This script demonstrates both paths using direct Pydantic validation
(no LLM dependency). It shows:
  1. A valid TestbedSpec passing Gate 1
  2. An invalid TestbedSpec failing Gate 1 with structured feedback
  3. The feedback loop in action (fix → re-validate)
"""

import json
import sys
from pathlib import Path

# Add the testbed package to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from testbed.contracts.spec import TestbedSpec, ServiceSpec, PortMapping, VolumeMount, TestSuite
from testbed.contracts.feedback import GateFeedback, GateStatus, Severity, Diagnostic, Action, ActionKind
from testbed.gates.gate1_spec_parser import parse_spec, _validate_spec, _add_warnings


def print_separator(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def demo_success_path() -> None:
    """Demonstrate a valid spec passing Gate 1."""
    print_separator("DEMO 1: SUCCESS PATH — Valid Spec Passes Gate 1")

    # A well-formed spec (as would be produced by LLM extraction)
    valid_spec_dict = {
        "name": "stablecoin-poc",
        "version": "0.1.0",
        "description": "Full-stack stablecoin POC with Fabric, Besu, and Solana",
        "tags": ["stablecoin", "fabric", "besu", "solana", "blockchain"],
        "services": [
            {
                "name": "postgres",
                "image": "postgres:16-alpine",
                "ports": [{"host": 5432, "container": 5432}],
                "mem_limit": "512M",
                "healthcheck": {"test": ["CMD", "pg_isready"], "interval": "10s"},
                "networks": ["platform-net"],
                "labels": {"project": "scdlt", "managed-by": "testbed"},
            },
            {
                "name": "besu-node",
                "image": "hyperledger/besu:24.1.0",
                "ports": [
                    {"host": 8545, "container": 8545},
                    {"host": 8546, "container": 8546, "protocol": "tcp"},
                ],
                "mem_limit": "1G",
                "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost:8545"], "interval": "30s"},
                "networks": ["platform-net"],
                "depends_on": ["postgres"],
                "labels": {"project": "scdlt", "managed-by": "testbed"},
            },
            {
                "name": "stablecoin-service",
                "image": "stablecoin-service:latest",
                "build": "./src/service",
                "ports": [{"host": 8000, "container": 8000}],
                "mem_limit": "1G",
                "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost:8000/health"], "interval": "15s"},
                "networks": ["platform-net", "fabric-x-net"],
                "depends_on": ["postgres", "besu-node"],
                "environment": {"DATABASE_URL": "postgres://user:pass@postgres:5432/scdlt"},
                "labels": {"project": "scdlt", "managed-by": "testbed"},
            },
        ],
        "test_suites": [
            {
                "name": "integration",
                "path": "scripts/e2e/integration/",
                "framework": "pytest",
                "markers": ["not live"],
                "required_services": ["postgres", "besu-node", "stablecoin-service"],
                "timeout_seconds": 300,
            },
        ],
        "infrastructure": {
            "networks": {
                "platform-net": {"driver": "bridge"},
                "fabric-x-net": {"driver": "bridge"},
            },
        },
        "constraints": {
            "memory_per_service": {
                "postgres": "512M",
                "besu-node": "1G",
                "stablecoin-service": "1G",
            },
            "max_containers": 20,
        },
        "guardrails": {
            "require_mem_limit": True,
            "require_healthcheck": True,
            "no_host_network": True,
            "no_privileged": True,
        },
    }

    # Validate
    validated, diagnostics, actions = _validate_spec(valid_spec_dict)
    _add_warnings(validated, diagnostics)

    if validated:
        print(f"  ✅ Spec VALID: {validated.name} v{validated.version}")
        print(f"     Services: {len(validated.services)}")
        for s in validated.services:
            mem = f" mem={s.mem_limit}" if s.mem_limit else ""
            hc = " ✓hc" if s.healthcheck else ""
            print(f"       • {s.name} ({s.image}){mem}{hc}")
        print(f"     Test Suites: {len(validated.test_suites)}")
        print(f"     Networks: {len(validated.infrastructure.networks)}")
        print(f"     Warnings: {len(diagnostics)}")
        for d in diagnostics:
            print(f"       ⚠️  [{d.code}] {d.message}")
    else:
        print("  ❌ Spec INVALID (unexpected)")


def demo_failure_path() -> None:
    """Demonstrate an invalid spec failing Gate 1 with structured feedback."""
    print_separator("DEMO 2: FAILURE PATH — Invalid Spec Fails Gate 1")

    # A deliberately broken spec
    broken_spec_dict = {
        "name": "broken-testbed",
        "services": [
            {
                # Missing 'image' — required field
                "name": "web-app",
                "ports": [{"host": 8080, "container": 80}],
                # No mem_limit
                # No healthcheck
                # No networks
            },
            {
                "name": "database",
                "image": "postgres:16-alpine",
                "ports": [{"host": 99999, "container": 5432}],  # Invalid port (>65535)
                # No mem_limit
                # No healthcheck
            },
            {
                "name": "web-app",  # Duplicate name!
                "image": "nginx:latest",
            },
        ],
        # No test_suites
        # No infrastructure
        # No guardrails
    }

    # Validate
    validated, diagnostics, actions = _validate_spec(broken_spec_dict)

    if validated:
        print("  ✅ Spec VALID (unexpected — should have failed)")
    else:
        print(f"  ❌ Spec INVALID: {len(diagnostics)} issues found")
        print(f"     {len(actions)} suggested actions")
        print()

        # Group by severity
        for severity in [Severity.critical, Severity.error, Severity.warning]:
            sev_diags = [d for d in diagnostics if d.severity == severity]
            if sev_diags:
                icon = {"critical": "🚨", "error": "❌", "warning": "⚠️"}.get(severity.value, "•")
                print(f"  {icon} {severity.value.upper()} ({len(sev_diags)}):")
                for d in sev_diags:
                    loc = f" [{d.location.field}]" if d.location else ""
                    print(f"       [{d.code}] {d.message}{loc}")
                print()

        print(f"  🔧 Suggested actions:")
        for a in actions:
            print(f"       [{a.kind.value}] {a.description}")
            if a.suggested_value:
                print(f"         → Suggested: {json.dumps(a.suggested_value)}")


def demo_feedback_loop() -> None:
    """Demonstrate the feedback loop: fail → fix → re-validate."""
    print_separator("DEMO 3: FEEDBACK LOOP — Fail → Fix → Re-validate")

    # Round 1: Spec with missing memory limits and healthchecks
    print("  Round 1: Spec with missing memory limits and healthchecks")
    spec_dict = {
        "name": "minimal-testbed",
        "description": "A minimal testbed missing critical fields",
        "services": [
            {
                "name": "api",
                "image": "my-api:latest",
                "ports": [{"host": 8080, "container": 8080}],
                # No mem_limit
                # No healthcheck
            },
            {
                "name": "db",
                "image": "postgres:16-alpine",
                # No mem_limit
                # No healthcheck
            },
        ],
    }

    validated, diagnostics, actions = _validate_spec(spec_dict)
    _add_warnings(validated, diagnostics)

    print(f"     Status: {'PASS' if validated else 'FAIL'}")
    print(f"     Diagnostics: {len(diagnostics)}")
    for d in diagnostics:
        print(f"       [{d.code}] {d.message}")

    # Round 2: Fix the issues
    print("\n  → Agent reads diagnostics, fixes spec...\n")

    fixed_spec_dict = {
        "name": "minimal-testbed",
        "description": "A minimal testbed with proper configuration",
        "tags": ["minimal", "demo"],
        "services": [
            {
                "name": "api",
                "image": "my-api:latest",
                "ports": [{"host": 8080, "container": 8080}],
                "mem_limit": "512M",
                "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost:8080/health"], "interval": "15s"},
                "networks": ["app-net"],
                "labels": {"project": "demo", "managed-by": "testbed"},
            },
            {
                "name": "db",
                "image": "postgres:16-alpine",
                "mem_limit": "512M",
                "healthcheck": {"test": ["CMD", "pg_isready"], "interval": "10s"},
                "networks": ["app-net"],
                "labels": {"project": "demo", "managed-by": "testbed"},
            },
        ],
        "test_suites": [
            {
                "name": "smoke",
                "path": "tests/smoke/",
                "framework": "pytest",
                "required_services": ["api", "db"],
            },
        ],
        "infrastructure": {
            "networks": {
                "app-net": {"driver": "bridge"},
            },
        },
        "guardrails": {
            "require_mem_limit": True,
            "require_healthcheck": True,
        },
    }

    validated, diagnostics, actions = _validate_spec(fixed_spec_dict)
    _add_warnings(validated, diagnostics)

    print("  Round 2: Fixed spec")
    print(f"     Status: {'PASS' if validated else 'FAIL'}")
    if validated:
        print(f"     ✅ Spec VALID: {validated.name} v{validated.version}")
        print(f"     Services: {len(validated.services)}")
        for s in validated.services:
            mem = f" mem={s.mem_limit}" if s.mem_limit else ""
            hc = " ✓hc" if s.healthcheck else ""
            print(f"       • {s.name} ({s.image}){mem}{hc}")
        print(f"     Test Suites: {len(validated.test_suites)}")
        print(f"     Warnings: {len(diagnostics)} (all non-blocking)")
        for d in diagnostics:
            print(f"       [{d.code}] {d.message}")
    else:
        print(f"     Diagnostics: {len(diagnostics)}")
        for d in diagnostics:
            print(f"       [{d.code}] {d.message}")


def demo_gate_feedback_structure() -> None:
    """Show the full GateFeedback structure."""
    print_separator("DEMO 4: GATE FEEDBACK STRUCTURE")

    # Create a realistic GateFeedback
    feedback = GateFeedback(
        gate_id="gate1.spec_parser",
        gate_version="0.1.0",
        status=GateStatus.fail,
        diagnostics=[
            Diagnostic(
                code="E020",
                severity=Severity.critical,
                message="No services defined. A testbed must have at least one service.",
                location={"field": "services"},
            ),
            Diagnostic(
                code="W001",
                severity=Severity.warning,
                message="No test suites defined. Add at least one test suite.",
                location={"field": "test_suites"},
            ),
        ],
        actions=[
            Action(
                kind=ActionKind.add,
                description="Define at least one Docker service with a name and image.",
                target_field="services",
                priority=0,
            ),
            Action(
                kind=ActionKind.add,
                description="Add a test suite to validate the testbed behavior.",
                target_field="test_suites",
                priority=3,
            ),
        ],
        raw_input="# My Testbed\n\nI want a testbed...",
        attempt_number=1,
    )

    print(f"  GateFeedback JSON structure:")
    print(f"  {json.dumps(feedback.model_dump(mode='json', exclude_none=True), indent=2)[:2000]}...")
    print()
    print(f"  Summary: {feedback.summary()}")
    print(f"  Has critical: {feedback.has_critical()}")
    print(f"  Has errors: {feedback.has_errors()}")


def demo_cli_parse() -> None:
    """Demonstrate the CLI parse command with the success spec."""
    print_separator("DEMO 5: CLI PARSE — Success Spec (via parse_spec)")

    spec_path = Path(__file__).resolve().parent / "success_spec.md"
    raw_text = spec_path.read_text()

    spec, feedback = parse_spec(raw_text, use_llm=False)

    print(f"  Gate: {feedback.gate_id} v{feedback.gate_version}")
    print(f"  Status: {feedback.status.value}")
    print(f"  Duration: {feedback.duration_ms}ms")
    print(f"  Diagnostics: {len(feedback.diagnostics)}")
    print(f"  Actions: {len(feedback.actions)}")

    if spec:
        print(f"\n  ✅ Validated Spec: {spec.name}")
        print(f"     Services ({len(spec.services)}):")
        for s in spec.services:
            print(f"       • {s.name} ({s.image})")
    else:
        print("\n  ❌ Spec validation failed")


def demo_kb_aware_feedback() -> None:
    """Demonstrate KB-aware feedback — cross-referencing the knowledgebase."""
    print_separator("DEMO 6: KB-AWARE FEEDBACK — Cross-referencing Knowledgebase")

    # Use the success spec with the scdlt knowledgebase
    spec_path = Path(__file__).resolve().parent / "success_spec.md"
    raw_text = spec_path.read_text()

    kb_dirs = [Path("/workspace/scdlt/knowledgebase")]

    spec, feedback = parse_spec(raw_text, use_llm=False, kb_dirs=kb_dirs)

    print(f"  Gate: {feedback.gate_id} v{feedback.gate_version}")
    print(f"  Status: {feedback.status.value}")
    print(f"  Duration: {feedback.duration_ms}ms")
    print(f"  Diagnostics: {len(feedback.diagnostics)}")
    print(f"  KB directory: /workspace/scdlt/knowledgebase")
    print()

    # Show KB-sourced diagnostics
    kb_diags = [d for d in feedback.diagnostics if d.code.startswith("KB_")]
    print(f"  📚 KB-sourced diagnostics ({len(kb_diags)}):")
    for d in kb_diags:
        print(f"     [{d.code}] {d.message}")
        if d.kb_refs:
            for ref in d.kb_refs:
                print(f"       → {ref.path}")
        if d.detail:
            # Show first 150 chars of snippet
            snippet = d.detail[:150].replace("\n", " ")
            print(f"       Snippet: {snippet}...")
        print()

    if not kb_diags:
        print("  (No KB matches found — the fallback parser produces weak extractions)")
        print("  With LLM extraction, the spec would have proper service names and")
        print("  images, leading to more relevant KB matches.")


if __name__ == "__main__":
    demo_success_path()
    demo_failure_path()
    demo_feedback_loop()
    demo_gate_feedback_structure()
    demo_cli_parse()
    demo_kb_aware_feedback()
