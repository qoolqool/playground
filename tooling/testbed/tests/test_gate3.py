"""Tests for Gate 3 — Security & Policy Guardrails.

Tests cover:
- Privilege & capabilities (privileged: true, risky cap_add)
- Dangerous mounts (Docker socket, sensitive host paths)
- Secrets hygiene (hardcoded secrets in env)
- Network / exposure (host network mode, excessive ports)
- Guardrail fidelity (spec guardrails vs compose reality)
- Allowlist mechanism (known exceptions)
- Error handling (missing spec, missing compose, bad JSON)
"""

import json
import sys
from pathlib import Path

# Add the parent of testbed/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
import yaml

from testbed.contracts.spec import (
    TestbedSpec,
    ServiceSpec,
    PortMapping,
    TestSuite,
    InfrastructureSpec,
    ConstraintSpec,
    GuardrailSpec,
)
from testbed.contracts.feedback import GateStatus, Severity
from testbed.gates.gate3_guardrails import (
    validate_guardrails,
    validate_guardrails_from_file,
    _load_compose,
    _is_docker_socket_mount,
    _is_sensitive_host_path,
    _is_secret_env_var,
    _count_published_ports,
)
from testbed.gates.policy_allowlist import (
    PolicyAllowlist,
    default_allowlist,
    RISKY_CAPABILITIES,
    SAFE_CAPABILITIES,
    SENSITIVE_HOST_PATHS,
    DOCKER_SOCKET_PATTERNS,
)


# =========================================================================
# Helper fixtures
# =========================================================================

@pytest.fixture
def quic_spec():
    """A TestbedSpec matching the real QUIC Edge v2 spec."""
    return TestbedSpec(
        name="quic-edge-v2",
        version="0.2.0",
        description="Phase 2 testbed for QUIC/HTTP/3 edge ingress",
        tags=["quic", "http3", "phase-2"],
        services=[
            ServiceSpec(
                name="quic-edge-proxy",
                image="envoyproxy/envoy:v1.29-latest",
                ports=[
                    PortMapping(host=443, container=443, protocol="udp"),
                    PortMapping(host=8443, container=8443, protocol="tcp"),
                ],
                mem_limit="512M",
                healthcheck={
                    "test": ["CMD", "bash", "-c", "exec 3<>/dev/tcp/localhost/9901; echo -e 'GET /ready HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3; grep -q 'LIVE' <&3"],
                    "interval": "15s",
                    "timeout": "5s",
                    "retries": 3,
                    "start_period": "10s",
                },
                networks=["edge-net", "internal-net"],
                labels={"project": "quic-edge-v2", "managed-by": "testbed"},
            ),
            ServiceSpec(
                name="netem-router",
                image="quic-testbed/netem:latest",
                build="./src/netem",
                ports=[PortMapping(host=8080, container=8080)],
                mem_limit="256M",
                cap_add=["NET_ADMIN"],
                healthcheck={
                    "test": ["CMD", "pgrep", "-x", "tail"],
                    "interval": "15s",
                    "timeout": "5s",
                    "retries": 3,
                },
                networks=["edge-net"],
                labels={"project": "quic-edge-v2", "managed-by": "testbed"},
            ),
            ServiceSpec(
                name="otel-collector",
                image="otel/opentelemetry-collector-contrib:latest",
                ports=[
                    PortMapping(host=4317, container=4317),
                    PortMapping(host=4318, container=4318),
                ],
                mem_limit="256M",
                healthcheck={"disable": True},
                networks=["internal-net", "observability-net"],
                labels={"project": "quic-edge-v2", "managed-by": "testbed"},
            ),
        ],
        test_suites=[
            TestSuite(name="smoke", path="tests/smoke/", framework="pytest"),
        ],
        infrastructure=InfrastructureSpec(
            networks={
                "edge-net": {"driver": "bridge"},
                "internal-net": {"driver": "bridge"},
                "observability-net": {"driver": "bridge"},
            },
        ),
        constraints=ConstraintSpec(max_containers=15),
        guardrails=GuardrailSpec(
            require_mem_limit=True,
            require_healthcheck=True,
            no_host_network=True,
            no_privileged=False,
        ),
    )


