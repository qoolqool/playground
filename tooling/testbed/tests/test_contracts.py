"""Tests for the Gated AI Testbed MVP contracts and Gate 1."""

import json
import sys
from pathlib import Path

# Add the parent of testbed/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from pydantic import ValidationError

from testbed.contracts.spec import (
    TestbedSpec,
    ServiceSpec,
    PortMapping,
    VolumeMount,
    TestSuite,
    InfrastructureSpec,
    ConstraintSpec,
    GuardrailSpec,
    NetworkMode,
    RestartPolicy,
    TestFramework,
)
from testbed.contracts.feedback import (
    GateFeedback,
    GateStatus,
    Severity,
    Diagnostic,
    Action,
    ActionKind,
    Location,
)
from testbed.gates.gate1_spec_parser import parse_spec, _validate_spec, _add_warnings


# =========================================================================
# TestbedSpec tests
# =========================================================================

class TestTestbedSpec:
    """Tests for the TestbedSpec model."""

    def test_minimal_valid_spec(self):
        """A spec with just name and one service should validate."""
        spec = TestbedSpec(
            name="test-testbed",
            services=[ServiceSpec(name="web", image="nginx:latest")],
        )
        assert spec.name == "test-testbed"
        assert spec.version == "0.1.0"
        assert len(spec.services) == 1
        assert spec.services[0].name == "web"
        assert spec.services[0].image == "nginx:latest"

    def test_full_spec(self):
        """A fully populated spec should validate."""
        spec = TestbedSpec(
            name="full-testbed",
            version="1.0.0",
            description="A full testbed",
            tags=["demo", "test"],
            services=[
                ServiceSpec(
                    name="api",
                    image="my-api:latest",
                    build="./src/api",
                    ports=[PortMapping(host=8080, container=8080)],
                    volumes=[VolumeMount(source="data", target="/data", mode="rw")],
                    environment={"DB_URL": "postgres://localhost/db"},
                    networks=["app-net"],
                    depends_on=["db"],
                    mem_limit="512M",
                    cpus=1.0,
                    restart=RestartPolicy.always,
                    healthcheck={"test": ["CMD", "curl", "-f", "http://localhost"]},
                    network_mode=NetworkMode.custom,
                    labels={"project": "test"},
                    extra_hosts=["host.docker.internal:host-gateway"],
                ),
                ServiceSpec(
                    name="db",
                    image="postgres:16-alpine",
                    mem_limit="1G",
                    healthcheck={"test": ["CMD", "pg_isready"]},
                ),
            ],
            test_suites=[
                TestSuite(
                    name="integration",
                    path="tests/integration/",
                    framework=TestFramework.pytest,
                    markers=["not slow"],
                    env={"CI": "true"},
                    timeout_seconds=600,
                    required_services=["api", "db"],
                    tags=["critical"],
                ),
            ],
            infrastructure=InfrastructureSpec(
                networks={"app-net": {"driver": "bridge"}},
                volumes={"data": {}},
            ),
            constraints=ConstraintSpec(
                memory_per_service={"api": "512M", "db": "1G"},
                max_containers=10,
            ),
            guardrails=GuardrailSpec(
                require_mem_limit=True,
                require_healthcheck=True,
                no_host_network=True,
            ),
        )
        assert spec.name == "full-testbed"
        assert len(spec.services) == 2
        assert len(spec.test_suites) == 1
        assert "app-net" in spec.infrastructure.networks

    def test_duplicate_service_names_fails(self):
        """Duplicate service names should raise ValidationError."""
        with pytest.raises(ValidationError, match="Duplicate service names"):
            TestbedSpec(
                name="dup-test",
                services=[
                    ServiceSpec(name="web", image="nginx:latest"),
                    ServiceSpec(name="web", image="httpd:latest"),
                ],
            )

    def test_depends_on_nonexistent_service_fails(self):
        """depends_on referencing a non-existent service should fail."""
        with pytest.raises(ValidationError, match="depends on 'db'"):
            TestbedSpec(
                name="dep-test",
                services=[
                    ServiceSpec(name="web", image="nginx:latest", depends_on=["db"]),
                ],
            )

    def test_test_suite_requires_nonexistent_service_fails(self):
        """Test suite requiring a non-existent service should fail."""
        with pytest.raises(ValidationError, match="requires service 'redis'"):
            TestbedSpec(
                name="suite-test",
                services=[
                    ServiceSpec(name="web", image="nginx:latest"),
                ],
                test_suites=[
                    TestSuite(
                        name="smoke",
                        path="tests/",
                        required_services=["redis"],
                    ),
                ],
            )

    def test_invalid_mem_limit_format_fails(self):
        """Invalid memory limit format should fail."""
        with pytest.raises(ValidationError):
            ServiceSpec(name="web", image="nginx:latest", mem_limit="not-a-limit")

    def test_port_out_of_range_fails(self):
        """Port number > 65535 should fail."""
        with pytest.raises(ValidationError):
            PortMapping(host=99999, container=80)

    def test_service_names_convenience(self):
        """service_names() and get_service() should work."""
        spec = TestbedSpec(
            name="test",
            services=[
                ServiceSpec(name="web", image="nginx:latest"),
                ServiceSpec(name="db", image="postgres:16-alpine"),
            ],
        )
        assert spec.service_names() == ["web", "db"]
        assert spec.get_service("web") is not None
        assert spec.get_service("web").name == "web"
        assert spec.get_service("redis") is None

    def test_serialize_roundtrip(self):
        """Spec should survive JSON serialize/deserialize roundtrip."""
        spec = TestbedSpec(
            name="roundtrip",
            services=[ServiceSpec(name="web", image="nginx:latest")],
        )
        data = json.loads(spec.model_dump_json())
        restored = TestbedSpec(**data)
        assert restored.name == spec.name
        assert restored.services[0].name == spec.services[0].name


