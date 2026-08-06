"""Gate 1 — Spec Parser & Linter.

YOU OWN THE QUALITY GATE. This is not optional documentation — it is a mandatory
checkpoint you must call yourself after every spec change.

The agent (AI model) reads the user's natural language description, studies the
PRD and INFRA docs, performs critical service analysis, and produces a structured
TestbedSpec as JSON. Gate 1 then:

  1. Validates the spec against the TestbedSpec Pydantic model
  2. Cross-references against the knowledgebase (gotchas, patterns, decisions)
  3. Returns structured GateFeedback with diagnostics and actions

The gate never crashes — it always returns a GateFeedback.

Hard rule:
  After every spec change → call validate_spec() → if status != "pass",
  apply the returned actions, then re-validate. Only proceed to code changes
  when status == "pass".

Design principle: The agent IS the model. No Ollama call needed for extraction.
The agent provides the structured spec directly. Gate 1's value is in
validation + KB cross-reference, not LLM extraction.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from testbed.contracts.spec import TestbedSpec
from testbed.contracts.feedback import (
    GateFeedback,
    GateStatus,
    Location,
    Severity,
    Diagnostic,
    Action,
    ActionKind,
)
from testbed.gates.kb_search import search_kb

# ---------------------------------------------------------------------------
# Error code registry
# ---------------------------------------------------------------------------

ERROR_CODES = {
    # Extraction errors
    "E001": "No spec content provided",
    "E002": "Input is not valid JSON",
    "E003": "Input is valid JSON but not a valid spec structure",
    # Validation errors
    "E010": "Missing required field",
    "E011": "Field validation error",
    "E012": "Model validation error (cross-field)",
    "E020": "No services defined",
    "E021": "Duplicate service name",
    "E022": "Service depends on non-existent service",
    "E023": "Test suite requires non-existent service",
    "E030": "Memory limit format invalid",
    "E031": "Port number out of range",
    # Warnings
    "W001": "No test suites defined",
    "W002": "No memory limits set on services",
    "W003": "No healthcheck configured",
    "W004": "No networks defined",
    "W005": "No description provided",
    "W006": "No tags provided",
    "W007": "Service missing description — document why it exists",
}

# Maximum actions to return (keep focused — agents handle short lists better)
_MAX_ACTIONS = 7


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------

def _parse_input(raw_text: str) -> tuple[Optional[dict], list[Diagnostic]]:
    """Parse raw input into a spec dictionary.

    Tries JSON first. If that fails, returns a diagnostic telling the agent
    to provide a JSON spec. No keyword fallback — the agent is the model.
    """
    diagnostics: list[Diagnostic] = []

    if not raw_text or not raw_text.strip():
        diagnostics.append(Diagnostic(
            code="E001",
            severity=Severity.critical,
            message="No spec content provided. The agent must provide a structured TestbedSpec as JSON.",
            location=Location(field="raw_input"),
        ))
        return None, diagnostics

    text = raw_text.strip()

    # Try JSON parse
    try:
        spec_dict = json.loads(text)
        if not isinstance(spec_dict, dict):
            raise ValueError("JSON root must be an object")
        return spec_dict, diagnostics
    except json.JSONDecodeError as exc:
        diagnostics.append(Diagnostic(
            code="E002",
            severity=Severity.error,
            message=f"Input is not valid JSON: {exc}. "
                    f"The agent must provide a structured TestbedSpec as JSON. "
                    f"Markdown specs are for human reading only — the agent extracts "
                    f"the structured spec and passes it as JSON.",
            location=Location(field="raw_input"),
            detail=f"Parse error at line {exc.lineno}, column {exc.colno}: {exc.msg}",
        ))
        return None, diagnostics


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_spec(spec_dict: dict) -> tuple[Optional[TestbedSpec], list[Diagnostic], list[Action]]:
    """Validate a spec dictionary against the TestbedSpec model.

    Returns (validated_spec, diagnostics, actions).
    Actions are sorted by priority (0=urgent first) and capped at _MAX_ACTIONS.
    """
    diagnostics: list[Diagnostic] = []
    actions: list[Action] = []

    # --- Structural checks before Pydantic ---

    # Check for services
    if "services" not in spec_dict or not spec_dict.get("services"):
        diagnostics.append(Diagnostic(
            code="E020",
            severity=Severity.critical,
            message="No services defined. A testbed must have at least one service.",
            location=Location(field="services"),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description="Define at least one Docker service with a name and image.",
            target_field="services",
            suggested_value=[{"name": "app", "image": "my-app:latest"}],
            priority=0,
        ))
        return None, diagnostics, actions

    # Check for service names
    for i, svc in enumerate(spec_dict.get("services", [])):
        if not svc.get("name"):
            diagnostics.append(Diagnostic(
                code="E010",
                severity=Severity.error,
                message=f"Service at index {i} is missing required field 'name'.",
                location=Location(field=f"services[{i}].name"),
            ))
            actions.append(Action(
                kind=ActionKind.add,
                description=f"Add a 'name' field to service at index {i}.",
                target_field=f"services[{i}].name",
                suggested_value="my-service",
                priority=1,
            ))

    # Check for service images
    for i, svc in enumerate(spec_dict.get("services", [])):
        if not svc.get("image"):
            svc_name = svc.get("name", f"index {i}")
            diagnostics.append(Diagnostic(
                code="E010",
                severity=Severity.error,
                message=f"Service '{svc_name}' is missing required field 'image'.",
                location=Location(field=f"services[{i}].image"),
            ))
            actions.append(Action(
                kind=ActionKind.add,
                description=f"Add an 'image' field to service '{svc_name}'.",
                target_field=f"services[{i}].image",
                suggested_value="my-image:latest",
                priority=1,
            ))

    # If we already have critical issues, don't attempt Pydantic validation
    if any(d.severity == Severity.critical for d in diagnostics):
        return None, diagnostics, _sort_and_cap_actions(actions)

    # --- Pydantic validation ---
    try:
        spec = TestbedSpec(**spec_dict)
        return spec, diagnostics, _sort_and_cap_actions(actions)
    except Exception as exc:
        error_msg = str(exc)
        diagnostics.append(Diagnostic(
            code="E012",
            severity=Severity.error,
            message=f"Spec validation failed: {error_msg}",
            detail=error_msg,
        ))
        actions.append(Action(
            kind=ActionKind.fix,
            description=f"Fix validation errors: {error_msg}",
            priority=0,
        ))
        return None, diagnostics, _sort_and_cap_actions(actions)


# ---------------------------------------------------------------------------
# Warnings (non-blocking) — now also produce actions
# ---------------------------------------------------------------------------

def _add_warnings(spec: TestbedSpec, diagnostics: list[Diagnostic], actions: list[Action]) -> None:
    """Add warning-level diagnostics and corresponding actions for missing optional fields."""
    if not spec.test_suites:
        diagnostics.append(Diagnostic(
            code="W001",
            severity=Severity.warning,
            message="No test suites defined. Add at least one test suite to validate the testbed.",
            location=Location(field="test_suites"),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description="Add a smoke test suite to validate basic connectivity.",
            target_field="test_suites",
            suggested_value=[{
                "name": "smoke",
                "path": "tests/smoke/",
                "framework": "pytest",
                "required_services": [s.name for s in spec.services[:3]],
                "timeout_seconds": 60,
            }],
            priority=3,
        ))

    if not spec.description:
        diagnostics.append(Diagnostic(
            code="W005",
            severity=Severity.info,
            message="No description provided. Adding a description helps humans understand the testbed's purpose.",
            location=Location(field="description"),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description="Add a description explaining the testbed's purpose, scope, and phase boundaries.",
            target_field="description",
            suggested_value="Phase 1 testbed for ...",
            priority=5,
        ))

    if not spec.tags:
        diagnostics.append(Diagnostic(
            code="W006",
            severity=Severity.info,
            message="No tags provided. Tags help with categorization and search.",
            location=Location(field="tags"),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description="Add categorization tags (e.g. quic, http3, phase-1).",
            target_field="tags",
            suggested_value=["phase-1", "networking"],
            priority=6,
        ))

    services_without_mem = [s.name for s in spec.services if not s.mem_limit]
    if services_without_mem:
        diagnostics.append(Diagnostic(
            code="W002",
            severity=Severity.warning,
            message=f"Services missing memory limits: {', '.join(services_without_mem)}. "
                    f"Uncapped containers can cause OOM on resource-constrained hosts.",
            location=Location(field="services"),
        ))
        for svc_name in services_without_mem[:3]:  # cap at 3 to keep list focused
            actions.append(Action(
                kind=ActionKind.fix,
                description=f"Set memory limit on '{svc_name}'.",
                target_field=f"services.{svc_name}.mem_limit",
                suggested_value="256M",
                priority=3,
            ))

    services_without_healthcheck = [
        s.name for s in spec.services if not s.healthcheck
    ]
    if services_without_healthcheck and spec.guardrails.require_healthcheck:
        diagnostics.append(Diagnostic(
            code="W003",
            severity=Severity.warning,
            message=f"Services missing healthcheck: {', '.join(services_without_healthcheck)}. "
                    f"Healthchecks enable dependency ordering and failure detection.",
            location=Location(field="services"),
        ))
        for svc_name in services_without_healthcheck[:3]:
            actions.append(Action(
                kind=ActionKind.add,
                description=f"Add healthcheck to '{svc_name}'.",
                target_field=f"services.{svc_name}.healthcheck",
                suggested_value={
                    "test": ["CMD", "curl", "-f", "http://localhost:8080/health"],
                    "interval": "15s",
                    "timeout": "5s",
                    "retries": 3,
                },
                priority=3,
            ))

    if not spec.infrastructure.networks:
        diagnostics.append(Diagnostic(
            code="W004",
            severity=Severity.info,
            message="No custom networks defined. Services will use the default network.",
            location=Location(field="infrastructure.networks"),
        ))
        actions.append(Action(
            kind=ActionKind.add,
            description="Define at least one custom network for service isolation.",
            target_field="infrastructure.networks",
            suggested_value={"app-net": {"driver": "bridge"}},
            priority=6,
        ))

    services_without_desc = [s.name for s in spec.services if not s.description]
    if services_without_desc:
        diagnostics.append(Diagnostic(
            code="W007",
            severity=Severity.info,
            message=f"Services missing description: {', '.join(services_without_desc)}. "
                    f"Every service should document why it exists and what alternatives were considered.",
            location=Location(field="services"),
        ))
        for svc_name in services_without_desc[:3]:
            actions.append(Action(
                kind=ActionKind.add,
                description=f"Add a description to '{svc_name}' explaining why it exists and what alternatives were considered.",
                target_field=f"services.{svc_name}.description",
                suggested_value=f"Why {svc_name} exists and what alternatives were considered.",
                priority=5,
            ))


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------

def _sort_and_cap_actions(actions: list[Action]) -> list[Action]:
    """Sort actions by priority (ascending) and cap at _MAX_ACTIONS."""
    actions.sort(key=lambda a: a.priority)
    return actions[:_MAX_ACTIONS]


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

def validate_spec(
    spec_dict: dict,
    kb_dirs: Optional[list[Path]] = None,
    attempt_number: int = 1,
    previous_summary: Optional[str] = None,
) -> tuple[Optional[TestbedSpec], GateFeedback]:
    """Validate a spec dictionary and cross-reference against the KB.

    This is the primary entry point for the agent-provided spec path.
    The agent reads the user's requirements, performs critical service analysis,
    produces a structured TestbedSpec as JSON, and passes it here for
    validation + KB cross-reference.

    Hard rule: After every spec change, call this function. If status != "pass",
    apply the returned actions, then re-validate. Only proceed to code changes
    when status == "pass".

    Args:
        spec_dict: The structured TestbedSpec as a Python dict (from agent).
        kb_dirs: Optional list of KB root directories to search for
                 relevant gotchas/patterns/decisions.
        attempt_number: Which attempt this is (for tracking iteration).
                        Pass incremented value on consecutive calls.
        previous_summary: One-line summary of the previous feedback attempt.
                          Pass the previous feedback's summary() on retry so
                          consecutive calls feel like a conversation.

    Returns:
        Tuple of (optional validated TestbedSpec, GateFeedback).
    """
    start_time = time.time()
    feedback_kwargs = {
        "gate_id": "gate1.spec_parser",
        "gate_version": "0.1.0",
        "raw_input": json.dumps(spec_dict, indent=2),
    }

    # Phase 1: Validate
    validated_spec, diagnostics, actions = _validate_spec(spec_dict)

    if validated_spec is not None:
        # Add warnings (also produces actions)
        _add_warnings(validated_spec, diagnostics, actions)

        # Phase 2: KB cross-reference
        if kb_dirs:
            try:
                kb_diagnostics = search_kb(validated_spec, kb_dirs)
                diagnostics.extend(kb_diagnostics)
            except Exception as exc:
                diagnostics.append(Diagnostic(
                    code="KB_ERR",
                    severity=Severity.info,
                    message=f"KB search failed: {exc}",
                ))

        # Sort and cap actions
        actions = _sort_and_cap_actions(actions)

        duration_ms = int((time.time() - start_time) * 1000)
        has_blockers = any(
            d.severity in (Severity.critical, Severity.error) for d in diagnostics
        )

        # Build metadata with iteration context
        metadata = {"attempt_number": attempt_number}
        if previous_summary:
            metadata["previous_summary"] = previous_summary

        feedback = GateFeedback(
            status=GateStatus.fail if has_blockers else GateStatus.pass_,
            diagnostics=diagnostics,
            actions=actions,
            spec_snapshot=validated_spec.model_dump(mode="json"),
            duration_ms=duration_ms,
            attempt_number=attempt_number,
            metadata=metadata,
            **feedback_kwargs,
        )
        return validated_spec, feedback
    else:
        # Sort and cap actions
        actions = _sort_and_cap_actions(actions)

        duration_ms = int((time.time() - start_time) * 1000)
        metadata = {"attempt_number": attempt_number}
        if previous_summary:
            metadata["previous_summary"] = previous_summary

        feedback = GateFeedback(
            status=GateStatus.fail,
            diagnostics=diagnostics,
            actions=actions,
            duration_ms=duration_ms,
            attempt_number=attempt_number,
            metadata=metadata,
            **feedback_kwargs,
        )
        return None, feedback


def parse_spec(
    raw_text: str,
    use_llm: bool = True,
    timeout_seconds: int = 30,
    kb_dirs: Optional[list[Path]] = None,
    attempt_number: int = 1,
    previous_summary: Optional[str] = None,
) -> tuple[Optional[TestbedSpec], GateFeedback]:
    """Parse raw text into a TestbedSpec.

    This function exists for backward compatibility and the CLI `parse` command.
    It tries to parse the input as JSON first. If that fails and use_llm is True,
    it attempts LLM extraction (Ollama). If LLM is unavailable, it returns a
    diagnostic telling the agent to provide a JSON spec.

    The preferred path is validate_spec() — the agent provides the spec directly.

    Args:
        raw_text: Raw input text (JSON preferred, markdown accepted for LLM path).
        use_llm: Whether to attempt LLM extraction if input is not JSON.
        timeout_seconds: Timeout for LLM call.
        kb_dirs: Optional list of KB root directories to search.
        attempt_number: Which attempt this is (for tracking iteration).
        previous_summary: One-line summary of the previous feedback attempt.

    Returns:
        Tuple of (optional validated TestbedSpec, GateFeedback).
    """
    start_time = time.time()
    feedback_kwargs = {
        "gate_id": "gate1.spec_parser",
        "gate_version": "0.1.0",
        "raw_input": raw_text,
    }

    # Try JSON first
    spec_dict, parse_diagnostics = _parse_input(raw_text)

    # If JSON parse failed and LLM is requested, try LLM extraction
    if spec_dict is None and use_llm:
        llm_spec, llm_diagnostics = _try_llm_extraction(raw_text, timeout_seconds)
        if llm_spec is not None:
            spec_dict = llm_spec
            parse_diagnostics.extend(llm_diagnostics)
        else:
            parse_diagnostics.extend(llm_diagnostics)

    if spec_dict is None:
        # No spec could be extracted — return failure
        duration_ms = int((time.time() - start_time) * 1000)
        metadata = {"attempt_number": attempt_number}
        if previous_summary:
            metadata["previous_summary"] = previous_summary

        feedback = GateFeedback(
            status=GateStatus.fail,
            diagnostics=parse_diagnostics,
            actions=[
                Action(
                    kind=ActionKind.fix,
                    description="Provide the TestbedSpec as JSON. The agent should read the user's "
                                "requirements, perform critical service analysis, and produce a "
                                "structured spec directly.",
                    target_field="raw_input",
                    priority=0,
                ),
            ],
            duration_ms=duration_ms,
            attempt_number=attempt_number,
            metadata=metadata,
            **feedback_kwargs,
        )
        return None, feedback

    # Validate + KB cross-reference
    return validate_spec(
        spec_dict,
        kb_dirs=kb_dirs,
        attempt_number=attempt_number,
        previous_summary=previous_summary,
    )


# ---------------------------------------------------------------------------
# LLM extraction (secondary path, for backward compatibility)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are a testbed specification parser. Your job is to extract a structured
TestbedSpec from the user's natural language description.

The TestbedSpec has these fields:
- name (required): short name for the testbed
- version (optional, default "0.1.0"): semantic version
- description (optional): purpose and scope
- tags (optional): list of categorization tags
- services (required, at least 1): list of service objects, each with:
  - name (required): service/container name
  - image (required): Docker image
  - build (optional): path to Dockerfile
  - command (optional): override command
  - ports (optional): list of {{"host": int, "container": int, "protocol": "tcp"|"udp"}}
  - volumes (optional): list of {{"source": str, "target": str, "mode": "rw"|"ro"}}
  - environment (optional): dict of env vars
  - networks (optional): list of network names
  - depends_on (optional): list of service names
  - mem_limit (optional): memory limit string like "512M", "2G"
  - cpus (optional): CPU limit as float
  - restart (optional): "always", "unless-stopped", "on-failure", "no"
  - healthcheck (optional): dict with test/interval/timeout/retries
  - network_mode (optional): "bridge", "host", "overlay", "none", "custom"
  - labels (optional): dict of label key-value pairs
  - extra_hosts (optional): list of "host:ip" strings
  - entrypoint (optional): custom entrypoint
- test_suites (optional): list of test suite objects, each with:
  - name (required): test suite name
  - path (required): path to test files
  - framework (optional): "pytest", "unittest", "go_test", "custom"
  - markers (optional): list of pytest markers
  - env (optional): dict of extra env vars
  - timeout_seconds (optional, default 300): max test duration
  - required_services (optional): list of service names needed
  - tags (optional): list of tags
- infrastructure (optional): object with:
  - networks (optional): dict of network name -> config
  - volumes (optional): dict of volume name -> config
  - secrets (optional): list of secret paths
- constraints (optional): object with:
  - memory_per_service (optional): dict of service -> limit string
  - global_mem_limit (optional): global memory cap
  - required_free_disk_gb (optional, default 5)
  - max_containers (optional, default 50)
  - privileged_services (optional): list of privileged service names
- guardrails (optional): object with:
  - no_host_network (optional, default true)
  - no_privileged (optional, default true)
  - required_labels (optional, default ["project", "managed-by"])
  - allowed_images (optional): list of allowed image prefixes
  - blocked_images (optional): list of blocked image prefixes
  - max_exposed_ports (optional, default 10)
  - require_healthcheck (optional, default true)
  - require_mem_limit (optional, default true)

Output ONLY valid JSON. No markdown, no explanation, no backticks.
The JSON must be parseable by json.loads().

User's description:
"""


