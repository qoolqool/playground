# Gated AI Testbed — MVP

A gated architecture for creating, validating, and iterating on AI-generated
testbed specifications. Each gate produces structured, machine-readable feedback
that enables autonomous iteration.

## Architecture

```
[ USER SPEC ] ──→ Gate 1: Spec Parser ──→ Gate 2: Code Validator
                                              ↓
                    [ REPO BASE ] ←── Gate 4: Runtime Test ←── Gate 3: Guardrail Vetting
```

**This MVP implements:**
- Shared contracts (TestbedSpec + GateFeedback)
- Gate 1 — Spec Parsing & Linting
- Gate 2 — Code / Artifact Validator
- Structured feedback loops
- CLI + thin pi skill

## Quick Start

```bash
# Check the environment
./testbed.sh check

# Create a new testbed spec from template
./testbed.sh init my-testbed

# Validate a JSON spec
./testbed.sh validate /workspace/quic-edge-spec.json

# Parse a markdown spec through Gate 1
./testbed.sh parse examples/success_spec.md

# Pretty-print a feedback JSON
./testbed.sh feedback /tmp/feedback.json

# Show examples
./testbed.sh example success
./testbed.sh example failure
```

Or via Make:

```bash
make check    # Check environment
make test     # Run all tests
make demo     # Run the demo script
make validate # Validate the QUIC edge spec
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `check` | Check the testbed environment (Python, deps, Ollama, KB) |
| `init <name>` | Create a new testbed spec from a template |
| `parse <file>` | Parse a markdown spec through Gate 1 |
| `validate <file>` | Validate a JSON spec directly |
| `feedback <file>` | Pretty-print a GateFeedback JSON |
| `example success|failure` | Show example spec files |
| `gate2 --spec <file>` | Run Gate 2 — Code / Artifact Validator |
| `gate3 --spec <file>` | Run Gate 3 — Security & Policy Guardrails |
| `gate4 --workspace <dir>` | Run Gate 4 — Runtime & Integration Verification |

## Package Structure

```
testbed/
├── __init__.py              # Package root (auto-sets PYTHONPATH)
├── cli.py                   # CLI entry point
├── testbed.sh               # Wrapper script (auto-sets PYTHONPATH)
├── Makefile                 # Common commands
├── pyproject.toml           # Package metadata
├── README.md                # This file
├── contracts/
│   ├── __init__.py
│   ├── spec.py              # TestbedSpec (universal contract)
│   └── feedback.py          # GateFeedback + supporting types
├── gates/
│   ├── __init__.py
│   ├── gate1_spec_parser.py # Gate 1: Spec Parser & Linter
│   ├── gate2_code_validator.py # Gate 2: Code / Artifact Validator
│   └── kb_search.py         # KB cross-reference engine
├── examples/
│   ├── success_spec.md       # Realistic success example
│   ├── failure_spec.md       # Deliberate failure example
│   └── demo.py               # Full demo script
└── tests/
    └── test_contracts.py     # 28 pytest tests