# =========================================================================
# GateFeedback tests
# =========================================================================

class TestGateFeedback:
    """Tests for the GateFeedback model."""

    def test_ok_factory(self):
        """GateFeedback.ok() should create a passing feedback."""
        fb = GateFeedback.ok(gate_id="gate1.test")
        assert fb.status == GateStatus.pass_
        assert fb.is_pass()
        assert len(fb.diagnostics) == 0

    def test_fail_factory(self):
        """GateFeedback.fail() should create a failing feedback with diagnostics."""
        fb = GateFeedback.fail(
            gate_id="gate1.test",
            diagnostics=[
                Diagnostic(code="E001", severity=Severity.error, message="Something wrong"),
            ],
            actions=[Action(kind=ActionKind.fix, description="Fix it")],
        )
        assert fb.status == GateStatus.fail
        assert fb.is_fail()
        assert len(fb.diagnostics) == 1
        assert len(fb.actions) == 1

    def test_error_factory(self):
        """GateFeedback.error() should create an error feedback."""
        fb = GateFeedback.error(gate_id="gate1.test", message="Gate crashed")
        assert fb.status == GateStatus.error
        assert fb.is_error()
        assert fb.diagnostics[0].code == "GATE_CRASH"

    def test_severity_helpers(self):
        """has_critical() and has_errors() should work correctly."""
        fb = GateFeedback(
            gate_id="test",
            status=GateStatus.fail,
            diagnostics=[
                Diagnostic(code="C001", severity=Severity.critical, message="Critical"),
                Diagnostic(code="E001", severity=Severity.error, message="Error"),
                Diagnostic(code="W001", severity=Severity.warning, message="Warning"),
            ],
        )
        assert fb.has_critical()
        assert fb.has_errors()

    def test_by_severity(self):
        """by_severity() should filter correctly."""
        fb = GateFeedback(
            gate_id="test",
            status=GateStatus.fail,
            diagnostics=[
                Diagnostic(code="E001", severity=Severity.error, message="Err1"),
                Diagnostic(code="W001", severity=Severity.warning, message="Warn1"),
                Diagnostic(code="E002", severity=Severity.error, message="Err2"),
            ],
        )
        errors = fb.by_severity(Severity.error)
        assert len(errors) == 2
        warnings = fb.by_severity(Severity.warning)
        assert len(warnings) == 1

    def test_summary(self):
        """summary() should return a one-line string."""
        fb = GateFeedback.ok(gate_id="gate1.test")
        summary = fb.summary()
        assert "gate1.test" in summary
        assert "pass" in summary

    def test_timestamp_auto_generated(self):
        """evaluated_at should be auto-generated."""
        fb = GateFeedback.ok(gate_id="test")
        assert fb.evaluated_at is not None
        assert "T" in fb.evaluated_at  # ISO 8601 format


# =========================================================================
# Gate 1: Spec Parser tests
# =========================================================================

