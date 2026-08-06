---
name: gated-testbed
description: "Quality gate for testbed specs and implementation artifacts. Validates spec consistency (Gate 1), implementation-vs-spec alignment (Gate 2), security/policy guardrails (Gate 3), and runtime/integration verification (Gate 4). Use at mandatory checkpoints during ADD delivery. Not a delivery pipeline — hand off to add-audit-driven-delivery for build work."
---

# Gated AI Testbed Skill

You own both quality gates. Neither is optional — you call them yourself.

## When to Use

- Validating a testbed spec against KB and guardrails (Gate 1)
- Validating implementation artifacts against an approved spec (Gate 2)
- Validating security & policy guardrails against the spec and compose (Gate 3)
- Validating runtime stack health, bootstrap verify, and E2E integration tests (Gate 4)
- Iterating on gate failures by applying returned `actions`
- Checking readiness before handoff, review, or HARDEN

**Do NOT use** as the primary driver for implementing phases, adding services, or building the next phase. This skill is a quality gate, not a delivery pipeline.

For any non-trivial build or change work → hand off to `add-audit-driven-delivery`; only run gates at the defined checkpoints.

## Out of Scope

- Owning AUDIT / DESIGN / PLAN / EXECUTE / HARDEN
- Implementing new phases or large feature sets under `/workspace`
- Skipping ADD phase gates

When the user asks to build or evolve a phase, use `add-audit-driven-delivery` and invoke this skill only at the mandatory Gate 1 / Gate 2 / Gate 3 checkpoints.

## State Machine

The agent tracks its position in this state machine at all times. Do not advance past a red state without running the corresponding gate.

```
SPEC_DIRTY ──[run Gate 1]──→ SPEC_CLEAN ──[implement]──→ ARTIFACTS_DIRTY ──[run Gate 2]──→ ARTIFACTS_CLEAN ──[run Gate 3]──→ POLICY_CLEAN ──[run Gate 4]──→ RUNTIME_CLEAN
     ↑                            │                                                  │
     └──[fix spec, re-run]────────┘                                                  │
                                                                                     │
     ┌──[fix artifacts, re-run]─────────────────────────────────────────────────────┘
```

| State | Meaning | Allowed Actions |
|-------|---------|-----------------|
| `SPEC_DIRTY` | Spec has been changed since last Gate 1 pass | Run Gate 1. Do NOT touch `/workspace` artifacts. |
| `SPEC_CLEAN` | Spec is validated and approved | Implement under `/workspace`. Any spec change → back to `SPEC_DIRTY`. |
| `ARTIFACTS_DIRTY` | Implementation artifacts changed since last Gate 2 pass | Run Gate 2. Do NOT claim work is done. |
| `ARTIFACTS_CLEAN` | Implementation matches the approved spec | Run Gate 3. Any security-relevant change → back to `ARTIFACTS_DIRTY`. |
| `POLICY_CLEAN` | Security & policy guardrails verified | Run Gate 4. Any security-relevant change → back to `ARTIFACTS_DIRTY`. |
| `RUNTIME_CLEAN` | Stack is running, healthy, and E2E tests pass | Work is complete. Ready for HARDEN / review. Any change → back to `ARTIFACTS_DIRTY`. |

## Hard Rules

### Gate 1 — Spec Validation
After every change to a testbed specification:

1. **Write/update** the spec as JSON.
2. **Call Gate 1** via `./testbed.sh validate <spec.json>`.
3. **If `status != "pass"`**, apply the returned `actions` (or ask the user when a product decision is required), then go back to step 1.
4. **Only when `status == "pass"`** may you proceed to code changes, Docker files, or modifications under `/workspace`.

Never skip Gate 1. Never treat a failing Gate 1 as "good enough for now".

### Gate 2 — Implementation Validation

After every change to implementation artifacts under `/workspace` (compose files, Dockerfiles, configs, tests, scripts):

1. **Call Gate 2** via `./testbed.sh gate2 --spec <spec.json> --workspace /workspace`.
2. **If `status != "pass"`**, read the `diagnostics` and `actions`, apply the fixes, then re-run Gate 2.
3. **Only when `status == "pass"`** may you proceed to Gate 3 or runtime testing.

Never skip Gate 2. Never treat a failing Gate 2 as "close enough".

### Gate 3 — Security & Policy Guardrails

After Gate 2 PASS and before any "done", "ready for review", HARDEN, or runtime-ready claim:

1. **Call Gate 3** via `./testbed.sh gate3 --spec <spec.json> --workspace /workspace`.
2. **If `status != "pass"`**, read the `diagnostics` and `actions`, apply the fixes, then re-run Gate 3.
3. **Only when `status == "pass"`** may you claim the work is done or proceed to HARDEN.

