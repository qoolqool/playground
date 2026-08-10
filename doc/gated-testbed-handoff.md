# Gated AI Testbed — Handoff Guide

> **Status:** MVP complete (Gate 1 only)
> **Location:** `/project/tooling/testbed/`
> **Skill:** `gated-testbed` (auto-discovered by pi)
> **Date:** 2026-08-05

## What This Is

A gated architecture for creating, validating, and iterating on AI-generated
testbed specifications. The system turns the agent from a one-shot generator
into an iterative system that learns from accumulated knowledge.

### Architecture (long-term)

```
[ USER SPEC ] ──→ Gate 1: Spec Parser ──→ Gate 2: Code Validator
                                              ↓
                    [ REPO BASE ] ←── Gate 4: Runtime Test ←── Gate 3: Guardrail Vetting
```

**Current MVP:** Gate 1 + shared contracts + KB cross-reference.

---

## Quick Start: Create a New Testbed

### Step 1: Write a spec

Create a markdown file describing your testbed. Include:

- **What** the testbed does (purpose, scope)
- **Services** (name, image, ports, memory, healthchecks, networks, dependencies)
- **Test suites** (what tests validate it)
- **Infrastructure** (networks, volumes)
- **Constraints** (memory limits, resource caps)
- **Guardrails** (security policies)

Example — save as `my-testbed-spec.md`:

```markdown
# My Testbed: Payment Processing Pipeline

A testbed for a payment processing pipeline with transaction validation,
ledger storage, and monitoring.

## Services

### Core
- **validator** (validator:latest): Transaction validation service
  - Port: 8080
  - Memory: 512M
  - Healthcheck: GET /health
  - Networks: app-net

- **ledger-db** (postgres:16-alpine): Transaction ledger
  - Port: 5432
  - Memory: 1G
  - Healthcheck: pg_isready
  - Networks: app-net
  - Depends on: validator

### Observability
- **prometheus** (prom/prometheus:latest): Metrics
  - Port: 9090
  - Memory: 256M
  - Networks: app-net, monitoring-net

- **grafana** (grafana/grafana:latest): Dashboards
  - Port: 3000
  - Memory: 256M
  - Networks: monitoring-net
  - Depends on: prometheus

## Test Suites

- **smoke**: tests/smoke/ — pytest, requires validator + ledger-db
- **integration**: tests/integration/ — pytest, requires all services

## Infrastructure

Networks:
- app-net: bridge (internal services)
- monitoring-net: bridge (observability)

## Constraints

- Memory limits on all services (see above)
- Max containers: 10

## Guardrails

- require_mem_limit: true
- require_healthcheck: true
- no_host_network: true
```

### Step 2: Run Gate 1

```bash
# Parse and validate, cross-referencing the knowledgebase
python3 -m testbed.cli parse my-testbed-spec.md \
  --kb-dir /workspace/scdlt/knowledgebase \
  -o /tmp/feedback.json
```

### Step 3: Read the feedback

```bash
python3 -m testbed.cli feedback /tmp/feedback.json
```

The output tells you:

| Section | What it means |
|---------|---------------|
| **Status** | `pass` = spec is structurally valid. `fail` = fix issues first. |
| **Diagnostics** | What's wrong, where, and how severe. Includes KB refs. |
| **Actions** | What to do next, in priority order. |
| **KB refs** | Links to relevant gotchas/patterns/decisions from the KB. |

### Step 4: Iterate

If the spec fails:
1. Read each diagnostic and its KB references
2. Read the referenced KB entries (they explain what went wrong before)
3. Fix the spec
4. Re-run Gate 1
5. Repeat until pass

If the spec passes but has warnings:
- Warnings are non-blocking but informative
- Consider fixing them before proceeding to implementation

---

## KB-Aware Feedback Loop

The key innovation: Gate 1 doesn't just validate structure — it cross-references
your spec against the accumulated knowledgebase.

### How it works

```
Your spec (services, images, tags, networks)
        │
        ▼
Keyword extraction ──→ KB search ──→ Scored matches
        │                              │
        ▼                              ▼
  Structural errors              Relevant gotchas,
  (Pydantic)                     patterns, decisions
        │                              │
        └──────────┬───────────────────┘
                   ▼
          Unified GateFeedback
          (diagnostics + KB refs)
```

### What the agent does with it

When a diagnostic has `kb_refs`, the agent should:

1. **Read the referenced KB entry** — it explains what went wrong before
2. **Apply the fix** — the gotcha/pattern/decision tells you what to do
3. **Re-run Gate 1** — verify the fix works
4. **The KB refs update** — as the spec changes, different KB entries become relevant

### Example

If your spec has a service using `network_mode: "service:peer"`, the KB
search will find the gotcha about `network_mode: service` requiring the
peer in the same compose invocation, and suggest using
`network_mode: "container:peer"` instead.

---

## CLI Reference

### `parse` — Parse and validate a spec

```bash
python3 -m testbed.cli parse <spec-file> [options]

Options:
  --stdin              Read spec from stdin (pipe mode)
  --no-llm             Skip LLM extraction (use keyword fallback)
  --kb-dir <path>      KB directory to cross-reference (repeatable)
  -o, --output <file>  Write feedback JSON to file
```

