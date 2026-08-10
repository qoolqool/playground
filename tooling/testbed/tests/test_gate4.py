"""Tests for Gate 4 — Runtime & Integration Verification.

Tests cover:
- Unit tests for helper functions (_truncate_output, _resolve_compose_path, etc.)
- Lifecycle / readiness (stack up, stack down, skip-up)
- Verify gate (pass, fail, per-service unhealthy)
- E2E happy-flow test (pass, fail, file not found)
- Error handling (missing compose, missing bootstrap, command errors)
- Edge cases (empty workspace, timeout)
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the parent of testbed/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from testbed.contracts.feedback import GateStatus, Severity
from testbed.gates.gate4_runtime import (
    validate_runtime,
    validate_runtime_from_cli,
    _truncate_output,
    _resolve_compose_path,
    _get_expected_container_count,
    _get_expected_container_names,
    _EXPECTED_CONTAINERS,
    _MAX_OUTPUT_LINES,
)


# =========================================================================
# Helpers
# =========================================================================

def _create_spec_file(tmp_path: Path, service_count: int = 3):
    """Create a spec JSON file with the given number of services."""
    spec = tmp_path / "quic-edge-v2-spec.json"
    services = [
        {"name": f"svc{i}", "image": f"img{i}:latest"}
        for i in range(service_count)
    ]
    spec.write_text(json.dumps({"services": services}))
    return spec


def _make_mock_run(
    compose_ps_output: str = "",
    compose_ps_rc: int = 0,
    compose_ps_stderr: str = "",
    bootstrap_up_rc: int = 0,
    bootstrap_up_stdout: str = "",
    bootstrap_up_stderr: str = "",
    bootstrap_verify_rc: int = 0,
    bootstrap_verify_stdout: str = "",
    bootstrap_verify_stderr: str = "",
    e2e_rc: int = 0,
    e2e_stdout: str = "",
    e2e_stderr: str = "",
):
    """Create a mock subprocess.run that returns different results based on command."""
    def mock_run(cmd, *args, **kwargs):
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

        if "ps" in cmd_str and "--format" in cmd_str:
            return MagicMock(
                returncode=compose_ps_rc,
                stdout=compose_ps_output,
                stderr=compose_ps_stderr,
            )
        elif "bootstrap.sh" in cmd_str and "up" in cmd_str:
            return MagicMock(
                returncode=bootstrap_up_rc,
                stdout=bootstrap_up_stdout,
                stderr=bootstrap_up_stderr,
            )
        elif "bootstrap.sh" in cmd_str and "verify" in cmd_str:
            return MagicMock(
                returncode=bootstrap_verify_rc,
                stdout=bootstrap_verify_stdout,
                stderr=bootstrap_verify_stderr,
            )
        elif "pytest" in cmd_str and "happy_flow" in cmd_str:
            return MagicMock(
                returncode=e2e_rc,
                stdout=e2e_stdout,
                stderr=e2e_stderr,
            )
        else:
            return MagicMock(returncode=0, stdout="", stderr="")

    return mock_run


def _setup_basic_env(tmp_path, service_count=3):
    """Set up compose file, bootstrap script, and spec file."""
    compose = tmp_path / "deploy" / "compose"
    compose.mkdir(parents=True)
    compose_file = compose / "root.yml"
    compose_file.write_text("services: {}\n")

    bootstrap = tmp_path / "scripts"
    bootstrap.mkdir()
    (bootstrap / "bootstrap.sh").write_text("#!/bin/bash\necho 'mock'")

    _create_spec_file(tmp_path, service_count)
    return compose_file


# =========================================================================
# Unit tests: helper functions
# =========================================================================

class TestTruncateOutput:
    def test_short_output(self):
        text = "line1\nline2\nline3"
        assert _truncate_output(text, max_lines=10) == text

    def test_long_output_truncated(self):
        lines = [f"line{i}" for i in range(100)]
        text = "\n".join(lines)
        result = _truncate_output(text, max_lines=10)
        assert "..." in result
        assert result.count("\n") <= 12  # 5 head + 1 ellipsis + 5 tail + trailing

    def test_exact_max_lines(self):
        lines = [f"line{i}" for i in range(10)]
        text = "\n".join(lines)
        assert _truncate_output(text, max_lines=10) == text

    def test_empty_output(self):
        assert _truncate_output("", max_lines=10) == ""

    def test_single_line(self):
        assert _truncate_output("hello", max_lines=10) == "hello"


class TestResolveComposePath:
    def test_finds_root_yml(self, tmp_path):
        compose = tmp_path / "deploy" / "compose"
        compose.mkdir(parents=True)
        (compose / "root.yml").write_text("services: {}")
        result = _resolve_compose_path(tmp_path)
        assert result == compose / "root.yml"

    def test_finds_docker_compose_yml(self, tmp_path):
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("services: {}")
        result = _resolve_compose_path(tmp_path)
        assert result == compose

    def test_finds_compose_yml(self, tmp_path):
        compose = tmp_path / "compose.yml"
        compose.write_text("services: {}")
        result = _resolve_compose_path(tmp_path)
        assert result == compose

    def test_no_compose_file(self, tmp_path):
        result = _resolve_compose_path(tmp_path)
        assert result is None

    def test_prefers_deploy_compose_root(self, tmp_path):
        """deploy/compose/root.yml should be preferred over docker-compose.yml."""
        deploy_compose = tmp_path / "deploy" / "compose"
        deploy_compose.mkdir(parents=True)
        (deploy_compose / "root.yml").write_text("services: {}")
        (tmp_path / "docker-compose.yml").write_text("services: {}")
        result = _resolve_compose_path(tmp_path)
        assert result == deploy_compose / "root.yml"


class TestGetExpectedContainerCount:
    def test_from_spec(self, tmp_path):
        spec = tmp_path / "quic-edge-v2-spec.json"
        spec.write_text(json.dumps({
            "services": [
                {"name": "svc1", "image": "img1"},
                {"name": "svc2", "image": "img2"},
                {"name": "svc3", "image": "img3"},
            ],
        }))
        assert _get_expected_container_count(tmp_path) == 3

    def test_fallback_to_default(self, tmp_path):
        assert _get_expected_container_count(tmp_path) == len(_EXPECTED_CONTAINERS)

    def test_invalid_spec_falls_back(self, tmp_path):
        spec = tmp_path / "quic-edge-v2-spec.json"
        spec.write_text("not json")
        assert _get_expected_container_count(tmp_path) == len(_EXPECTED_CONTAINERS)


class TestGetExpectedContainerNames:
    def test_from_spec(self, tmp_path):
        spec = tmp_path / "quic-edge-v2-spec.json"
        spec.write_text(json.dumps({
            "services": [
                {"name": "svc1", "image": "img1"},
                {"name": "svc2", "image": "img2"},
            ],
        }))
        assert _get_expected_container_names(tmp_path) == ["svc1", "svc2"]

    def test_fallback_to_default(self, tmp_path):
        assert _get_expected_container_names(tmp_path) == _EXPECTED_CONTAINERS

    def test_skips_services_without_name(self, tmp_path):
        spec = tmp_path / "quic-edge-v2-spec.json"
        spec.write_text(json.dumps({
            "services": [
                {"name": "svc1", "image": "img1"},
                {"image": "img2"},  # no name
            ],
        }))
        assert _get_expected_container_names(tmp_path) == ["svc1"]


# =========================================================================
# Integration tests: validate_runtime with mocked subprocess
# =========================================================================

class TestValidateRuntime:
    def test_all_checks_pass(self, tmp_path):
        """All checks passing should return pass status."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        e2e_dir = tmp_path / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)
        (e2e_dir / "test_wired_01_happy_flow.py").write_text("# mock test")

        mock_run = _make_mock_run(
            compose_ps_output="svc0\nsvc1\nsvc2\n",
            bootstrap_verify_rc=0,
            bootstrap_verify_stdout="=== All verification gates PASS ===",
            e2e_rc=0,
            e2e_stdout="1 passed",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        assert feedback.status == GateStatus.pass_, (
            f"Expected pass, got {feedback.status}: {[d.message for d in feedback.diagnostics]}"
        )
        assert feedback.gate_id == "gate4.runtime"
        assert feedback.attempt_number == 1

    def test_stack_not_running_skip_up(self, tmp_path):
        """Stack not running with --skip-up should fail with G4_STACK_NOT_RUNNING."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        mock_run = _make_mock_run(
            compose_ps_output="",  # No containers running
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=True,
            )

        assert feedback.status == GateStatus.fail
        assert any(d.code == "G4_STACK_NOT_RUNNING" for d in feedback.diagnostics)

    def test_bootstrap_up_fails(self, tmp_path):
        """bootstrap.sh up failing should return G4_BOOTSTRAP_FAILED."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        mock_run = _make_mock_run(
            compose_ps_output="",  # No containers running
            bootstrap_up_rc=1,
            bootstrap_up_stderr="Error: failed to start",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        assert feedback.status == GateStatus.fail
        assert any(d.code == "G4_BOOTSTRAP_FAILED" for d in feedback.diagnostics)

    def test_verify_fails_with_unhealthy_services(self, tmp_path):
        """Verify failure should report per-service unhealthy diagnostics."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        mock_run = _make_mock_run(
            compose_ps_output="svc0\nsvc1\nsvc2\n",
            bootstrap_verify_rc=1,
            bootstrap_verify_stdout=(
                "--- Checking service status ---\n"
                "  Running containers: 3\n"
                "--- Checking health ---\n"
                "  OK: quic-edge-proxy health=healthy\n"
                "  FAIL: caddy health=unhealthy\n"
                "  FAIL: mock-payment-api health=starting\n"
                "--- Checking networks ---\n"
                "  OK: edge-net exists\n"
                "=== 2 verification gate(s) FAILED ===\n"
            ),
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        assert feedback.status == GateStatus.fail
        assert any(d.code == "G4_VERIFY_FAILED" for d in feedback.diagnostics)
        # Should have per-service unhealthy diagnostics
        unhealthy_diags = [d for d in feedback.diagnostics if d.code == "G4_SERVICE_UNHEALTHY"]
        assert len(unhealthy_diags) >= 2

    def test_e2e_test_fails(self, tmp_path):
        """E2E happy-flow test failure should return G4_E2E_TEST_FAILED."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        e2e_dir = tmp_path / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)
        (e2e_dir / "test_wired_01_happy_flow.py").write_text("# mock test")

        mock_run = _make_mock_run(
            compose_ps_output="svc0\nsvc1\nsvc2\n",
            bootstrap_verify_rc=0,
            bootstrap_verify_stdout="=== All verification gates PASS ===",
            e2e_rc=1,
            e2e_stdout="FAILED tests/e2e/test_wired_01_happy_flow.py::test_quic_edge_happy_flow_live",
            e2e_stderr="AssertionError: Soft assertions failed",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        assert feedback.status == GateStatus.fail
        assert any(d.code == "G4_E2E_TEST_FAILED" for d in feedback.diagnostics)

    def test_missing_compose_file(self, tmp_path):
        """No compose file should return fail with G4_COMMAND_ERROR."""
        feedback = validate_runtime(
            workspace_root=tmp_path,
            compose_path=None,
        )
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G4_COMMAND_ERROR" for d in feedback.diagnostics)

    def test_missing_bootstrap_script(self, tmp_path):
        """Missing bootstrap.sh should return fail."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)
        # Remove the bootstrap script
        import shutil
        shutil.rmtree(tmp_path / "scripts")

        mock_run = _make_mock_run(
            compose_ps_output="",  # No containers running
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        assert feedback.status == GateStatus.fail
        assert any(d.code == "G4_COMMAND_ERROR" for d in feedback.diagnostics)

    def test_no_happy_flow_file_skips_e2e(self, tmp_path):
        """No happy-flow test file should skip E2E check (not a hard failure)."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        # No e2e directory at all
        mock_run = _make_mock_run(
            compose_ps_output="svc0\nsvc1\nsvc2\n",
            bootstrap_verify_rc=0,
            bootstrap_verify_stdout="=== All verification gates PASS ===",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        # Should pass because verify passed and E2E is optional
        assert feedback.status == GateStatus.pass_

    def test_attempt_number_tracking(self, tmp_path):
        """Attempt number should be passed through correctly."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        e2e_dir = tmp_path / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)
        (e2e_dir / "test_wired_01_happy_flow.py").write_text("# mock test")

        mock_run = _make_mock_run(
            compose_ps_output="svc0\nsvc1\nsvc2\n",
            bootstrap_verify_rc=0,
            bootstrap_verify_stdout="=== All verification gates PASS ===",
            e2e_rc=0,
            e2e_stdout="1 passed",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                attempt_number=3,
            )

        assert feedback.attempt_number == 3

    def test_previous_summary_tracking(self, tmp_path):
        """Previous summary should be passed through correctly."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        e2e_dir = tmp_path / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)
        (e2e_dir / "test_wired_01_happy_flow.py").write_text("# mock test")

        mock_run = _make_mock_run(
            compose_ps_output="svc0\nsvc1\nsvc2\n",
            bootstrap_verify_rc=0,
            bootstrap_verify_stdout="=== All verification gates PASS ===",
            e2e_rc=0,
            e2e_stdout="1 passed",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                previous_summary="[gate4.runtime] status=fail diagnostics=2 actions=2 attempt=1",
            )

        assert feedback.metadata.get("previous_summary") is not None

    def test_never_crashes(self, tmp_path):
        """validate_runtime should never crash, even with garbage input."""
        try:
            feedback = validate_runtime(
                workspace_root=Path("/nonexistent"),
                compose_path=Path("/nonexistent/compose.yml"),
            )
            assert feedback.status in (GateStatus.fail, GateStatus.error)
        except Exception:
            pytest.fail("validate_runtime crashed instead of returning GateFeedback")

    def test_actions_are_specific(self, tmp_path):
        """Actions should have specific field paths and descriptions."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        mock_run = _make_mock_run(
            compose_ps_output="",  # No containers
            bootstrap_up_rc=1,
            bootstrap_up_stderr="Error",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        for action in feedback.actions:
            assert action.target_field is not None, f"Action missing target_field: {action.description}"
            assert action.description, "Action missing description"

    def test_actions_capped(self, tmp_path):
        """Actions should be capped at _MAX_ACTIONS."""
        compose_file = _setup_basic_env(tmp_path, service_count=20)

        # Create many unhealthy services to trigger many actions
        fail_lines = "\n".join([f"  FAIL: svc{i} health=unhealthy" for i in range(20)])

        mock_run = _make_mock_run(
            compose_ps_output="\n".join([f"svc{i}" for i in range(20)]),
            bootstrap_verify_rc=1,
            bootstrap_verify_stdout=f"--- Checking health ---\n{fail_lines}\n=== 20 verification gate(s) FAILED ===\n",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        assert len(feedback.actions) <= 7

    def test_verify_missing_network(self, tmp_path):
        """Verify should detect missing networks."""
        compose_file = _setup_basic_env(tmp_path, service_count=2)

        mock_run = _make_mock_run(
            compose_ps_output="svc0\nsvc1\n",
            bootstrap_verify_rc=1,
            bootstrap_verify_stdout=(
                "--- Checking networks ---\n"
                "  OK: edge-net exists\n"
                "  FAIL: observability-net missing\n"
                "=== 1 verification gate(s) FAILED ===\n"
            ),
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        assert feedback.status == GateStatus.fail
        assert any(d.code == "G4_VERIFY_FAILED" for d in feedback.diagnostics)


# =========================================================================
# Integration tests: validate_runtime_from_cli
# =========================================================================

class TestValidateRuntimeFromCLI:
    def test_delegates_to_validate_runtime(self, tmp_path):
        """validate_runtime_from_cli should delegate to validate_runtime."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        e2e_dir = tmp_path / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)
        (e2e_dir / "test_wired_01_happy_flow.py").write_text("# mock test")

        mock_run = _make_mock_run(
            compose_ps_output="svc0\nsvc1\nsvc2\n",
            bootstrap_verify_rc=0,
            bootstrap_verify_stdout="=== All verification gates PASS ===",
            e2e_rc=0,
            e2e_stdout="1 passed",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime_from_cli(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        assert feedback.status == GateStatus.pass_


# =========================================================================
# Edge cases
# =========================================================================

class TestEdgeCases:
    def test_empty_workspace(self, tmp_path):
        """An empty workspace with no files should fail appropriately."""
        feedback = validate_runtime(workspace_root=tmp_path)
        assert feedback.status == GateStatus.fail
        assert len(feedback.diagnostics) > 0

    def test_compose_ps_fails(self, tmp_path):
        """docker compose ps failure should be handled gracefully."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        mock_run = _make_mock_run(
            compose_ps_rc=1,
            compose_ps_stderr="Cannot connect to Docker daemon",
        )

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
            )

        assert feedback.status == GateStatus.fail
        assert any(d.code == "G4_COMMAND_ERROR" for d in feedback.diagnostics)

    def test_bootstrap_up_partial_start(self, tmp_path):
        """bootstrap.sh up succeeds but not all containers start."""
        compose_file = _setup_basic_env(tmp_path, service_count=3)

        call_count = [0]

        def mock_run(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            call_count[0] += 1

            if "ps" in cmd_str and "--format" in cmd_str:
                if call_count[0] <= 1:
                    # First call: empty (stack not running)
                    return MagicMock(returncode=0, stdout="", stderr="")
                else:
                    # Second call: partial (after bootstrap up)
                    return MagicMock(returncode=0, stdout="svc0\n", stderr="")
            elif "bootstrap.sh" in cmd_str and "up" in cmd_str:
                return MagicMock(returncode=0, stdout="Done", stderr="")
            else:
                return MagicMock(returncode=0, stdout="", stderr="")

        with patch("testbed.gates.gate4_runtime.subprocess.run", mock_run):
            feedback = validate_runtime(
                workspace_root=tmp_path,
                compose_path=compose_file,
                skip_up=False,
            )

        assert feedback.status == GateStatus.fail
        assert any(d.code == "G4_BOOTSTRAP_FAILED" for d in feedback.diagnostics)
