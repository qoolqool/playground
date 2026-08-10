"""Tests for Gate 2 — Code / Artifact Validator.

Tests cover:
- Spec ↔ Artifact consistency (image, build, ports, mem_limit, healthcheck, networks, depends_on)
- Required files exist (compose, Dockerfiles, test paths)
- Compose / config syntax & basic structure
- Network consistency
- Test suite presence
- Undeclared services
- Static hygiene (config file syntax)
- Error handling (missing spec, missing compose, bad JSON)
"""

import json
import sys
import tempfile
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
from testbed.gates.gate2_code_validator import (
    validate_code,
    validate_code_from_file,
    _load_compose,
    _normalize_port_str,
    _compose_port_to_normalized,
    _normalize_healthcheck,
    _healthchecks_match,
    _mem_limits_match,
    _networks_match,
    _depends_on_match,
    _resolve_build_path,
)


# =========================================================================
# Helper fixtures
# =========================================================================

@pytest.fixture
def minimal_spec():
    """A minimal valid TestbedSpec for testing."""
    return TestbedSpec(
        name="test-testbed",
        services=[
            ServiceSpec(
                name="web",
                image="nginx:latest",
                mem_limit="256M",
                healthcheck={"test": ["CMD", "curl", "-f", "http://localhost/health"]},
                networks=["app-net"],
            ),
        ],
        infrastructure=InfrastructureSpec(
            networks={"app-net": {"driver": "bridge"}},
        ),
    )


@pytest.fixture
def full_spec():
    """A full TestbedSpec matching the real workspace pattern."""
    return TestbedSpec(
        name="quic-edge-v2",
        version="0.1.0",
        description="Phase 1 testbed for QUIC/HTTP/3 edge ingress",
        tags=["quic", "http3", "phase-1"],
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
                name="caddy",
                image="caddy:2-alpine",
                ports=[
                    PortMapping(host=444, container=444, protocol="udp"),
                    PortMapping(host=8444, container=8444, protocol="tcp"),
                ],
                mem_limit="128M",
                healthcheck={
                    "test": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
                    "interval": "15s",
                    "timeout": "5s",
                    "retries": 3,
                    "start_period": "10s",
                },
                networks=["edge-net", "internal-net"],
                labels={"project": "quic-edge-v2", "managed-by": "testbed"},
            ),
            ServiceSpec(
                name="mock-payment-api",
                image="quic-testbed/mock-api:latest",
                build="./src/mock-api",
                ports=[PortMapping(host=8000, container=8000)],
                mem_limit="256M",
                healthcheck={
                    "test": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                    "interval": "15s",
                    "timeout": "5s",
                    "retries": 3,
                },
                networks=["internal-net"],
                depends_on=["quic-edge-proxy"],
                labels={"project": "quic-edge-v2", "managed-by": "testbed"},
            ),
            ServiceSpec(
                name="quic-client",
                image="quic-testbed/quic-client:latest",
                build="./src/quic-client",
                mem_limit="256M",
                healthcheck={
                    "test": ["CMD-SHELL", "cat /proc/1/cmdline | grep -q tail || exit 1"],
                    "interval": "30s",
                    "timeout": "5s",
                    "retries": 2,
                    "start_period": "10s",
                },
                networks=["edge-net"],
                depends_on=["quic-edge-proxy", "caddy"],
                labels={"project": "quic-edge-v2", "managed-by": "testbed"},
            ),
            ServiceSpec(
                name="test-runner",
                image="python:3.12-slim",
                mem_limit="256M",
                healthcheck={
                    "test": ["CMD-SHELL", "python3 -c 'import pytest' || exit 1"],
                    "interval": "30s",
                    "timeout": "5s",
                    "retries": 3,
                    "start_period": "30s",
                },
                networks=["edge-net", "internal-net"],
                depends_on=["quic-edge-proxy", "caddy", "mock-payment-api", "quic-client"],
                labels={"project": "quic-edge-v2", "managed-by": "testbed"},
            ),
        ],
        test_suites=[
            TestSuite(name="smoke", path="tests/smoke/", framework="pytest"),
            TestSuite(name="h3-handshake", path="tests/h3-handshake/", framework="pytest"),
        ],
        infrastructure=InfrastructureSpec(
            networks={
                "edge-net": {"driver": "bridge"},
                "internal-net": {"driver": "bridge"},
            },
        ),
        constraints=ConstraintSpec(max_containers=10),
        guardrails=GuardrailSpec(
            require_mem_limit=True,
            require_healthcheck=True,
            no_host_network=True,
            no_privileged=True,
        ),
    )