### `validate` — Validate a JSON spec directly

```bash
python3 -m testbed.cli validate <spec-file.json>
```

### `feedback` — Pretty-print a feedback JSON

```bash
python3 -m testbed.cli feedback <feedback.json>
```

### `example` — Show example specs

```bash
python3 -m testbed.cli example success
python3 -m testbed.cli example failure
```

---

## Python API

For programmatic use (e.g., from a pi skill or extension):

```python
from pathlib import Path
from testbed.gates.gate1_spec_parser import parse_spec

spec, feedback = parse_spec(
    raw_text="# My Testbed\n\n...",
    use_llm=True,
    kb_dirs=[Path("/workspace/scdlt/knowledgebase")],
)

if feedback.is_pass():
    # Spec is valid — proceed to implementation
    print(f"✅ {spec.name} v{spec.version}")
    print(f"   Services: {len(spec.services)}")
else:
    # Spec has issues — iterate
    for d in feedback.diagnostics:
        print(f"❌ [{d.code}] {d.message}")
        for ref in d.kb_refs:
            print(f"   📚 See: {ref.path}")
    for a in feedback.actions:
        print(f"🔧 {a.description}")
```

---

## Targeting the Existing Testbed (/workspace)

The system is designed to operate on any project mount. To use it with
the existing testbed in `/workspace`:

### Option A: Parse the existing compose files into a spec

The existing testbed at `/workspace/scdlt/` has 15+ compose files under
`deploy/compose/`. A future Gate 2 enhancement could parse these into a
`TestbedSpec` automatically. For now, write a spec manually based on:

- `deploy/compose/platform.yml` — core services
- `deploy/compose/custody.yml` — custody infrastructure
- `deploy/compose/observability.yml` — monitoring stack
- `deploy/compose/root.yml` — test-runner and tooling

### Option B: Cross-reference against the scdlt knowledgebase

The scdlt knowledgebase at `/workspace/scdlt/knowledgebase/` has **392 entries**
covering gotchas, patterns, decisions, and facts. When creating a new testbed
spec, always include:

```bash
--kb-dir /workspace/scdlt/knowledgebase
```

This surfaces relevant accumulated wisdom automatically.

---

## What's Next (Gates 2–4)

### Gate 2 — Code Validator (not yet implemented)

Should consume the validated `TestbedSpec` and inspect the actual codebase:

- Do the Dockerfiles match the `build` paths?
- Are the compose files consistent with the service definitions?
- Do the test suites exist at the specified paths?
- Are the environment variables actually used?

**Plugs into:** Same `GateFeedback` object. Produces diagnostics with `kb_refs`.

### Gate 3 — Guardrail Vetter (not yet implemented)

Should check security and compliance policies:

- No privileged containers unless explicitly allowed
- No host network mode unless explicitly allowed
- All images come from allowed registries
- Memory limits on all services

**Plugs into:** Same `GateFeedback` object. Reuses `GuardrailSpec` from spec.

### Gate 4 — Runtime Test (not yet implemented)

Should actually run the testbed and report results:

- Start all services
- Run healthchecks
- Execute test suites
- Report pass/fail with diagnostics

**Plugs into:** Same `GateFeedback` object. Adds runtime-specific diagnostics.

---

## Files

| Path | Purpose |
|------|---------|
| `/project/tooling/testbed/` | Package root |
| `/project/tooling/testbed/contracts/spec.py` | TestbedSpec model |
| `/project/tooling/testbed/contracts/feedback.py` | GateFeedback + KBRef models |
| `/project/tooling/testbed/gates/gate1_spec_parser.py` | Gate 1 implementation |
| `/project/tooling/testbed/gates/kb_search.py` | KB cross-reference engine |
| `/project/tooling/testbed/cli.py` | CLI entry point |
| `/project/tooling/testbed/examples/success_spec.md` | Realistic success example |
| `/project/tooling/testbed/examples/failure_spec.md` | Deliberate failure example |
| `/project/tooling/testbed/examples/demo.py` | Full demo script |
| `/project/tooling/testbed/tests/test_contracts.py` | 28 pytest tests |
| `/project/tooling/testbed/SKILL.md` | pi skill (in-package) |
| `/project/tooling/skills/gated-testbed/SKILL.md` | pi skill (auto-discovered) |
| `/workspace/scdlt/knowledgebase/` | 392 KB entries for cross-reference |

## Verification

After setup, verify everything works:

```bash
# 1. Run the demo
python3 /project/tooling/testbed/examples/demo.py

# 2. Run the tests
cd /project/tooling/testbed && python3 -m pytest tests/ -v

# 3. Parse the success example with KB cross-reference
python3 -m testbed.cli parse /project/tooling/testbed/examples/success_spec.md \
  --kb-dir /workspace/scdlt/knowledgebase

# 4. Parse the failure example
python3 -m testbed.cli parse /project/tooling/testbed/examples/failure_spec.md
```