**Re-run Gate 3** if implementation changes in ways that affect:
- Privilege or capabilities (`privileged`, `cap_add`, `cap_drop`)
- Volume mounts (Docker socket, sensitive host paths)
- Environment variables / secrets
- Network mode (`network_mode: host`)
- Ports (excessive exposure)
- Guardrails-related settings in the compose file
- **npm dependencies** — any `package.json` file added, removed, or modified

**npm supply chain security check:** Gate 3 now scans all `package.json` files
under the workspace (excluding `node_modules`) for known vulnerable npm packages.
This check was added in response to the Keyv/cacheable supply chain attack
(https://www.wiz.io/blog/keyv-and-cacheable-npm-supply-chain-attack) where
malicious versions of `keyv`, `cacheable-request`, and `cacheable-lookup` were
published via npm account takeover, exfiltrating environment variables and secrets.

| Vulnerable Package | Severity | Advisory |
|-------------------|----------|----------|
| `keyv` | critical | Compromised via npm account takeover (2023-11). Malicious versions exfiltrated env vars and secrets. |
| `cacheable-request` | critical | Same supply chain attack as keyv. |
| `cacheable-lookup` | critical | Same supply chain attack as keyv. |

**Policy:** Any `package.json` file containing a known vulnerable npm package
will produce a `G3_NPM_SUPPLY_CHAIN` diagnostic with severity `critical` and an
action to remove or replace the package. This is a hard block — do not proceed
past Gate 3 until resolved.

**Explicit allowlist awareness:** The default allowlist encodes known exceptions:
- `netem-router` → `NET_ADMIN` capability (required for traffic shaping, in `SAFE_CAPABILITIES`)
- `otel-collector` → healthcheck disabled (distroless image, no shell)

Do NOT "fix" these by removing required capabilities or adding healthchecks to distroless images. If a new service needs a similar exception, add it to the allowlist via `PolicyAllowlist`.

Never skip Gate 3. Never treat a failing Gate 3 as "close enough".

### Gate 4 — Runtime & Integration Verification

After Gate 3 PASS and before any "done", "ready for review", HARDEN, or runtime-ready claim:

1. **Call Gate 4** via `./testbed.sh gate4 --workspace /workspace [--skip-up] [--e2e-timeout N]`.
2. **If `status != "pass"`**, read the `diagnostics` and `actions`, apply the fixes, then re-run Gate 4.
3. **Only when `status == "pass"`** may you claim the work is done or proceed to HARDEN.

**Gate 4 performs three phases:**
- **Lifecycle check** — `docker compose ps` verifies expected containers are running. If the stack is down and `--skip-up` is not set, it runs `bootstrap.sh up` to bring it up.
- **Bootstrap verify** — `bootstrap.sh verify` runs health checks on all services from inside the compose network.
- **E2E happy-flow test** — Discovers `*happy_flow*` under `tests/e2e/` and runs it via `docker compose exec test-runner python3 -m pytest`. If no happy-flow file exists, this phase is skipped with a warning (not a hard failure).

**Re-run Gate 4** if:
- The stack was brought down and back up
- Services were added, removed, or reconfigured
- E2E tests were added or modified
- The bootstrap verify script was changed

**Diagnostic codes:**
| Code | Severity | Meaning |
|------|----------|--------|
| `G4_STACK_NOT_RUNNING` | critical | Stack is down and `--skip-up` was set |
| `G4_BOOTSTRAP_FAILED` | critical | `bootstrap.sh up` failed or partial container start |
| `G4_VERIFY_FAILED` | error | `bootstrap.sh verify` reported failures |
| `G4_SERVICE_UNHEALTHY` | error | Per-service health failure (named in detail) |
| `G4_E2E_TEST_FAILED` | error | E2E happy-flow test failed |
| `G4_COMMAND_ERROR` | error/warning | Subprocess/tooling problem (e.g., missing compose file) |

Never skip Gate 4. Never treat a failing Gate 4 as "close enough".

### Before Claiming "Done" / "Ready for Review" / HARDEN

Before any handoff, review request, or HARDEN claim:

1. **All four gates must be PASS.** If any is stale (artifacts changed since last run), re-run it.
2. **Preferred final check:** Run all four gates back-to-back. Only report success if all return `status=pass`.
3. **Revision protocol is mandatory for all gates:** read `actions` → apply fixes → re-run → repeat until `status == "pass"`.

## Minimal Invocations

### Gate 1 — Spec Validation
```bash
./testbed.sh validate /workspace/<name>-spec.json
```

Or the equivalent Python call:

```python
from testbed.gates.gate1_spec_parser import validate_spec
from pathlib import Path

validated, feedback = validate_spec(
    spec_dict,
    kb_dirs=[Path("<knowledgebase-dir>")],
    attempt_number=1,
    previous_summary=None,
)
```

Always work with a JSON file or a Python dict. Do not rely on the markdown/LLM parser.

### Gate 2 — Implementation Validation
```bash
./testbed.sh gate2 --spec /workspace/<name>-spec.json --workspace /workspace
```

Or the equivalent Python call:

```python
from testbed.gates.gate2_code_validator import validate_code

feedback = validate_code(
    spec=validated_spec,
    workspace_root=Path("/workspace"),
    attempt_number=1,
)
```

The gate auto-detects the compose file under `/workspace/deploy/compose/root.yml`.

### Gate 3 — Security & Policy Guardrails
```bash
./testbed.sh gate3 --spec /workspace/<name>-spec.json --workspace /workspace
```

Or the equivalent Python call:

```python
from testbed.gates.gate3_guardrails import validate_guardrails

feedback = validate_guardrails(
    spec=validated_spec,
    workspace_root=Path("/workspace"),
    attempt_number=1,
)
```

The gate auto-detects the compose file under `/workspace/deploy/compose/root.yml`. Optionally pass `--compose <path>` for a non-standard location.

### Gate 4 — Runtime & Integration Verification
```bash
./testbed.sh gate4 --workspace /workspace [--skip-up] [--e2e-timeout 300]
```

Or the equivalent Python call:

```python
from testbed.gates.gate4_runtime import validate_runtime
from pathlib import Path

feedback = validate_runtime(
    workspace_root=Path("/workspace"),
    compose_path=Path("/workspace/deploy/compose/root.yml"),
    skip_up=False,
    e2e_timeout=300,
    attempt_number=1,
    previous_summary=None,
)
```

The gate auto-detects the compose file under `/workspace/deploy/compose/root.yml`. Pass `--skip-up` to skip the `bootstrap.sh up` phase (useful when the stack is already running).

## How to Consume the Feedback (all gates)

- **`status == "pass"`** → you may proceed. Still read warnings and any KB diagnostics.
- **`status == "fail"`** → treat `actions` as your primary to-do list. Each action is specific (field path + suggested change). Apply them, fix the artifacts, and re-run the gate.
- Use `diagnostics` for context and accumulated wisdom, but let `actions` drive the concrete edits.
- Pass `attempt_number` and `previous_summary` on consecutive calls so the feedback feels like a conversation, not a reset.
- The revision protocol is identical for all gates: read → apply → re-run → repeat until `status == "pass"`.

## Phase 0 (still required, but now feeds the gate)

Before the first `validate` call, perform the critical service analysis and encode the results directly into the spec (`description` fields, guardrails, etc.). Gate 1 will then enforce the quality of those decisions.

## What Success Looks Like

1. **Gate 1:** You produce a JSON spec → call `validate` → receive `status=pass` (possibly after 1–3 tight revision cycles) → state transitions to `SPEC_CLEAN` → only then start implementing or modifying the testbed in `/workspace`.
2. **Gate 2:** You implement the artifacts → call `gate2` → receive `status=pass` (possibly after 1–3 fix cycles) → state transitions to `ARTIFACTS_CLEAN`.
3. **Gate 3:** You run security & policy guardrails → call `gate3` → receive `status=pass` (possibly after 1–3 fix cycles) → state transitions to `POLICY_CLEAN`.
4. **Gate 4:** You verify the runtime stack → call `gate4` → receive `status=pass` (possibly after 1–3 fix cycles) → state transitions to `RUNTIME_CLEAN`.
5. **Final handoff:** All four gates PASS. State is `SPEC_CLEAN + ARTIFACTS_CLEAN + POLICY_CLEAN + RUNTIME_CLEAN`. Work is ready for HARDEN / review.

## Post-Implementation: Sync Documentation

After **all four** gates pass and implementation is complete, you **must** update the main documentation files under `/workspace` to reflect the actual deployed state. This is a mandatory step — the docs must match reality.

### Which files to update

Scan `/workspace` for these files and update any that exist:

| File | What to sync |
|------|-------------|
| `README.md` | Project overview, service list, architecture diagram references, quick-start instructions |
| `PRD.md` | Testbed infrastructure tables (deployed services vs future-phase services), design decisions, test scenarios |
| `INFRA.md` | Service definitions (images, ports, healthchecks, networks, build contexts, env vars), test suites, constraints, guardrails, gotchas |

Also update any other `.md` files under `/workspace` that reference services, ports, healthchecks, networks, or test suites (e.g., architecture docs, design docs, implementation plans).

### What to verify in each file

For each service in the deployed spec, ensure the docs reflect:

- **Service name and image** — matches the spec exactly
- **Ports** — host:container mapping and protocol
- **Healthcheck** — actual command used (not a placeholder; account for image limitations like missing `curl`)
- **Networks** — which networks the service belongs to
- **Memory limits** — per-service constraints
- **Build contexts** — if the service is built from source, include the `./src/...` path
- **Environment variables** — if set in the compose file
- **Container names** — if explicitly set
- **Depends on** — startup dependencies

For test suites, verify:

- **Suite names and count** — match the spec exactly
- **What each validates** — accurate description
- **Required services** — listed correctly

For infrastructure, verify:

- **Networks** — names, drivers, descriptions
- **Constraints** — max containers, memory per service
- **Guardrails** — match the spec

### What to do with non-deployed services

Services that exist in the spec/design but are **not in the current deployment** should be moved to a **"Next Steps"** or **"Future Phases"** section, clearly labeled with the phase they belong to (Phase 2, Phase 3, etc.). Do not label them as "deferred Phase 1" — they belong to later phases.

### Procedure

1. Read the deployed compose file (e.g., `/workspace/deploy/compose/root.yml`) and the validated spec JSON
2. For each `.md` file under `/workspace`:
   - Compare its service tables, test suite tables, and infrastructure descriptions against the deployed compose + spec
   - Fix any discrepancies: wrong healthchecks, wrong ports, missing services, stale service lists
   - Move non-deployed services to a future-phase section
   - Add any gotchas or deployment learnings from the KB session
3. Verify consistency: all deployed services are mentioned, all healthchecks match, all ports match

## Pitfalls

- **Floating image tags** (`latest`) are acceptable for prototyping but pin versions before production.
- **Missing healthchecks** and **missing memory limits** are common blockers or strong warnings.
- **Every service needs a `description` field** — this forces you to justify why it exists.
- **Do not add services that belong to a future phase.** Each phase should be self-contained.
- **PYTHONPATH must be set.** Use `./testbed.sh` (wrapper script) or `export PYTHONPATH=/project/tooling` before running commands.
- **pip install is blocked** by PEP 668. Use `--break-system-packages` or set PYTHONPATH instead.
- **KB cross-reference quality** depends on the spec having meaningful service names and images.
- **Gate 1 validates the *spec*, not the *code*.** Gate 2 validates the *code* against the spec. Both are mandatory.
- **Docs drift is a quality failure.** If the `.md` files under `/workspace` don't match the deployed compose, the implementation is incomplete. Always sync docs after code changes.
- **Do not label non-deployed services as "deferred Phase 1".** They belong to their actual target phase (Phase 2, Phase 3, etc.). Use a "Next Steps" section.
- **Healthchecks in docs must match the actual deployed command**, not a theoretical one. Account for image limitations (e.g., Envoy image doesn't include `curl`).

## Verification

After reaching `status=pass` on **Gate 1**:
1. Review all warnings — they indicate missing optional fields
2. Review KB-sourced diagnostics — these are relevant accumulated learnings
3. Verify the extracted services match the user's intent
4. Run the test suite: `cd /project/tooling/testbed && python3 -m pytest tests/ -v`
5. Run the environment check: `./testbed.sh check`

After reaching `status=pass` on **Gate 2**:
1. Review all warnings — they indicate non-blocking issues (empty test dirs, etc.)
2. Verify the compose file matches the spec on every checked field
3. Verify all required files (Dockerfiles, test dirs, configs) exist on disk

After reaching `status=pass` on **Gate 3**:
1. Review all warnings — they indicate non-blocking issues (excessive ports, host network when allowed)
2. Verify the allowlist is correct — no unexpected exceptions, no missing required exceptions
3. Verify no secrets leaked into environment variables
4. Verify no Docker socket mounts or sensitive host paths
5. **Verify no known vulnerable npm packages** — check that no `G3_NPM_SUPPLY_CHAIN` diagnostics were raised
6. Run the test suite: `cd /project/tooling/testbed && python3 -m pytest tests/test_gate3.py -v`

After reaching `status=pass` on **Gate 4**:
1. Review all warnings — they indicate non-blocking issues (missing happy-flow file, etc.)
2. Verify the stack is running with expected container count
3. Verify `bootstrap.sh verify` passes cleanly
4. Verify E2E happy-flow test passed (if the file exists)
5. Run the test suite: `cd /project/tooling/testbed && python3 -m pytest tests/test_gate4.py -v`

After syncing documentation:
1. Verify every deployed service appears in each `.md` file
2. Verify healthcheck commands match the deployed compose (not theoretical)
3. Verify non-deployed services are in a "Next Steps" / "Future Phases" section, not mixed with deployed services
4. Verify port mappings, networks, memory limits, and build contexts match the compose file
5. Run a consistency check: `python3 -c "import json; spec=json.load(open('/workspace/<name>-spec.json')); [s['name'] for s in spec['services']]"` and cross-reference against each `.md` file