@pytest.fixture
def matching_compose():
    """A Docker Compose file that matches full_spec."""
    return {
        "name": "quic-edge-v2",
        "networks": {
            "edge-net": {"driver": "bridge"},
            "internal-net": {"driver": "bridge"},
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
            "caddy": {
                "image": "caddy:2-alpine",
                "container_name": "caddy",
                "ports": ["444:444/udp", "8444:8444/tcp"],
                "mem_limit": "128M",
                "healthcheck": {
                    "test": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
                    "interval": "15s",
                    "timeout": "5s",
                    "retries": 3,
                    "start_period": "10s",
                },
                "networks": ["edge-net", "internal-net"],
                "labels": {"project": "quic-edge-v2", "managed-by": "testbed"},
            },
            "mock-payment-api": {
                "build": {"context": "./src/mock-api", "dockerfile": "Dockerfile"},
                "image": "quic-testbed/mock-api:latest",
                "container_name": "mock-payment-api",
                "ports": ["8000:8000"],
                "mem_limit": "256M",
                "healthcheck": {
                    "test": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                    "interval": "15s",
                    "timeout": "5s",
                    "retries": 3,
                },
                "networks": ["internal-net"],
                "depends_on": ["quic-edge-proxy"],
                "labels": {"project": "quic-edge-v2", "managed-by": "testbed"},
            },
            "quic-client": {
                "build": {"context": "./src/quic-client", "dockerfile": "Dockerfile"},
                "image": "quic-testbed/quic-client:latest",
                "container_name": "quic-client",
                "mem_limit": "256M",
                "healthcheck": {
                    "test": ["CMD-SHELL", "cat /proc/1/cmdline | grep -q tail || exit 1"],
                    "interval": "30s",
                    "timeout": "5s",
                    "retries": 2,
                    "start_period": "10s",
                },
                "networks": ["edge-net"],
                "depends_on": ["quic-edge-proxy", "caddy"],
                "labels": {"project": "quic-edge-v2", "managed-by": "testbed"},
            },
            "test-runner": {
                "image": "python:3.12-slim",
                "container_name": "test-runner",
                "mem_limit": "256M",
                "healthcheck": {
                    "test": ["CMD-SHELL", "python3 -c 'import pytest' || exit 1"],
                    "interval": "30s",
                    "timeout": "5s",
                    "retries": 3,
                    "start_period": "30s",
                },
                "networks": ["edge-net", "internal-net"],
                "depends_on": ["quic-edge-proxy", "caddy", "mock-payment-api", "quic-client"],
                "labels": {"project": "quic-edge-v2", "managed-by": "testbed"},
            },
        },
    }


# =========================================================================
# Unit tests: helper functions
# =========================================================================

class TestNormalizePortStr:
    def test_basic_tcp(self):
        assert _normalize_port_str(8080, 8080) == "8080:8080/tcp"

    def test_udp(self):
        assert _normalize_port_str(443, 443, "udp") == "443:443/udp"

    def test_different_ports(self):
        assert _normalize_port_str(8443, 443) == "8443:443/tcp"


class TestComposePortToNormalized:
    def test_full_format(self):
        assert _compose_port_to_normalized("443:443/udp") == "443:443/udp"

    def test_tcp_default(self):
        assert _compose_port_to_normalized("8080:8080") == "8080:8080/tcp"

    def test_short_form(self):
        assert _compose_port_to_normalized("8000") == "8000:8000/tcp"

    def test_short_form_udp(self):
        assert _compose_port_to_normalized("8000/udp") == "8000:8000/udp"

    def test_invalid(self):
        assert _compose_port_to_normalized(8080) is None
        assert _compose_port_to_normalized("") is None