@pytest.fixture
def clean_compose():
    """A clean compose file with no security issues."""
    return {
        "name": "quic-edge-v2",
        "networks": {
            "edge-net": {"driver": "bridge"},
            "internal-net": {"driver": "bridge"},
            "observability-net": {"driver": "bridge"},
        },
        "services": {
            "quic-edge-proxy": {
                "image": "envoyproxy/envoy:v1.29-latest",
                "container_name": "quic-edge-proxy",
                "ports": ["443:443/udp", "8443:8443/tcp"],
                "mem_limit": "512M",
                "healthcheck": {
                    "test": ["CMD", "bash", "-c", "exec 3<>/dev/tcp/localhost/9901; echo -e 'GET /ready HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3; grep -q 'LIVE' <&3"],
                    "interval": "15s",
                    "timeout": "5s",
                    "retries": 3,
                    "start_period": "10s",
                },
                "networks": ["edge-net", "internal-net"],
                "labels": {"project": "quic-edge-v2", "managed-by": "testbed"},
            },
            "netem-router": {
                "image": "quic-testbed/netem:latest",
                "container_name": "netem-router",
                "ports": ["8080:8080"],
                "mem_limit": "256M",
                "cap_add": ["NET_ADMIN"],
                "healthcheck": {
                    "test": ["CMD", "pgrep", "-x", "tail"],
                    "interval": "15s",
                    "timeout": "5s",
                    "retries": 3,
                },
                "networks": ["edge-net"],
                "labels": {"project": "quic-edge-v2", "managed-by": "testbed"},
            },
            "otel-collector": {
                "image": "otel/opentelemetry-collector-contrib:latest",
                "container_name": "otel-collector",
                "ports": ["4317:4317", "4318:4318"],
                "mem_limit": "256M",
                "healthcheck": {"disable": True},
                "networks": ["internal-net", "observability-net"],
                "labels": {"project": "quic-edge-v2", "managed-by": "testbed"},
            },
        },
    }


# =========================================================================
# Unit tests: helper functions
# =========================================================================

class TestIsDockerSocketMount:
    def test_docker_sock(self):
        assert _is_docker_socket_mount("/var/run/docker.sock")

    def test_short_sock(self):
        assert _is_docker_socket_mount("/run/docker.sock")

    def test_var_run_docker(self):
        assert _is_docker_socket_mount("/var/run/docker")

    def test_normal_path(self):
        assert not _is_docker_socket_mount("/data")

    def test_empty(self):
        assert not _is_docker_socket_mount("")

    def test_variable_prefix(self):
        """Variable-prefixed paths should still be detected."""
        assert _is_docker_socket_mount("${HOST_DIR}/var/run/docker.sock")


class TestIsSensitiveHostPath:
    def test_root(self):
        assert _is_sensitive_host_path("/")

    def test_etc(self):
        assert _is_sensitive_host_path("/etc")

    def test_proc(self):
        assert _is_sensitive_host_path("/proc")

    def test_sys(self):
        assert _is_sensitive_host_path("/sys")

    def test_dev(self):
        assert _is_sensitive_host_path("/dev")

    def test_docker_sock(self):
        assert _is_sensitive_host_path("/var/run/docker.sock")

    def test_normal_path(self):
        assert not _is_sensitive_host_path("/data")

    def test_relative_path(self):
        assert not _is_sensitive_host_path("./data")

    def test_variable_prefix(self):
        assert _is_sensitive_host_path("${HOST_DIR}/etc")