class TestGate1SpecParser:
    """Tests for Gate 1 — Spec Parser."""

    def test_parse_valid_spec_dict(self):
        """A valid spec dict should pass validation."""
        spec_dict = {
            "name": "test-testbed",
            "services": [
                {"name": "web", "image": "nginx:latest", "mem_limit": "512M"},
            ],
            "test_suites": [
                {"name": "smoke", "path": "tests/"},
            ],
        }
        validated, diagnostics, actions = _validate_spec(spec_dict)
        _add_warnings(validated, diagnostics, actions)
        assert validated is not None
        assert validated.name == "test-testbed"

    def test_parse_empty_services_fails(self):
        """A spec with no services should fail with critical diagnostic."""
        spec_dict = {"name": "empty", "services": []}
        validated, diagnostics, actions = _validate_spec(spec_dict)
        assert validated is None
        assert any(d.code == "E020" for d in diagnostics)
        assert any(d.severity == Severity.critical for d in diagnostics)

    def test_parse_missing_service_image(self):
        """A service missing 'image' should produce a diagnostic."""
        spec_dict = {
            "name": "missing-image",
            "services": [{"name": "web"}],
        }
        validated, diagnostics, actions = _validate_spec(spec_dict)
        assert validated is None
        assert any(d.code == "E010" for d in diagnostics)

    def test_parse_with_warnings(self):
        """A valid spec with missing optional fields should produce warnings."""
        spec_dict = {
            "name": "minimal",
            "services": [
                {"name": "web", "image": "nginx:latest"},
            ],
        }
        validated, diagnostics, actions = _validate_spec(spec_dict)
        _add_warnings(validated, diagnostics, actions)
        assert validated is not None
        warning_codes = {d.code for d in diagnostics}
        assert "W001" in warning_codes  # No test suites
        assert "W002" in warning_codes  # No memory limits
        assert "W003" in warning_codes  # No healthchecks

    def test_parse_spec_no_llm_fallback(self):
        """parse_spec with use_llm=False should use keyword fallback."""
        spec, feedback = parse_spec("# Test\n\nA simple testbed", use_llm=False)
        # The fallback produces a spec (even if weak)
        assert feedback.gate_id == "gate1.spec_parser"
        assert feedback.status in (GateStatus.pass_, GateStatus.fail)

    def test_parse_spec_with_llm_fallback(self):
        """parse_spec with use_llm=True should fall back when Ollama is down."""
        spec, feedback = parse_spec("# Test\n\nA simple testbed", use_llm=True, timeout_seconds=2)
        # Should fall back to keyword parser since Ollama has no models
        assert feedback.gate_id == "gate1.spec_parser"

    def test_duplicate_service_name_in_validation(self):
        """Duplicate service names should be caught by model validator."""
        spec_dict = {
            "name": "dup-test",
            "services": [
                {"name": "web", "image": "nginx:latest"},
                {"name": "web", "image": "httpd:latest"},
            ],
        }
        validated, diagnostics, actions = _validate_spec(spec_dict)
        assert validated is None
        assert any("Duplicate" in d.message for d in diagnostics)

    def test_bad_depends_on(self):
        """depends_on referencing non-existent service should be caught."""
        spec_dict = {
            "name": "bad-dep",
            "services": [
                {"name": "web", "image": "nginx:latest", "depends_on": ["db"]},
            ],
        }
        validated, diagnostics, actions = _validate_spec(spec_dict)
        assert validated is None
        assert any("depends on" in d.message for d in diagnostics)


# =========================================================================
# Integration: CLI roundtrip
# =========================================================================

class TestCLIIntegration:
    """Integration tests for the CLI."""

    def test_cli_parse_success(self):
        """CLI parse should produce a feedback JSON file."""
        import subprocess
        testbed_root = str(Path(__file__).resolve().parent.parent.parent)
        result = subprocess.run(
            [
                sys.executable, "-m", "testbed.cli", "parse",
                str(Path(__file__).resolve().parent.parent / "examples" / "success_spec.md"),
                "--no-llm", "-o", "/tmp/test_cli_feedback.json",
            ],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env={**__import__('os').environ, "PYTHONPATH": testbed_root},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        feedback_path = Path("/tmp/test_cli_feedback.json")
        assert feedback_path.exists()
        data = json.loads(feedback_path.read_text())
        assert data["gate_id"] == "gate1.spec_parser"
        assert data["status"] in ("pass", "fail")

    def test_cli_feedback_pretty_print(self):
        """CLI feedback should pretty-print a feedback JSON."""
        import subprocess
        import os
        testbed_root = str(Path(__file__).resolve().parent.parent.parent)
        # First create a feedback file
        fb = GateFeedback.ok(gate_id="gate1.test")
        fb_path = Path("/tmp/test_pretty_feedback.json")
        fb_path.write_text(fb.model_dump_json(indent=2))

        result = subprocess.run(
            [sys.executable, "-m", "testbed.cli", "feedback", str(fb_path)],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ, "PYTHONPATH": testbed_root},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "gate1.test" in result.stdout

    def test_cli_example_success(self):
        """CLI example success should show the success spec."""
        import subprocess
        import os
        testbed_root = str(Path(__file__).resolve().parent.parent.parent)
        result = subprocess.run(
            [sys.executable, "-m", "testbed.cli", "example", "success"],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ, "PYTHONPATH": testbed_root},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Stablecoin POC" in result.stdout

    def test_cli_example_failure(self):
        """CLI example failure should show the failure spec."""
        import subprocess
        import os
        testbed_root = str(Path(__file__).resolve().parent.parent.parent)
        result = subprocess.run(
            [sys.executable, "-m", "testbed.cli", "example", "failure"],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parent.parent,
            env={**os.environ, "PYTHONPATH": testbed_root},
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "My Testbed" in result.stdout