class TestNormalizeHealthcheck:
    def test_cmd_list(self):
        hc = {"test": ["CMD", "curl", "-f", "http://localhost/health"]}
        result = _normalize_healthcheck(hc)
        assert result is not None
        assert result[0] == ("CMD", "curl", "-f", "http://localhost/health")

    def test_cmd_shell_string(self):
        hc = {"test": "curl -f http://localhost/health || exit 1"}
        result = _normalize_healthcheck(hc)
        assert result is not None
        assert result[0] == ("CMD-SHELL", "curl -f http://localhost/health || exit 1")

    def test_none(self):
        assert _normalize_healthcheck(None) is None
        assert _normalize_healthcheck({}) is None

    def test_with_interval_timeout(self):
        hc = {
            "test": ["CMD", "pg_isready"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 3,
        }
        result = _normalize_healthcheck(hc)
        assert result is not None
        assert result[1] == "10s"
        assert result[2] == "5s"
        assert result[3] == 3


class TestHealthchecksMatch:
    def test_exact_match(self):
        hc1 = {"test": ["CMD", "curl", "-f", "http://localhost/health"]}
        hc2 = {"test": ["CMD", "curl", "-f", "http://localhost/health"]}
        assert _healthchecks_match(hc1, hc2)

    def test_both_none(self):
        assert _healthchecks_match(None, None)

    def test_one_none(self):
        hc = {"test": ["CMD", "curl"]}
        assert not _healthchecks_match(hc, None)
        assert not _healthchecks_match(None, hc)

    def test_similar_keywords(self):
        """Healthchecks with same significant keywords should match."""
        hc1 = {"test": ["CMD", "curl", "-f", "http://localhost:8000/health"]}
        hc2 = {"test": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]}
        assert _healthchecks_match(hc1, hc2)

    def test_different_mechanisms(self):
        """Healthchecks with different mechanisms should not match."""
        hc1 = {"test": ["CMD", "pg_isready"]}
        hc2 = {"test": ["CMD", "curl", "-f", "http://localhost/health"]}
        assert not _healthchecks_match(hc1, hc2)


class TestMemLimitsMatch:
    def test_exact_match(self):
        assert _mem_limits_match("512M", "512M")

    def test_both_none(self):
        assert _mem_limits_match(None, None)

    def test_one_none(self):
        assert not _mem_limits_match("512M", None)
        assert not _mem_limits_match(None, "512M")

    def test_case_insensitive(self):
        assert _mem_limits_match("512m", "512M")
        assert _mem_limits_match("1g", "1G")

    def test_different_values(self):
        assert not _mem_limits_match("256M", "512M")


class TestNetworksMatch:
    def test_exact_match(self):
        assert _networks_match(["edge-net", "internal-net"], ["edge-net", "internal-net"])

    def test_both_empty(self):
        assert _networks_match([], [])

    def test_different_order(self):
        assert _networks_match(["a", "b"], ["b", "a"])

    def test_mismatch(self):
        assert not _networks_match(["a"], ["b"])
        assert not _networks_match(["a", "b"], ["a"])

    def test_dict_format(self):
        """Compose long syntax: [{'net-name': {'aliases': [...]}}]"""
        assert _networks_match(["edge-net"], [{"edge-net": {"aliases": ["proxy"]}}])


class TestDependsOnMatch:
    def test_exact_match(self):
        assert _depends_on_match(["a", "b"], ["a", "b"])

    def test_both_empty(self):
        assert _depends_on_match([], None)
        assert _depends_on_match([], [])

    def test_dict_format(self):
        """Compose long syntax: {'svc': {'condition': 'service_healthy'}}"""
        assert _depends_on_match(["a"], {"a": {"condition": "service_healthy"}})

    def test_mismatch(self):
        assert not _depends_on_match(["a"], ["b"])
        assert not _depends_on_match(["a", "b"], ["a"])