```

## Contracts

### TestbedSpec

The universal contract that every gate produces and consumes:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | str | ✅ | Human-readable testbed name |
| `version` | str | ❌ | Semantic version (default: 0.1.0) |
| `description` | str | ❌ | Purpose and scope |
| `tags` | list[str] | ❌ | Categorization tags |
| `services` | list[ServiceSpec] | ✅ | Docker services (min 1) |
| `test_suites` | list[TestSuite] | ❌ | Test suites |
| `infrastructure` | InfrastructureSpec | ❌ | Networks, volumes |
| `constraints` | ConstraintSpec | ❌ | Resource constraints |
| `guardrails` | GuardrailSpec | ❌ | Security guardrails |
| `metadata` | dict | ❌ | Extensibility |

### GateFeedback

Structured feedback from any gate:

| Field | Type | Description |
|-------|------|-------------|
| `gate_id` | str | Which gate produced this |
| `status` | enum | pass / fail / error / skip |
| `diagnostics` | list[Diagnostic] | Issues found, ordered by severity |
| `actions` | list[Action] | Suggested fixes, ordered by priority |
| `spec_snapshot` | dict | The spec at time of evaluation |
| `raw_input` | str | Original input text |
| `attempt_number` | int | Which attempt (for iteration tracking) |

## Gate 1: Spec Parser

Two-phase approach:

1. **LLM Extraction**: Sends raw text to Ollama with a structured prompt,
   asking it to produce a TestbedSpec JSON.
2. **Pydantic Validation**: Validates the extracted JSON against TestbedSpec.
   Returns either a validated spec or rich GateFeedback with diagnostics.

**Fallback**: If Ollama is unavailable, uses a keyword-based extractor that
produces a minimal spec. For reliable results, use `validate` with a JSON spec
instead of `parse` with markdown.

## Gate 2: Code / Artifact Validator

Validates that implementation artifacts under a workspace root are consistent
with an approved `TestbedSpec` and are statically coherent.

**Checks performed:**

| Check | Code | Severity | Description |
|-------|------|----------|-------------|
| Spec ↔ Artifact consistency | `G2_MISSING_SERVICE` | error | Service in spec not found in compose |
| | `G2_UNDECLARED_SERVICE` | warning | Service in compose not in spec |
| | `G2_IMAGE_MISMATCH` | error | Image doesn't match spec |
| | `G2_BUILD_MISMATCH` | warning | Build context doesn't match spec |
| | `G2_PORT_MISMATCH` | warning | Port mapping doesn't match spec |
| | `G2_MEMLIMIT_MISMATCH` | error | Memory limit missing or wrong |
| | `G2_HEALTHCHECK_MISMATCH` | error/warning | Healthcheck missing or wrong |
| | `G2_NETWORK_MISMATCH` | error | Network attachment mismatch |
| | `G2_DEPENDS_MISMATCH` | warning | depends_on mismatch |
| Required files | `G2_MISSING_FILE` | critical | Required file not found |
| | `G2_MISSING_DOCKERFILE` | error | Dockerfile not found for build service |
| Compose syntax | `G2_COMPOSE_SYNTAX` | critical | YAML parse error |
| | `G2_COMPOSE_STRUCTURE` | critical | Missing required section |
| Network consistency | `G2_NETWORK_MISSING` | error | Network in spec not in compose |
| | `G2_NETWORK_UNDECLARED` | warning | Network in compose not in spec |
| Test suite presence | `G2_MISSING_TEST_SUITE` | warning | Test suite path not found |
| Static hygiene | `G2_CONFIG_SYNTAX` | warning | Config file parse error |
| | `G2_ENVOY_CONFIG_SYNTAX` | error | Envoy config YAML error |

**Usage:**

```bash
# Run Gate 2 against the real workspace
./testbed.sh gate2 --spec /workspace/quic-edge-v2-spec.json --workspace /workspace

# With explicit compose path
./testbed.sh gate2 --spec /workspace/quic-edge-v2-spec.json \
    --workspace /workspace \
    --compose /workspace/deploy/compose/root.yml

# Write feedback to file
./testbed.sh gate2 --spec /workspace/quic-edge-v2-spec.json \
    --workspace /workspace -o /tmp/gate2-feedback.json

# Via Make
make gate2
```

**Python API:**

```python
from pathlib import Path
from testbed.contracts.spec import TestbedSpec
from testbed.gates.gate2_code_validator import validate_code

spec = TestbedSpec(**json.loads(Path("spec.json").read_text()))
feedback = validate_code(spec, workspace_root=Path("/workspace"))
```

## Feedback Loop

When Gate 1 or Gate 2 fails, the agent receives:
- **Diagnostics**: What's wrong, where, and how severe
- **Actions**: What to do next, with suggested values
- **Spec snapshot**: What was evaluated

The agent can then:
1. Read the diagnostics and actions
2. Fix the spec
3. Re-run Gate 1
4. Repeat until pass

## Gate 3: Security & Policy Guardrails

Validates that the implementation is safe to run under security and policy constraints.

**Checks performed:**

| Check | Code | Severity | Description |
|-------|------|----------|-------------|
| Privilege & capabilities | `G3_PRIVILEGED_CONTAINER` | error | Service uses `privileged: true` |
| | `G3_RISKY_CAPABILITY` | error | Service has risky `cap_add` (SYS_ADMIN, SYS_PTRACE, etc.) |
| Dangerous mounts | `G3_DOCKER_SOCKET_MOUNT` | critical | Docker socket mounted into container |
| | `G3_HOST_PATH_MOUNT` | error | Sensitive host path mounted (/, /etc, /proc, etc.) |
| Secrets hygiene | `G3_SECRET_IN_ENV` | error | Hardcoded secret in environment variable |
| Network / exposure | `G3_HOST_NETWORK_MODE` | error | Host network mode when spec disallows it |
| | `G3_EXCESSIVE_PORTS` | warning | More published ports than spec allows |
| Guardrail fidelity | `G3_GUARDRAIL_VIOLATION` | error | Spec guardrail violated by compose config |
| Informational | `G3_HEALTHCHECK_DISABLED` | info | Healthcheck disabled (distroless awareness) |

**Allowlist mechanism:** Known exceptions (e.g. netem-router `NET_ADMIN`, otel-collector distroless healthcheck) are declared in `gates/policy_allowlist.py` — visible and intentional, not hidden in code branches.

**Usage:**

```bash
# Run Gate 3 against the real workspace
./testbed.sh gate3 --spec /workspace/quic-edge-v2-spec.json --workspace /workspace