class TestIsSecretEnvVar:
    def test_password_in_name(self):
        assert _is_secret_env_var("DB_PASSWORD", "s3cret123")

    def test_api_key_in_name(self):
        assert _is_secret_env_var("API_KEY", "abc123def456")

    def test_token_in_name(self):
        assert _is_secret_env_var("AUTH_TOKEN", "tok_xyz789")

    def test_secret_in_name(self):
        assert _is_secret_env_var("SECRET_KEY", "my-secret-value")

    def test_variable_reference_not_secret(self):
        """Variable references like ${VAR} should not be flagged."""
        assert not _is_secret_env_var("DB_PASSWORD", "${DB_PASSWORD}")

    def test_empty_value_not_secret(self):
        assert not _is_secret_env_var("DB_PASSWORD", "")

    def test_path_value_not_secret(self):
        assert not _is_secret_env_var("CONFIG_PATH", "/etc/config")

    def test_normal_env_var_not_secret(self):
        assert not _is_secret_env_var("LOG_LEVEL", "debug")

    def test_long_alphanumeric_looks_like_key(self):
        """A long alphanumeric value in a secret-named var should be flagged."""
        assert _is_secret_env_var("API_KEY", "abcdef1234567890abcdef1234567890ab")


class TestCountPublishedPorts:
    def test_no_ports(self):
        assert _count_published_ports({}) == 0

    def test_single_port(self):
        assert _count_published_ports({"ports": ["8080:8080"]}) == 1

    def test_multiple_ports(self):
        assert _count_published_ports({"ports": ["8080:8080", "443:443/udp", "9090:9090"]}) == 3

    def test_not_a_list(self):
        assert _count_published_ports({"ports": "string"}) == 0


# =========================================================================
# Unit tests: _load_compose
# =========================================================================

class TestLoadCompose:
    def test_valid_compose(self, tmp_path):
        compose_path = tmp_path / "compose.yml"
        compose_data = {"services": {"web": {"image": "nginx"}}}
        compose_path.write_text(yaml.dump(compose_data))
        result, diags, actions = _load_compose(compose_path)
        assert result is not None
        assert len(diags) == 0

    def test_missing_file(self, tmp_path):
        compose_path = tmp_path / "nonexistent.yml"
        result, diags, actions = _load_compose(compose_path)
        assert result is None
        assert any(d.code == "G3_MISSING_COMPOSE" for d in diags)

    def test_invalid_yaml(self, tmp_path):
        compose_path = tmp_path / "bad.yml"
        compose_path.write_text("{invalid: yaml: [}")
        result, diags, actions = _load_compose(compose_path)
        assert result is None
        assert any(d.code == "G3_COMPOSE_SYNTAX" for d in diags)


# =========================================================================
# Integration tests: validate_guardrails
# =========================================================================