class TestResolveBuildPath:
    def test_relative_to_workspace(self, tmp_path):
        """A relative path should resolve relative to workspace."""
        result = _resolve_build_path("./src/mock-api", tmp_path / "compose" / "root.yml", tmp_path)
        assert result == (tmp_path / "src" / "mock-api").resolve()

    def test_variable_prefix(self, tmp_path):
        """${VAR}/src/... should strip the variable and resolve relative to workspace."""
        result = _resolve_build_path("${HOST_PROJECT_DIR}/src/mock-api", tmp_path / "compose" / "root.yml", tmp_path)
        assert result == (tmp_path / "src" / "mock-api").resolve()

    def test_absolute_path(self, tmp_path):
        """An absolute path should be returned as-is."""
        abs_path = tmp_path / "some" / "dir"
        abs_path.mkdir(parents=True)
        result = _resolve_build_path(str(abs_path), tmp_path / "compose" / "root.yml", tmp_path)
        assert result == abs_path.resolve()


# =========================================================================
# Unit tests: _load_compose
# =========================================================================

class TestLoadCompose:
    def test_valid_compose(self, tmp_path):
        compose_path = tmp_path / "compose.yml"
        compose_data = {"services": {"web": {"image": "nginx"}}, "networks": {"net1": {}}}
        compose_path.write_text(yaml.dump(compose_data))
        result, diags, actions = _load_compose(compose_path)
        assert result is not None
        assert result["services"]["web"]["image"] == "nginx"
        assert len(diags) == 0

    def test_missing_file(self, tmp_path):
        compose_path = tmp_path / "nonexistent.yml"
        result, diags, actions = _load_compose(compose_path)
        assert result is None
        assert any(d.code == "G2_MISSING_FILE" for d in diags)

    def test_invalid_yaml(self, tmp_path):
        compose_path = tmp_path / "bad.yml"
        compose_path.write_text("{invalid: yaml: [}")
        result, diags, actions = _load_compose(compose_path)
        assert result is None
        assert any(d.code == "G2_COMPOSE_SYNTAX" for d in diags)

    def test_not_a_dict(self, tmp_path):
        compose_path = tmp_path / "list.yml"
        compose_path.write_text(yaml.dump(["a", "b"]))
        result, diags, actions = _load_compose(compose_path)
        assert result is None
        assert any(d.code == "G2_COMPOSE_STRUCTURE" for d in diags)

    def test_missing_services(self, tmp_path):
        compose_path = tmp_path / "no_services.yml"
        compose_path.write_text(yaml.dump({"networks": {}}))
        result, diags, actions = _load_compose(compose_path)
        assert result is not None
        assert any(d.code == "G2_COMPOSE_STRUCTURE" for d in diags)


# =========================================================================
# Integration tests: validate_code
# =========================================================================