# With explicit compose path
./testbed.sh gate3 --spec /workspace/quic-edge-v2-spec.json \
    --workspace /workspace \
    --compose /workspace/deploy/compose/root.yml

# Write feedback to file
./testbed.sh gate3 --spec /workspace/quic-edge-v2-spec.json \
    --workspace /workspace -o /tmp/gate3-feedback.json

# Via Make
make gate3
```

**Python API:**

```python
from pathlib import Path
from testbed.contracts.spec import TestbedSpec
from testbed.gates.gate3_guardrails import validate_guardrails

spec = TestbedSpec(**json.loads(Path("spec.json").read_text()))
feedback = validate_guardrails(spec, workspace_root=Path("/workspace"))
```

## Gate 4: Runtime & Integration Verification

Validates that the stack actually boots, stays healthy, and passes automated
runtime checks. This is the final gate before claiming HARDEN / runtime-ready.

**Checks performed:**

| Check | Code | Severity | Description |
|-------|------|----------|-------------|
| Lifecycle / readiness | `G4_STACK_NOT_RUNNING` | critical | Stack not running and `--skip-up` set |
| | `G4_BOOTSTRAP_FAILED` | critical | `bootstrap.sh up` failed |
| Verify gate | `G4_VERIFY_FAILED` | error | `bootstrap.sh verify` reported failures |
| Unhealthy services | `G4_SERVICE_UNHEALTHY` | error | Per-service health failure |
| E2E happy flow | `G4_E2E_TEST_FAILED` | error | E2E happy-flow integration test failed |
| Tooling errors | `G4_COMMAND_ERROR` | error | Subprocess invocation problem |

**Usage:**

```bash
# Run Gate 4 against the real workspace (auto-starts stack if needed)
./testbed.sh gate4 --workspace /workspace

# Skip automatic bring-up (fail if stack not running)
./testbed.sh gate4 --workspace /workspace --skip-up

# With explicit compose path and custom E2E timeout
./testbed.sh gate4 --workspace /workspace \
    --compose /workspace/deploy/compose/root.yml \
    --e2e-timeout 600

# Write feedback to file
./testbed.sh gate4 --workspace /workspace -o /tmp/gate4-feedback.json

# Via Make
make gate4
make gate4-skip-up
```

**Python API:**

```python
from pathlib import Path
from testbed.gates.gate4_runtime import validate_runtime

feedback = validate_runtime(
    workspace_root=Path("/workspace"),
    skip_up=False,
    e2e_timeout=300,
)
```

**Failure scenarios:**

| Scenario | Expected feedback |
|----------|------------------|
| Stack not running, `--skip-up` set | `G4_STACK_NOT_RUNNING` (critical) |
| `bootstrap.sh up` fails | `G4_BOOTSTRAP_FAILED` (critical) + truncated output |
| Service unhealthy | `G4_VERIFY_FAILED` + `G4_SERVICE_UNHEALTHY` per service |
| E2E test fails | `G4_E2E_TEST_FAILED` (error) + pytest failure summary |
| Compose file missing | `G4_COMMAND_ERROR` (critical) |

## Future Gates

| Gate | Purpose | Status |
|------|---------|--------|
| **Gate 1** | Spec Parser & Linter | ✅ Implemented |
| **Gate 2** | Code Validator | ✅ Implemented |
| **Gate 3** | Guardrail Vetter | ✅ Implemented |
| **Gate 4** | Runtime Test | ✅ Implemented |

Each gate produces a `GateFeedback` with the same structure, enabling
a unified iteration loop.

## Development

```bash
# Check environment
./testbed.sh check

# Run tests
make test

# Run demo
make demo
```