def _call_llm(prompt: str, timeout_seconds: int = 30) -> Optional[str]:
    """Call the local Ollama API for structured extraction."""
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": "qwen2.5:0.5b",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,
        },
    }).encode()

    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            result = json.loads(resp.read().decode())
            return result.get("response", "")
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError, TimeoutError) as exc:
        return None


def _extract_json_from_llm_output(text: str) -> Optional[dict]:
    """Extract a JSON object from LLM output, handling common wrapping."""
    text = text.strip()

    # Try direct parse first
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try to find JSON between triple backticks
    if "```" in text:
        import re
        matches = re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        for m in matches:
            m = m.strip()
            if m.startswith("{"):
                try:
                    return json.loads(m)
                except json.JSONDecodeError:
                    pass

    # Try to find first { ... } block
    import re
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def _try_llm_extraction(
    raw_text: str,
    timeout_seconds: int = 30,
) -> tuple[Optional[dict], list[Diagnostic]]:
    """Attempt LLM-based extraction from raw text.

    Returns (spec_dict_or_None, diagnostics).
    """
    diagnostics: list[Diagnostic] = []

    llm_prompt = EXTRACTION_PROMPT + raw_text
    llm_output = _call_llm(llm_prompt, timeout_seconds)

    if llm_output is None:
        diagnostics.append(Diagnostic(
            code="E004",
            severity=Severity.warning,
            message="LLM extraction unavailable (Ollama not reachable). "
                    "The agent should provide the TestbedSpec as JSON directly.",
        ))
        return None, diagnostics

    parsed = _extract_json_from_llm_output(llm_output)
    if parsed is None:
        diagnostics.append(Diagnostic(
            code="E002",
            severity=Severity.warning,
            message="LLM output was not valid JSON. "
                    "The agent should provide the TestbedSpec as JSON directly.",
            detail=f"Raw LLM output (first 500 chars): {llm_output[:500]}",
        ))
        return None, diagnostics

    return parsed, diagnostics