class TestValidateGuardrails:
    def test_clean_compose_passes(self, quic_spec, clean_compose, tmp_path):
        """A clean compose with no security issues should pass."""
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(clean_compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.pass_, f"Expected pass, got fail: {[d.message for d in feedback.diagnostics]}"
        # Should only have info-level diagnostics (allowlisted exceptions)
        for d in feedback.diagnostics:
            assert d.severity in (Severity.info,), f"Unexpected severity: {d.severity} for {d.code}"

    def test_privileged_container_fails(self, quic_spec, clean_compose, tmp_path):
        """A service with privileged: true should fail."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["privileged"] = True

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G3_PRIVILEGED_CONTAINER" and d.severity == Severity.error for d in feedback.diagnostics)

    def test_privileged_allowlisted(self, quic_spec, clean_compose, tmp_path):
        """A service with privileged: true that is allowlisted should pass with info."""
        allowlist = default_allowlist()
        allowlist.allowed_privileged_services.append("quic-edge-proxy")

        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["privileged"] = True

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path, allowlist=allowlist)
        # Should pass (only info-level for allowlisted privileged)
        has_error = any(d.severity == Severity.error for d in feedback.diagnostics)
        assert not has_error, f"Unexpected errors: {[d.message for d in feedback.diagnostics if d.severity == Severity.error]}"

    def test_risky_capability_fails(self, quic_spec, clean_compose, tmp_path):
        """A service with a risky capability should fail."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["cap_add"] = ["SYS_ADMIN"]

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G3_RISKY_CAPABILITY" and d.severity == Severity.error for d in feedback.diagnostics)

    def test_safe_capability_not_flagged(self, quic_spec, clean_compose, tmp_path):
        """A service with a safe capability (NET_ADMIN) should not be flagged."""
        # netem-router already has NET_ADMIN in clean_compose, and it's allowlisted
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(clean_compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        # NET_ADMIN is in SAFE_CAPABILITIES, so it should not be flagged
        risky_caps = [d for d in feedback.diagnostics if d.code == "G3_RISKY_CAPABILITY"]
        assert len(risky_caps) == 0

    def test_docker_socket_mount_fails(self, quic_spec, clean_compose, tmp_path):
        """A service with Docker socket mount should fail critically."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["volumes"] = ["/var/run/docker.sock:/var/run/docker.sock"]

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G3_DOCKER_SOCKET_MOUNT" and d.severity == Severity.critical for d in feedback.diagnostics)

    def test_sensitive_host_path_mount_fails(self, quic_spec, clean_compose, tmp_path):
        """A service with sensitive host path mount should fail."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["volumes"] = ["/etc:/host/etc:ro"]

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G3_HOST_PATH_MOUNT" and d.severity == Severity.error for d in feedback.diagnostics)

    def test_secret_in_env_fails(self, quic_spec, clean_compose, tmp_path):
        """A service with hardcoded secret in env should fail."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["environment"] = {
            "DB_PASSWORD": "s3cret123",
        }

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G3_SECRET_IN_ENV" for d in feedback.diagnostics)

    def test_secret_in_env_list_format_fails(self, quic_spec, clean_compose, tmp_path):
        """A service with hardcoded secret in env list format should fail."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["environment"] = [
            "DB_PASSWORD=s3cret123",
        ]

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G3_SECRET_IN_ENV" for d in feedback.diagnostics)

    def test_host_network_mode_fails_when_disallowed(self, quic_spec, clean_compose, tmp_path):
        """Host network mode should fail when spec disallows it."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["network_mode"] = "host"

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G3_HOST_NETWORK_MODE" and d.severity == Severity.error for d in feedback.diagnostics)

    def test_host_network_mode_warns_when_allowed(self, quic_spec, clean_compose, tmp_path):
        """Host network mode should warn when spec allows it."""
        spec = quic_spec.model_copy(deep=True)
        spec.guardrails.no_host_network = False

        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["network_mode"] = "host"

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(spec, workspace_root=tmp_path, compose_path=compose_path)
        # Should have a warning, not an error
        host_net_diags = [d for d in feedback.diagnostics if d.code == "G3_HOST_NETWORK_MODE"]
        assert len(host_net_diags) > 0
        assert all(d.severity == Severity.warning for d in host_net_diags)

    def test_excessive_ports_warns(self, quic_spec, clean_compose, tmp_path):
        """A service with too many ports should warn."""
        spec = quic_spec.model_copy(deep=True)
        spec.guardrails.max_exposed_ports = 1  # Very low limit

        compose = clean_compose.copy()
        # otel-collector has 2 ports
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G3_EXCESSIVE_PORTS" for d in feedback.diagnostics)

    def test_guardrail_violation_privileged(self, quic_spec, clean_compose, tmp_path):
        """Spec says no_privileged=true but compose has privileged: true."""
        spec = quic_spec.model_copy(deep=True)
        spec.guardrails.no_privileged = True

        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["privileged"] = True

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G3_GUARDRAIL_VIOLATION" for d in feedback.diagnostics)

    def test_guardrail_violation_healthcheck_disabled(self, quic_spec, clean_compose, tmp_path):
        """Spec says require_healthcheck=true but compose has healthcheck disabled (not allowlisted)."""
        spec = quic_spec.model_copy(deep=True)
        spec.guardrails.require_healthcheck = True

        allowlist = default_allowlist()
        allowlist.healthcheck_disabled_services = []  # Remove otel-collector from allowlist

        compose = clean_compose.copy()
        # otel-collector has healthcheck disabled

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(spec, workspace_root=tmp_path, compose_path=compose_path, allowlist=allowlist)
        assert any(d.code == "G3_GUARDRAIL_VIOLATION" for d in feedback.diagnostics)

    def test_guardrail_violation_missing_healthcheck(self, quic_spec, clean_compose, tmp_path):
        """Spec says require_healthcheck=true but compose has no healthcheck at all."""
        spec = quic_spec.model_copy(deep=True)
        spec.guardrails.require_healthcheck = True

        compose = clean_compose.copy()
        del compose["services"]["quic-edge-proxy"]["healthcheck"]

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G3_GUARDRAIL_VIOLATION" for d in feedback.diagnostics)

    def test_guardrail_violation_missing_mem_limit(self, quic_spec, clean_compose, tmp_path):
        """Spec says require_mem_limit=true but compose has no mem_limit."""
        spec = quic_spec.model_copy(deep=True)
        spec.guardrails.require_mem_limit = True

        compose = clean_compose.copy()
        del compose["services"]["quic-edge-proxy"]["mem_limit"]

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G3_GUARDRAIL_VIOLATION" for d in feedback.diagnostics)

    def test_guardrail_violation_missing_labels(self, quic_spec, clean_compose, tmp_path):
        """Spec requires labels but compose service is missing them."""
        spec = quic_spec.model_copy(deep=True)
        spec.guardrails.required_labels = ["project", "managed-by", "owner"]

        compose = clean_compose.copy()
        # Services have project and managed-by but not owner

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G3_GUARDRAIL_VIOLATION" for d in feedback.diagnostics)

    def test_guardrail_violation_blocked_image(self, quic_spec, clean_compose, tmp_path):
        """Spec blocks an image prefix and compose uses it."""
        spec = quic_spec.model_copy(deep=True)
        spec.guardrails.blocked_images = ["envoyproxy/"]

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(clean_compose))

        feedback = validate_guardrails(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G3_GUARDRAIL_VIOLATION" for d in feedback.diagnostics)

    def test_allowlist_net_admin_not_flagged(self, quic_spec, clean_compose, tmp_path):
        """NET_ADMIN on netem-router should not be flagged (in SAFE_CAPABILITIES)."""
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(clean_compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        risky_caps = [d for d in feedback.diagnostics if d.code == "G3_RISKY_CAPABILITY"]
        assert len(risky_caps) == 0

    def test_allowlist_healthcheck_disabled(self, quic_spec, clean_compose, tmp_path):
        """otel-collector healthcheck disabled should be info-level (allowlisted)."""
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(clean_compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        hc_disabled = [d for d in feedback.diagnostics if d.code == "G3_HEALTHCHECK_DISABLED"]
        assert len(hc_disabled) == 1
        assert hc_disabled[0].severity == Severity.info

    def test_multiple_issues_produce_multiple_actions(self, quic_spec, clean_compose, tmp_path):
        """Multiple issues should produce multiple actions."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["privileged"] = True
        compose["services"]["quic-edge-proxy"]["volumes"] = ["/var/run/docker.sock:/var/run/docker.sock"]
        compose["services"]["quic-edge-proxy"]["environment"] = {"DB_PASSWORD": "s3cret123"}

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert len(feedback.diagnostics) >= 3
        assert len(feedback.actions) > 0

    def test_actions_are_specific(self, quic_spec, clean_compose, tmp_path):
        """Actions should have specific field paths."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["privileged"] = True

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        for action in feedback.actions:
            assert action.target_field is not None, f"Action missing target_field: {action.description}"
            assert action.description, "Action missing description"

    def test_spec_snapshot_included(self, quic_spec, clean_compose, tmp_path):
        """Feedback should include a spec_snapshot."""
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(clean_compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.spec_snapshot is not None
        assert feedback.spec_snapshot["name"] == "quic-edge-v2"

    def test_never_crashes(self):
        """validate_guardrails should never crash, even with garbage input."""
        try:
            feedback = validate_guardrails(
                spec="not a spec",  # type: ignore
                workspace_root=Path("/nonexistent"),
            )
            assert feedback.status in (GateStatus.fail, GateStatus.error)
        except Exception:
            pytest.fail("validate_guardrails crashed instead of returning GateFeedback")

    def test_no_compose_file_found(self, quic_spec, tmp_path):
        """No compose file in workspace should fail."""
        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G3_MISSING_COMPOSE" for d in feedback.diagnostics)

    def test_volume_dict_format_docker_socket(self, quic_spec, clean_compose, tmp_path):
        """Docker socket mount in dict format should be detected."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["volumes"] = [
            {"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}
        ]

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G3_DOCKER_SOCKET_MOUNT" for d in feedback.diagnostics)

    def test_volume_dict_format_sensitive_path(self, quic_spec, clean_compose, tmp_path):
        """Sensitive host path mount in dict format should be detected."""
        compose = clean_compose.copy()
        compose["services"]["quic-edge-proxy"]["volumes"] = [
            {"type": "bind", "source": "/etc", "target": "/host/etc"}
        ]

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G3_HOST_PATH_MOUNT" for d in feedback.diagnostics)


# =========================================================================
# Integration tests: validate_guardrails_from_file
# =========================================================================

class TestValidateGuardrailsFromFile:
    def test_missing_spec_file(self, tmp_path):
        """A missing spec file should return an error feedback."""
        feedback = validate_guardrails_from_file(
            spec_path=tmp_path / "nonexistent.json",
            workspace_root=tmp_path,
        )
        assert feedback.status == GateStatus.error
        assert any(d.code == "GATE_CRASH" for d in feedback.diagnostics)

    def test_invalid_json_spec(self, tmp_path):
        """An invalid JSON spec file should return an error feedback."""
        spec_path = tmp_path / "bad.json"
        spec_path.write_text("not json")
        feedback = validate_guardrails_from_file(
            spec_path=spec_path,
            workspace_root=tmp_path,
        )
        assert feedback.status == GateStatus.error
        assert any(d.code == "GATE_CRASH" for d in feedback.diagnostics)

    def test_valid_spec_file(self, quic_spec, clean_compose, tmp_path):
        """A valid spec file should work end-to-end."""
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(quic_spec.model_dump_json(indent=2))

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(clean_compose))

        feedback = validate_guardrails_from_file(
            spec_path=spec_path,
            workspace_root=tmp_path,
            compose_path=compose_path,
        )
        assert feedback.status == GateStatus.pass_, f"Expected pass, got fail: {[d.message for d in feedback.diagnostics]}"

    def test_attempt_number_tracking(self, quic_spec, clean_compose, tmp_path):
        """Attempt number should be passed through correctly."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {"image": "nginx:latest", "privileged": True},
            },
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path, attempt_number=3)
        assert feedback.attempt_number == 3

    def test_previous_summary_tracking(self, quic_spec, clean_compose, tmp_path):
        """Previous summary should be passed through correctly."""
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(clean_compose))

        feedback = validate_guardrails(
            quic_spec,
            workspace_root=tmp_path,
            compose_path=compose_path,
            previous_summary="[gate3.guardrails] status=fail diagnostics=2 actions=2 attempt=1",
        )
        assert feedback.metadata.get("previous_summary") is not None


# =========================================================================
# Edge cases
# =========================================================================

class TestEdgeCases:
    def test_empty_workspace(self, quic_spec, tmp_path):
        """An empty workspace with no files should fail appropriately."""
        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path)
        assert feedback.status == GateStatus.fail
        assert len(feedback.diagnostics) > 0

    def test_actions_capped(self, quic_spec, tmp_path):
        """Actions should be capped at _MAX_ACTIONS."""
        compose_data = {
            "services": {
                f"svc{i}": {
                    "image": f"img{i}:latest",
                    "privileged": True,
                }
                for i in range(10)
            },
        }
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_guardrails(quic_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert len(feedback.actions) <= 7

    def test_risky_capability_not_in_safe_list(self):
        """Verify that no capability is in both RISKY and SAFE lists."""
        overlap = RISKY_CAPABILITIES & SAFE_CAPABILITIES
        assert len(overlap) == 0, f"Capabilities in both risky and safe: {overlap}"

    def test_default_allowlist_has_netem(self):
        """Default allowlist should include netem-router NET_ADMIN."""
        allowlist = default_allowlist()
        assert "netem-router" in allowlist.allowed_capabilities
        assert "NET_ADMIN" in allowlist.allowed_capabilities["netem-router"]

    def test_default_allowlist_has_otel(self):
        """Default allowlist should include otel-collector healthcheck disable."""
        allowlist = default_allowlist()
        assert "otel-collector" in allowlist.healthcheck_disabled_services
