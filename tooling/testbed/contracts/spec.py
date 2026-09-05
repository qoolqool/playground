"""
TestbedSpec — the universal contract for the Gated AI Testbed system.

Every gate (Spec Parser, Code Validator, Guardrail Vetter, Runtime Test)
produces and/or consumes a TestbedSpec. This ensures a consistent,
machine-readable representation of what a testbed should be.

The spec is designed to be:
- LLM-friendly: flat-ish structure, clear field names, optional descriptions
- Validation-friendly: Pydantic v2 with strict type checks
- Extensible: new fields can be added without breaking existing gates
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NetworkMode(str, Enum):
    """How a service connects to the Docker network topology."""
    bridge = "bridge"
    host = "host"
    overlay = "overlay"
    none = "none"
    custom = "custom"


class RestartPolicy(str, Enum):
    always = "always"
    unless_stopped = "unless-stopped"
    on_failure = "on-failure"
    no = "no"


class TestFramework(str, Enum):
    pytest = "pytest"
    unittest = "unittest"
    go_test = "go_test"
    custom = "custom"


# ---------------------------------------------------------------------------
# Component specs
# ---------------------------------------------------------------------------

class PortMapping(BaseModel):
    """A single port mapping (host:container)."""
    host: int = Field(..., ge=1, le=65535, description="Host port")
    container: int = Field(..., ge=1, le=65535, description="Container port")
    protocol: str = Field("tcp", pattern=r"^(tcp|udp)$")


class VolumeMount(BaseModel):
    """A single volume or bind mount."""
    source: str = Field(..., description="Host path or volume name")
    target: str = Field(..., description="Container path")
    mode: str = Field("rw", pattern=r"^(rw|ro)$")


class ServiceSpec(BaseModel):
    """Specification for a single Docker service in the testbed."""
    name: str = Field(..., min_length=1, description="Service name (used as container name)")
    image: str = Field(..., min_length=1, description="Docker image (e.g. postgres:16-alpine)")
    description: Optional[str] = Field(None, description="Why this service exists, what alternatives were considered")
    build: Optional[str] = Field(None, description="Path to Dockerfile for local build")
    command: Optional[str] = Field(None, description="Override command/entrypoint")
    ports: list[PortMapping] = Field(default_factory=list, description="Exposed ports")
    volumes: list[VolumeMount] = Field(default_factory=list, description="Volume mounts")
    environment: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    networks: list[str] = Field(default_factory=list, description="Networks this service belongs to")
    depends_on: list[str] = Field(default_factory=list, description="Services that must start first")
    mem_limit: Optional[str] = Field(None, description="Memory limit (e.g. 512M, 2G)")
    cpus: Optional[float] = Field(None, ge=0.1, le=64, description="CPU limit")
    restart: RestartPolicy = Field(RestartPolicy.unless_stopped, description="Restart policy")
    healthcheck: Optional[dict[str, Any]] = Field(None, description="Docker healthcheck config")
    network_mode: NetworkMode = Field(NetworkMode.custom, description="Network mode")
    labels: dict[str, str] = Field(default_factory=dict, description="Docker labels")
    extra_hosts: list[str] = Field(default_factory=list, description="Extra host entries")
    entrypoint: Optional[str] = Field(None, description="Custom entrypoint script")

    @field_validator("mem_limit")
    @classmethod
    def validate_mem_limit(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            import re
            if not re.match(r"^\d+(\.\d+)?[kKmMgGtT]?$", v):
                raise ValueError(
                    f"Invalid mem_limit format: '{v}'. Use format like '512M', '2G', '1024m'."
                )
        return v


class TestSuite(BaseModel):
    """Specification for a test suite to run against the testbed."""
    name: str = Field(..., min_length=1, description="Test suite name")
    path: str = Field(..., min_length=1, description="Path to test files (relative to project root)")
    framework: TestFramework = Field(TestFramework.pytest, description="Test framework")
    markers: list[str] = Field(default_factory=list, description="Pytest markers to select")
    env: dict[str, str] = Field(default_factory=dict, description="Extra env vars for tests")
    timeout_seconds: int = Field(300, ge=1, le=3600, description="Max test duration")
    required_services: list[str] = Field(
        default_factory=list,
        description="Services that must be healthy before running",
    )
    tags: list[str] = Field(default_factory=list, description="Arbitrary tags for filtering")


class InfrastructureSpec(BaseModel):
    """Networks, volumes, and other infrastructure."""
    networks: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Docker networks (name → config)",
    )
    volumes: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Docker volumes (name → config)",
    )
    secrets: list[str] = Field(default_factory=list, description="Required secret files/paths")


class ConstraintSpec(BaseModel):
    """Resource and operational constraints."""
    memory_per_service: dict[str, str] = Field(
        default_factory=dict,
        description="Per-service memory limits (service → limit string)",
    )
    global_mem_limit: Optional[str] = Field(
        None, description="Global memory cap for the entire testbed"
    )
    required_free_disk_gb: int = Field(5, ge=1, description="Minimum free disk space (GB)")
    max_containers: int = Field(50, ge=1, le=200, description="Maximum number of containers")
    privileged_services: list[str] = Field(
        default_factory=list,
        description="Services requiring privileged mode",
    )


class GuardrailSpec(BaseModel):
    """Security, compliance, and policy guardrails."""
    no_host_network: bool = Field(True, description="Disallow host network mode")
    no_privileged: bool = Field(True, description="Disallow privileged containers")
    required_labels: list[str] = Field(
        default_factory=lambda: ["project", "managed-by"],
        description="Labels that must be present on every service",
    )
    allowed_images: list[str] = Field(
        default_factory=list,
        description="Allowlist of Docker image prefixes (empty = allow all)",
    )
    blocked_images: list[str] = Field(
        default_factory=list,
        description="Blocklist of Docker image prefixes",
    )
    max_exposed_ports: int = Field(10, ge=0, le=100, description="Maximum number of exposed ports")
    require_healthcheck: bool = Field(True, description="Require healthcheck on all services")
    require_mem_limit: bool = Field(True, description="Require memory limits on all services")


# ---------------------------------------------------------------------------
# Inter-component callflow contracts
# ---------------------------------------------------------------------------

class ExpectMode(str, Enum):
    """How an expected result is checked. Keeps the schema protocol-agnostic.

    - exact:        parsed response must equal the expected value
    - contains:     expected dict must be a recursive subset of the response
    - success:      only the status code must match; body is ignored
    - verify_hook:  a project-owned checker runs and decides pass/fail
    """
    exact = "exact"
    contains = "contains"
    success = "success"
    verify_hook = "verify_hook"


class ContractExpect(BaseModel):
    """The expected outcome of one inter-component call."""
    mode: ExpectMode = Field(
        ExpectMode.exact,
        description="How the response is checked against the expected result",
    )
    status: Optional[int] = Field(
        None,
        ge=100,
        le=599,
        description="Expected status/response code (when the protocol has one)",
    )
    body: Optional[Any] = Field(
        None,
        description="Expected response body for exact/contains modes",
    )
    verify_hook: Optional[str] = Field(
        None,
        description="Path (relative to workspace) to a project-owned checker for verify_hook mode",
    )


class ContractEdge(BaseModel):
    """One directional inter-component call to verify at runtime.

    The edge declares WHAT should happen. A protocol adapter decides HOW to
    make the call. This keeps the schema generic: adding a protocol never
    requires changing this model, only registering an adapter.
    """
    id: str = Field(..., min_length=1, description="Unique edge id, e.g. 'consumer->api.summary'")
    source: str = Field(
        ..., min_length=1, description="Caller service name (must match a declared service)"
    )
    target: str = Field(
        ..., min_length=1, description="Callee service name (must match a declared service)"
    )
    protocol: str = Field(
        "http",
        min_length=1,
        description="Adapter discriminator: http, grpc, dlt-invoke, verify-hook, ...",
    )
    description: Optional[str] = Field(None, description="Why this call exists")
    request: dict[str, Any] = Field(
        default_factory=dict,
        description="Protocol-specific request spec (http: method + path)",
    )
    expect: ContractExpect = Field(
        default_factory=ContractExpect,
        description="Expected result for this call",
    )


class CallflowSpec(BaseModel):
    """The declared inter-component callflow: the expected result to verify.

    The spec carries the callflow as data; it never executes it. Gate 2
    validates the shape statically, and Gate 4 dispatches each edge to a
    protocol adapter or a project-owned verify hook.
    """
    edges: list[ContractEdge] = Field(
        default_factory=list,
        description="Ordered list of inter-component call contracts",
    )
    entry: Optional[str] = Field(
        None,
        description="Edge id to start the walk when ordering matters (future use)",
    )


# ---------------------------------------------------------------------------
# Top-level spec
# ---------------------------------------------------------------------------

class TestbedSpec(BaseModel):
    """Complete specification for a gated AI testbed.

    This is the universal contract. Every gate produces or consumes this type.
    """
    # Metadata
    name: str = Field(..., min_length=1, description="Human-readable testbed name")
    version: str = Field("0.1.0", description="Semantic version of this spec")
    description: str = Field("", description="Purpose and scope of this testbed")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")

    # Core components
    services: list[ServiceSpec] = Field(
        ..., min_length=1, description="Docker services in the testbed"
    )
    test_suites: list[TestSuite] = Field(
        default_factory=list, description="Test suites to validate the testbed"
    )

    # Infrastructure
    infrastructure: InfrastructureSpec = Field(
        default_factory=InfrastructureSpec,
        description="Networks, volumes, and infrastructure",
    )

    # Constraints
    constraints: ConstraintSpec = Field(
        default_factory=ConstraintSpec,
        description="Resource and operational constraints",
    )

    # Guardrails
    guardrails: GuardrailSpec = Field(
        default_factory=GuardrailSpec,
        description="Security and policy guardrails",
    )

    # Inter-component callflow contracts
    callflow: CallflowSpec = Field(
        default_factory=CallflowSpec,
        description="Declared inter-component callflow (expected result to verify at runtime)",
    )

    # Extensibility
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata for extensibility",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def check_service_names_unique(self) -> "TestbedSpec":
        names = [s.name for s in self.services]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"Duplicate service names: {duplicates}")
        return self

    @model_validator(mode="after")
    def check_depends_on_refer_to_existing(self) -> "TestbedSpec":
        valid_names = {s.name for s in self.services}
        for svc in self.services:
            for dep in svc.depends_on:
                if dep not in valid_names:
                    raise ValueError(
                        f"Service '{svc.name}' depends on '{dep}', "
                        f"but no service named '{dep}' exists"
                    )
        return self

    @model_validator(mode="after")
    def check_test_required_services_exist(self) -> "TestbedSpec":
        valid_names = {s.name for s in self.services}
        for ts in self.test_suites:
            for req in ts.required_services:
                if req not in valid_names:
                    raise ValueError(
                        f"Test suite '{ts.name}' requires service '{req}', "
                        f"but no service named '{req}' exists"
                    )
        return self

    def service_names(self) -> list[str]:
        """Convenience: list all service names."""
        return [s.name for s in self.services]

    def get_service(self, name: str) -> Optional[ServiceSpec]:
        """Convenience: find a service by name."""
        for s in self.services:
            if s.name == name:
                return s
        return None

    # ------------------------------------------------------------------
    # Callflow validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def check_callflow_edge_ids_unique(self) -> "TestbedSpec":
        seen: dict[str, int] = {}
        for edge in self.callflow.edges:
            seen[edge.id] = seen.get(edge.id, 0) + 1
        dups = {k: v for k, v in seen.items() if v > 1}
        if dups:
            raise ValueError(f"Duplicate callflow edge ids: {list(dups)}")
        return self

    @model_validator(mode="after")
    def check_callflow_services_exist(self) -> "TestbedSpec":
        valid_names = {s.name for s in self.services}
        for edge in self.callflow.edges:
            for role in (edge.source, edge.target):
                if role not in valid_names:
                    raise ValueError(
                        f"Callflow edge '{edge.id}' references service '{role}' "
                        f"which is not declared in services"
                    )
        if self.callflow.entry and self.callflow.entry not in {
            e.id for e in self.callflow.edges
        }:
            raise ValueError(
                f"Callflow entry '{self.callflow.entry}' does not match any edge id"
            )
        return self

    def callflow_edges(self) -> list[ContractEdge]:
        """Convenience: list all declared callflow edges."""
        return list(self.callflow.edges)