class TestValidateCode:
    def test_perfect_match(self, full_spec, matching_compose, tmp_path):
        """A spec and compose that match perfectly should pass."""
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(matching_compose))

        # Create mock Dockerfiles
        (tmp_path / "src" / "mock-api").mkdir(parents=True)
        (tmp_path / "src" / "mock-api" / "Dockerfile").write_text("FROM python:3.12-slim\n")
        (tmp_path / "src" / "quic-client").mkdir(parents=True)
        (tmp_path / "src" / "quic-client" / "Dockerfile").write_text("FROM python:3.12-slim\n")

        # Create test directories
        (tmp_path / "tests" / "smoke").mkdir(parents=True)
        (tmp_path / "tests" / "smoke" / "test_smoke.py").write_text("def test_pass(): pass\n")
        (tmp_path / "tests" / "h3-handshake").mkdir(parents=True)
        (tmp_path / "tests" / "h3-handshake" / "test_h3.py").write_text("def test_pass(): pass\n")

        feedback = validate_code(full_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.pass_, f"Expected pass, got fail: {[d.message for d in feedback.diagnostics]}"
        assert len(feedback.diagnostics) == 0

    def test_missing_service_in_compose(self, minimal_spec, tmp_path):
        """A service in spec but not in compose should fail."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {},  # No services at all
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G2_MISSING_SERVICE" for d in feedback.diagnostics)

    def test_undeclared_service(self, minimal_spec, tmp_path):
        """A service in compose but not in spec should warn."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {"image": "nginx:latest"},
                "redis": {"image": "redis:alpine"},  # Not in spec
            },
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_UNDECLARED_SERVICE" for d in feedback.diagnostics)

    def test_image_mismatch(self, minimal_spec, tmp_path):
        """A service with wrong image should fail."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {"image": "httpd:latest"},  # Spec says nginx:latest
            },
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_IMAGE_MISMATCH" for d in feedback.diagnostics)

    def test_missing_mem_limit(self, minimal_spec, tmp_path):
        """A service missing mem_limit should fail."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    # No mem_limit
                },
            },
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_MEMLIMIT_MISMATCH" for d in feedback.diagnostics)

    def test_missing_healthcheck(self, minimal_spec, tmp_path):
        """A service missing healthcheck should fail."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "mem_limit": "256M",
                    # No healthcheck
                },
            },
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_HEALTHCHECK_MISMATCH" for d in feedback.diagnostics)

    def test_network_mismatch(self, minimal_spec, tmp_path):
        """A service with wrong network should fail."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "mem_limit": "256M",
                    "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost/health"]},
                    "networks": ["wrong-net"],  # Spec says app-net
                },
            },
            "networks": {"wrong-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_NETWORK_MISMATCH" for d in feedback.diagnostics)

    def test_missing_network_in_compose(self, minimal_spec, tmp_path):
        """A network in spec but not in compose should fail."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "mem_limit": "256M",
                    "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost/health"]},
                    "networks": ["app-net"],
                },
            },
            "networks": {},  # No networks defined
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_NETWORK_MISSING" for d in feedback.diagnostics)

    def test_missing_test_suite_path(self, minimal_spec, tmp_path):
        """A test suite path that doesn't exist should warn."""
        # Add a test suite to minimal spec
        spec = minimal_spec.model_copy(deep=True)
        spec.test_suites = [
            TestSuite(name="smoke", path="tests/smoke/", framework="pytest"),
        ]

        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "mem_limit": "256M",
                    "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost/health"]},
                    "networks": ["app-net"],
                },
            },
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_MISSING_TEST_SUITE" for d in feedback.diagnostics)

    def test_missing_dockerfile(self, full_spec, matching_compose, tmp_path):
        """A service with build context but no Dockerfile should fail."""
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(matching_compose))

        # Don't create Dockerfiles — they should be detected as missing
        feedback = validate_code(full_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_MISSING_DOCKERFILE" for d in feedback.diagnostics)

    def test_bad_yaml_in_compose(self, minimal_spec, tmp_path):
        """A compose file with bad YAML should fail."""
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text("{bad: yaml: [broken}")

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G2_COMPOSE_SYNTAX" for d in feedback.diagnostics)

    def test_no_compose_file_found(self, minimal_spec, tmp_path):
        """No compose file in workspace should fail."""
        feedback = validate_code(minimal_spec, workspace_root=tmp_path)
        assert feedback.status == GateStatus.fail
        assert any(d.code == "G2_MISSING_FILE" for d in feedback.diagnostics)

    def test_port_mismatch(self, minimal_spec, tmp_path):
        """A service with wrong ports should warn."""
        spec = minimal_spec.model_copy(deep=True)
        spec.services[0].ports = [PortMapping(host=8080, container=8080)]

        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "mem_limit": "256M",
                    "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost/health"]},
                    "networks": ["app-net"],
                    "ports": ["9090:9090"],  # Wrong port
                },
            },
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_PORT_MISMATCH" for d in feedback.diagnostics)

    def test_depends_on_mismatch(self, minimal_spec, tmp_path):
        """A service with wrong depends_on should warn."""
        spec = minimal_spec.model_copy(deep=True)
        spec.services[0].depends_on = ["db"]
        spec.services.append(
            ServiceSpec(name="db", image="postgres:16-alpine", mem_limit="256M", networks=["app-net"])
        )

        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "mem_limit": "256M",
                    "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost/health"]},
                    "networks": ["app-net"],
                    "depends_on": [],  # Spec says depends_on: ["db"]
                },
                "db": {
                    "image": "postgres:16-alpine",
                    "mem_limit": "256M",
                    "networks": ["app-net"],
                },
            },
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert any(d.code == "G2_DEPENDS_MISMATCH" for d in feedback.diagnostics)

    def test_actions_are_specific(self, minimal_spec, tmp_path):
        """Actions should have specific field paths and suggested values."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    # Missing mem_limit and healthcheck
                },
            },
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert len(feedback.actions) > 0
        for action in feedback.actions:
            assert action.target_field is not None, f"Action missing target_field: {action.description}"
            assert action.description, "Action missing description"

    def test_spec_snapshot_included(self, minimal_spec, tmp_path):
        """Feedback should include a spec_snapshot."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    "mem_limit": "256M",
                    "healthcheck": {"test": ["CMD", "curl", "-f", "http://localhost/health"]},
                    "networks": ["app-net"],
                },
            },
            "networks": {"app-net": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(minimal_spec, workspace_root=tmp_path, compose_path=compose_path)
        assert feedback.spec_snapshot is not None
        assert feedback.spec_snapshot["name"] == "test-testbed"

    def test_never_crashes(self):
        """validate_code should never crash, even with garbage input."""
        try:
            feedback = validate_code(
                spec="not a spec",  # type: ignore
                workspace_root=Path("/nonexistent"),
            )
            assert feedback.status in (GateStatus.fail, GateStatus.error)
        except Exception:
            pytest.fail("validate_code crashed instead of returning GateFeedback")


# =========================================================================
# Integration tests: validate_code_from_file
# =========================================================================

class TestValidateCodeFromFile:
    def test_missing_spec_file(self, tmp_path):
        """A missing spec file should return an error feedback."""
        feedback = validate_code_from_file(
            spec_path=tmp_path / "nonexistent.json",
            workspace_root=tmp_path,
        )
        assert feedback.status == GateStatus.error
        assert any(d.code == "GATE_CRASH" for d in feedback.diagnostics)

    def test_invalid_json_spec(self, tmp_path):
        """An invalid JSON spec file should return an error feedback."""
        spec_path = tmp_path / "bad.json"
        spec_path.write_text("not json")
        feedback = validate_code_from_file(
            spec_path=spec_path,
            workspace_root=tmp_path,
        )
        assert feedback.status == GateStatus.error
        assert any(d.code == "GATE_CRASH" for d in feedback.diagnostics)

    def test_valid_spec_file(self, full_spec, matching_compose, tmp_path):
        """A valid spec file should work end-to-end."""
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(full_spec.model_dump_json(indent=2))

        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(matching_compose))

        # Create mock Dockerfiles
        (tmp_path / "src" / "mock-api").mkdir(parents=True)
        (tmp_path / "src" / "mock-api" / "Dockerfile").write_text("FROM python:3.12-slim\n")
        (tmp_path / "src" / "quic-client").mkdir(parents=True)
        (tmp_path / "src" / "quic-client" / "Dockerfile").write_text("FROM python:3.12-slim\n")

        # Create test directories
        (tmp_path / "tests" / "smoke").mkdir(parents=True)
        (tmp_path / "tests" / "smoke" / "test_smoke.py").write_text("def test_pass(): pass\n")
        (tmp_path / "tests" / "h3-handshake").mkdir(parents=True)
        (tmp_path / "tests" / "h3-handshake" / "test_h3.py").write_text("def test_pass(): pass\n")

        feedback = validate_code_from_file(
            spec_path=spec_path,
            workspace_root=tmp_path,
            compose_path=compose_path,
        )
        assert feedback.status == GateStatus.pass_, f"Expected pass, got fail: {[d.message for d in feedback.diagnostics]}"

    def test_attempt_number_tracking(self, full_spec, matching_compose, tmp_path):
        """Attempt number should be passed through correctly."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {"image": "nginx:latest"},  # Missing service
            },
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(full_spec, workspace_root=tmp_path, compose_path=compose_path, attempt_number=3)
        assert feedback.attempt_number == 3

    def test_previous_summary_tracking(self, full_spec, matching_compose, tmp_path):
        """Previous summary should be passed through correctly."""
        compose_path = tmp_path / "compose.yml"
        compose_path.write_text(yaml.dump(matching_compose))

        # Create mock Dockerfiles
        (tmp_path / "src" / "mock-api").mkdir(parents=True)
        (tmp_path / "src" / "mock-api" / "Dockerfile").write_text("FROM python:3.12-slim\n")
        (tmp_path / "src" / "quic-client").mkdir(parents=True)
        (tmp_path / "src" / "quic-client" / "Dockerfile").write_text("FROM python:3.12-slim\n")

        # Create test directories
        (tmp_path / "tests" / "smoke").mkdir(parents=True)
        (tmp_path / "tests" / "smoke" / "test_smoke.py").write_text("def test_pass(): pass\n")
        (tmp_path / "tests" / "h3-handshake").mkdir(parents=True)
        (tmp_path / "tests" / "h3-handshake" / "test_h3.py").write_text("def test_pass(): pass\n")

        feedback = validate_code(
            full_spec,
            workspace_root=tmp_path,
            compose_path=compose_path,
            previous_summary="[gate2.code_validator] status=fail diagnostics=3 actions=3 attempt=1",
        )
        assert feedback.metadata.get("previous_summary") is not None


# =========================================================================
# Edge cases
# =========================================================================

class TestEdgeCases:
    def test_empty_workspace(self, minimal_spec, tmp_path):
        """An empty workspace with no files should fail appropriately."""
        feedback = validate_code(minimal_spec, workspace_root=tmp_path)
        assert feedback.status == GateStatus.fail
        # Should have at least one diagnostic about missing compose
        assert len(feedback.diagnostics) > 0

    def test_compose_with_variable_build_paths(self, full_spec, tmp_path):
        """Compose with ${VAR}/path build contexts should resolve correctly."""
        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "name": "quic-edge-v2",
            "networks": {
                "edge-net": {"driver": "bridge"},
                "internal-net": {"driver": "bridge"},
            },
            "services": {
                "quic-edge-proxy": {
                    "image": "envoyproxy/envoy:v1.29-latest",
                    "mem_limit": "512M",
                    "healthcheck": {
                        "test": ["CMD", "bash", "-c", "exec 3<>/dev/tcp/localhost/9901; echo -e 'GET /ready HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3; grep -q 'LIVE' <&3"],
                        "interval": "15s",
                        "timeout": "5s",
                        "retries": 3,
                        "start_period": "10s",
                    },
                    "networks": ["edge-net", "internal-net"],
                },
                "caddy": {
                    "image": "caddy:2-alpine",
                    "mem_limit": "128M",
                    "healthcheck": {
                        "test": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
                        "interval": "15s",
                        "timeout": "5s",
                        "retries": 3,
                        "start_period": "10s",
                    },
                    "networks": ["edge-net", "internal-net"],
                },
                "mock-payment-api": {
                    "build": {"context": "${HOST_PROJECT_DIR}/src/mock-api", "dockerfile": "Dockerfile"},
                    "image": "quic-testbed/mock-api:latest",
                    "mem_limit": "256M",
                    "healthcheck": {
                        "test": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                        "interval": "15s",
                        "timeout": "5s",
                        "retries": 3,
                    },
                    "networks": ["internal-net"],
                    "depends_on": ["quic-edge-proxy"],
                },
                "quic-client": {
                    "build": {"context": "${HOST_PROJECT_DIR}/src/quic-client", "dockerfile": "Dockerfile"},
                    "image": "quic-testbed/quic-client:latest",
                    "mem_limit": "256M",
                    "healthcheck": {
                        "test": ["CMD-SHELL", "cat /proc/1/cmdline | grep -q tail || exit 1"],
                        "interval": "30s",
                        "timeout": "5s",
                        "retries": 2,
                        "start_period": "10s",
                    },
                    "networks": ["edge-net"],
                    "depends_on": ["quic-edge-proxy", "caddy"],
                },
                "test-runner": {
                    "image": "python:3.12-slim",
                    "mem_limit": "256M",
                    "healthcheck": {
                        "test": ["CMD-SHELL", "python3 -c 'import pytest' || exit 1"],
                        "interval": "30s",
                        "timeout": "5s",
                        "retries": 3,
                        "start_period": "30s",
                    },
                    "networks": ["edge-net", "internal-net"],
                    "depends_on": ["quic-edge-proxy", "caddy", "mock-payment-api", "quic-client"],
                },
            },
        }
        compose_path.write_text(yaml.dump(compose_data))

        # Create mock Dockerfiles at workspace-relative paths
        (tmp_path / "src" / "mock-api").mkdir(parents=True)
        (tmp_path / "src" / "mock-api" / "Dockerfile").write_text("FROM python:3.12-slim\n")
        (tmp_path / "src" / "quic-client").mkdir(parents=True)
        (tmp_path / "src" / "quic-client" / "Dockerfile").write_text("FROM python:3.12-slim\n")

        # Create test directories
        (tmp_path / "tests" / "smoke").mkdir(parents=True)
        (tmp_path / "tests" / "smoke" / "test_smoke.py").write_text("def test_pass(): pass\n")
        (tmp_path / "tests" / "h3-handshake").mkdir(parents=True)
        (tmp_path / "tests" / "h3-handshake" / "test_h3.py").write_text("def test_pass(): pass\n")

        feedback = validate_code(full_spec, workspace_root=tmp_path, compose_path=compose_path)
        # The build context comparison should handle the variable prefix
        build_mismatches = [d for d in feedback.diagnostics if d.code == "G2_BUILD_MISMATCH"]
        assert len(build_mismatches) == 0, f"Unexpected build mismatches: {[d.message for d in build_mismatches]}"
        assert feedback.status == GateStatus.pass_, f"Expected pass: {[d.message for d in feedback.diagnostics]}"

    def test_multiple_issues_produce_multiple_actions(self, tmp_path):
        """Multiple issues should produce multiple actions."""
        spec = TestbedSpec(
            name="multi-issue",
            services=[
                ServiceSpec(name="web", image="nginx:latest", mem_limit="256M", networks=["net1"]),
                ServiceSpec(name="api", image="my-api:latest", mem_limit="512M", networks=["net1"]),
            ],
            infrastructure=InfrastructureSpec(networks={"net1": {"driver": "bridge"}}),
        )

        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                "web": {
                    "image": "nginx:latest",
                    # Missing mem_limit, healthcheck
                },
                "api": {
                    "image": "my-api:latest",
                    # Missing mem_limit, healthcheck
                },
            },
            "networks": {"net1": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(spec, workspace_root=tmp_path, compose_path=compose_path)
        assert len(feedback.diagnostics) >= 2
        assert len(feedback.actions) > 0

    def test_actions_capped(self, tmp_path):
        """Actions should be capped at _MAX_ACTIONS."""
        spec = TestbedSpec(
            name="many-issues",
            services=[
                ServiceSpec(name=f"svc{i}", image=f"img{i}:latest", mem_limit="256M", networks=["net1"])
                for i in range(10)
            ],
            infrastructure=InfrastructureSpec(networks={"net1": {"driver": "bridge"}}),
        )

        compose_path = tmp_path / "compose.yml"
        compose_data = {
            "services": {
                f"svc{i}": {"image": f"img{i}:latest"}  # All missing mem_limit, healthcheck
                for i in range(10)
            },
            "networks": {"net1": {"driver": "bridge"}},
        }
        compose_path.write_text(yaml.dump(compose_data))

        feedback = validate_code(spec, workspace_root=tmp_path, compose_path=compose_path)
        # Actions should be capped (max 7)
        assert len(feedback.actions) <= 7
