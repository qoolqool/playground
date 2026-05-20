---
name: add-audit-driven-delivery
description: "End-to-end delivery pipeline for DinD + Docker Compose microservices: AUDIT → DESIGN → PLAN → EXECUTE → HARDEN. Consolidates brainstorming, DDD, SPARC, TDD, and engineering methodology with mandatory phase gates and DinD-aware decision trees."
version: 2
created: 2026-05-20
updated: 2026-05-20
---
# ADD — Audit-Driven Delivery Pipeline

The end-to-end delivery workflow that produced the x402 PoC: 9 microservices, 3 network segments, 17 Docker containers, distributed tracing, fault injection, live pcap capture, and multiple guided scenarios — built incrementally with human review at every phase gate.

## When to Use

- Adding any feature, service, or infrastructure to a **Docker-in-Docker (DinD) + Docker Compose microservices project**
- Starting a new DinD microservices project from scratch (greenfield)
- Before writing any code — this workflow produces design docs and plans first
- When you need an audit trail from "what exists" through "shipped and verified"

**Do NOT use** when: fixing a trivial bug (one-line change), performing routine maintenance (version bumps), or doing exploratory prototyping (though prototyping may feed into Phase 0 audit).

## DinD Context

This methodology assumes a **Docker-in-Docker** development environment where:

- A DinD container runs on a host (often Podman-managed) with `docker:dind` image
- Docker Compose orchestrates services **inside** the DinD container
- Services are distributed across multi-network segments for isolation
- A **test-runner container** spans all networks and runs integration tests
- A **bootstrap.sh CLI** manages the lifecycle (`up`, `down`, `rebuild`, `verify`, etc.)
- Source code is copied into DinD via `docker cp` (not volume mounts)
- Port forwarding requires 3 layers: host → tooling → DinD → compose service

**Podman-specific:** The host may use Podman instead of Docker. This affects port forwarding (`-p` flags don't propagate through Podman — use a port-forwarding script), socket paths, and storage drivers. The sub-skills handle the details; ADD just flags the decision points.

**Key sub-skills that handle the technical details (ADD routes to them):**

| Concern | Skill |
|---------|-------|
| DinD + Compose setup on Podman | `dind-compose-setup` |
| Bootstrap CLI + tiered rebuilds | `compose-bootstrap-cli` |
| Multi-network isolation | `compose-multi-network-isolation` |
| Test-runner container | `compose-test-runner-container` |
| 3-layer port forwarding | `dind-port-forwarding` |
| Container discovery (varying names) | `dind-discover-containers-by-pattern` |
| TDD Red-Green-Refactor for infra | `tdd-dind-compose-infra` |
| 3-document workflow | `design-impl-result-docs` |
| Observability dashboard | `compose-observe-dashboard` |
| Prometheus metrics pipeline | `compose-prometheus-metrics-pipeline` |

## Core Principle: Audit Before You Build

**Never start implementing until you can answer three questions:**
1. **What exists?** — Read the running code, not the documentation.
2. **What's tested?** — Trace each test to what it actually verifies, not what it claims to test.
3. **What's the gap?** — Classify every flow as WIRED, STUB, MISSING, or BLOCKED.

## The 5 Phases

Every phase has a **mandatory ⏸️ gate** at the end. The agent NEVER auto-advances past a gate — it presents the artifact and waits for human review. This is non-negotiable.

```
AUDIT ─[⏸️ show matrix]→ DESIGN ─[⏸️ show design doc]→ PLAN ─[⏸️ show plan]→ EXECUTE ─[⏸️ per batch]→ HARDEN ─[⏸️ done?]→
```

---

### Phase 0: AUDIT — "What exists?"

**Goal:** Understand the current system before proposing any change.

This phase has **two tracks** depending on whether a DinD project already exists.

---

#### Track A: Greenfield — No existing DinD project

**How to detect:** No `docker-compose.yml`, no `bootstrap.sh`, no service directories, no `Dockerfile` files.

**If greenfield, the first design task MUST be the DinD infrastructure itself.** Do not skip to designing application services.

**What to check:**

| Check | How | Action if missing |
|-------|-----|-------------------|
| DinD container setup | Look for a `docker-compose.yml` or bootstrap script | Design DinD environment first (see `dind-compose-setup`) |
| Network topology | Any existing network segments defined | Design multi-network isolation (see `compose-multi-network-isolation`) |
| Bootstrap CLI | `bootstrap.sh` or equivalent | Design bootstrap CLI (see `compose-bootstrap-cli`) |
| Test-runner | Container that spans all networks | Design test-runner (see `compose-test-runner-container`) |
| Shared library | Common Python package for all services | Design shared library (see `python-shared-library-compose-monorepo`) |
| Observability | Jaeger, Prometheus, Grafana | Optional — design after core infrastructure |

**Artifact:** Audit report stating "This is a greenfield project. Infrastructure design needed first."

**⏸️ GATE:** Present the audit. Say: *"No existing DinD infrastructure found. The first task is designing the Docker-in-Docker environment. Ready to proceed?"*

---

#### Track B: Brownfield — DinD project exists

**How to detect:** `docker-compose.yml` exists, `bootstrap.sh` exists, services are running or defined.

**What to check in order:**

**Check 1: Does the feature need a new container/service?**
- Is it a new standalone service? → needs `docker-compose.yml` entry, Dockerfile, service directory, network assignment
- Is it an infrastructure addition (Jaeger, Prometheus, database)? → needs compose entry + network placement + port forwarding
- Is it a modification to existing service(s)? → identify which specific service to modify

**Check 2: Network placement (if new container)**
- Which existing network segment does it belong to?
- Does it need to cross segments? → needs to be an ACL/bridge service (multi-homed)
- Does it need host port forwarding? → 3-layer pattern required if on Podman
- See `compose-multi-network-isolation` for network topology patterns

**Check 3: Existing infrastructure audit**
- What bootstrap.sh subcommands exist? (up/down/status/verify/observe/profile/review/scenario/loadgen)
- Does the test-runner exist? Is it on all required networks already?
- What verification gates exist? (bootstrap.sh verify passes?)
- What observability stack exists? (Jaeger? Prometheus? Grafana?)

**Check 4: Produce the Audit Matrix** — for each integration point or flow, classify:

| Status | Meaning | Action |
|--------|---------|--------|
| WIRED | Code exists, tests pass end-to-end | Verify, move on |
| STUB | Code skeleton with hardcoded values | Replace with real call |
| MISSING | No code exists at all | Implement from scratch |
| BLOCKED | External dep not available | Document, add workaround, track as risk |

**Check 5: Check what's tested** — trace each test to the actual HTTP calls it makes. If more than 50% of tests bypass the orchestration layer and call downstream mocks directly, the integration is not validated regardless of the pass rate.

**Check 6: Define the scope boundary** — explicitly list what's OUT of scope and why:

| Item | Why Out of Scope |
|------|-----------------|
| ... | ... |

**Check 7: Search existing docs** — look in `docs/plans/`, `knowledgebase/` (if available), `docs/gaps/` for prior work on this topic.

**Artifact:** Audit matrix + gap report with greenfield/brownfield classification, new-container decision, and network placement recommendation.

**⏸️ GATE:** Present the audit matrix and decision summary. Say: *"Here's the audit. Ready to proceed to design?"* Do NOT continue to Phase 1 without explicit approval.

---

### Phase 1: DESIGN — "What + Why"

**Goal:** Produce a validated design document covering architecture, decisions, and verification criteria.

**Step 1: Explore approaches**
Propose 2-3 different approaches with trade-offs. Present options conversationally with your recommendation and reasoning. Lead with your recommended option and explain why.

**Step 2: DDD analysis**
- Identify which bounded context(s) the work touches
- Map communication patterns between contexts:
  - Same context → conformist (internal RPC)
  - Different contexts → anti-corruption layer (translation service)
- Network segments are physical bounded context boundaries: a service on `settlement-net` cannot call `internet` directly — the boundary enforces the context.
- Document context mapping: Open Host Service, Published Language, Anti-Corruption Layer, Conformist.
- Reference `compose-multi-network-isolation` for network topology decisions.

**DinD-specific design decisions to document:**
- For new services: network segment, compose entry point, port mappings, environment variables
- For infrastructure: compose config, port forwarding layers (see `dind-port-forwarding`)
- For cross-segment traffic: which multi-homed service acts as the bridge (ACL)

**Step 3: Write the design document**
Write to `docs/plans/YYYY-MM-DD-<topic>-design.md` covering:

```markdown
## Overview
One-paragraph description.

## Design Decisions
| Decision | Choice | Rationale | Alternatives Considered |
|----------|--------|-----------|------------------------|

## Architecture / DDD Analysis
Bounded contexts, network placement, anti-corruption layers.

## Verification Criteria
Numbered list of testable outcomes.

| # | Criterion | How to Verify |
|---|-----------|---------------|

## Out of Scope
```

**Artifact:** Design document at `docs/plans/YYYY-MM-DD-<topic>-design.md`

**⏸️ GATE:** Present the design document in sections (200-300 words each, asking "does this look right?" after each). After approval, say: *"Design approved. Ready for me to create the implementation plan?"* Do NOT proceed to Phase 2 without explicit approval.

---

### Phase 2: PLAN — "How"

**Goal:** Produce a step-by-step implementation plan with exact file paths, code, commands, and expected outputs. Assume the implementer knows nothing about the project.

**Break the design into bite-sized TDD tasks** (each task is 2-5 minutes of work):

```markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**
```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**
```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**
Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**
```

**Rules for tasks:**
- Each task is independently verifiable (run a command, see pass/fail)
- Include EXACT code in the plan, not vague descriptions
- Map the dependency chain (which tasks can run in parallel, which are sequential)
- If the plan exceeds ~8 tasks, split into phases with checkpoint tags
- Include the final checklist of all files changed

**DinD-specific planning patterns:**
- **Infrastructure TDD** (new compose service, observability): Use `tdd-dind-compose-infra` pattern — write failing integration tests from test-runner first
- **Container discovery**: Do not hardcode container names — use `docker ps --format` filters (see `dind-discover-containers-by-pattern`)
- **Rebuild order**: `docker compose down`, rebuild images, `docker compose up -d --build` (see `compose-bootstrap-cli` tiered rebuild section)
- **3-document workflow**: Use `design-impl-result-docs` pattern for the full traceability chain

**Artifact:** Implementation plan at `docs/plans/YYYY-MM-DD-<topic>-impl.md`

**⏸️ GATE:** Present the task overview and dependency chain. Say: *"Plan saved. Ready to start executing? I'll process tasks in batches and report after each batch."* Do NOT proceed to Phase 3 without explicit approval.

---

### Phase 3: EXECUTE — "Build it"

**Goal:** Implement the plan incrementally with TDD, batching for human review checkpoints.

**Process:**

1. **Execute in batches** — default 3 tasks per batch, then pause for feedback.
2. **For each task:** Follow the plan steps exactly (write failing test → verify fail → implement → verify pass → commit).
3. **Root-cause fix on failures** — do NOT fix symptoms. When a test fails: read the error carefully, trace the actual call chain, do not ignore errors.
4. **Incremental-build:** Wire one integration, test it, fix what breaks, THEN wire the next. Do not wire all clients then test.
5. **Document as you go:** Every discovered gotcha, every non-obvious behavior, every workaround — record it.

**DinD execution context — ALL commands run inside the Docker-in-Docker environment:**

```
┌──────────────────────────────────────────────────┐
│  HOST (Podman/Docker)                             │
│  ┌────────────────────────────────────────────┐   │
│  │  DinD Container (docker:dind)              │   │
│  │  ┌──────────────────────────────────────┐  │   │
│  │  │  Docker Compose Network              │  │   │
│  │  │  ┌──────────┐  ┌──────────┐         │  │   │
│  │  │  │ service-1│  │ service-2│         │  │   │
│  │  │  └──────────┘  └──────────┘         │  │   │
│  │  │  ┌────────────────────────────┐     │  │   │
│  │  │  │ test-runner (multi-homed)  │     │  │   │
│  │  │  │ ← ALL tests run from here  │     │  │   │
│  │  │  └────────────────────────────┘     │  │   │
│  │  └──────────────────────────────────────┘  │   │
│  └────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

**Command patterns used in this phase:**

| Action | Pattern |
|--------|---------|
| Run tests | `docker exec DIND docker exec TEST_RUNNER python3 -m pytest tests/ -v` |
| Discover test-runner | `docker exec DIND docker ps --format '{{.Names}}' \| grep test-runner \| head -1` |
| Rebuild compose | `docker exec DIND docker compose -f /workspace/docker-compose.yml up -d --build` |
| Copy scripts to test-runner | `docker exec DIND docker cp /workspace/script.py TEST_RUNNER:/tmp/script.py` |
| Run inline Python | Single-quote the Python block to avoid host shell expansion |
| Service health check | `docker exec DIND docker exec SERVICE python3 -c "import urllib.request; ..."` |
| Check compose status | `docker exec DIND docker compose -f /workspace/docker-compose.yml ps` |

**Key gotchas in this environment:**
- `docker cp src/. dest/` flattens directory contents — source goes into dest/ not dest/src/
- Container names vary by compose project prefix — use `--format` filters, not hardcoded names
- Single-quote Python blocks in `docker exec` — double quotes cause shell expansion of `$` and `.get()`
- Environment variables do NOT propagate through nested `docker exec` — pass them explicitly with `-e`
- Host shell expands variables in `sh -c` strings — use single quotes for DinD-internal paths
- Settlement-net services are UNREACHABLE from test-runner by design (network isolation, not a bug)
- Port forwarding through Podman requires a separate port-forwarding script — direct `-p` doesn't propagate

**⏸️ GATE after each batch:** Show what was implemented, show verification output, show test results. Say: *"Batch complete. Ready for feedback, or proceed to next batch?"*

**⏸️ GATE on blockers:** If a task is blocked (missing dependency, test fails inexplicably, plan instruction unclear), STOP. Do not guess or skip. Report the blocker and ask for guidance.

**⏸️ GATE when the plan is wrong:** If you've learned something that makes the remaining plan unworkable, STOP. Report what changed and why the plan needs revision.

---

### Phase 4: HARDEN — "Ship it"

**Goal:** Verify everything works, fix any issues, and present for completion.

1. **Run the full test suite** — from test-runner inside DinD
2. **Run verification gates** — via `bootstrap.sh verify` (or equivalent health + e2e gate)
3. **Run performance profile** — via `bootstrap.sh profile` or latency checks from test-runner
4. **Run static analysis** — pre-commit checks (imports, lint, network isolation via `bootstrap.sh review`)
5. **Run operational readiness checklist:**
   - [ ] Health endpoints on all services (check via `bootstrap.sh observe`)
   - [ ] Observability producing data (Jaeger traces, Prometheus metrics)
   - [ ] Verification gates pass (`bootstrap.sh verify` scores ≥ threshold)
   - [ ] Gotchas documented somewhere findable
   - [ ] All commits pushed
6. **Write the implementation result** — `docs/implementation/YYYY-MM-DD-<topic>.md` covering what actually shipped, actual commit hashes, test counts, deviations from plan (with reasons). See `design-impl-result-docs` skill.

**DinD-specific verification:**
- `bootstrap.sh verify` runs health checks on all services from inside the compose network
- `bootstrap.sh observe` shows reachability matrix and trace data
- Both commands use the test-runner container — they verify cross-service reachability, not just individual health
- Expected: settlement-net services show as UNREACHABLE from internet-net services (correct isolation)
- Verify that new services appear in `bootstrap.sh status` output

**Artifact:** Implementation result doc + clean commit history + all gates passing.

**⏸️ GATE:** Show verification summary. Say: *"All gates passing. Ready to finish this branch?"* Reference the `finishing-a-development-branch` skill for merge/PR/cleanup options.

---

## Phase Gate Protocol (Critical)

**These rules apply in EVERY phase:**

1. **Never auto-proceed past a ⏸️ GATE** — always present the artifact and wait for human response.
2. **Artifacts before gates** — the audit matrix, design doc, plan doc, batch results, and verification summary must be PRESENTED to the human. Not just "I wrote it" but showing the content.
3. **If the human gives feedback at a gate, apply it and re-present the artifact** — do not skip to the next phase.
4. **STOP and ask on:** any failure you can't explain, any instruction you don't understand, any discovery that invalidates the current phase.

**Never implement on main/master without explicit consent. Prefer feature branches.**

## Pitfalls

- **Skipping Phase 0 (Audit) is the most common failure mode** — you will design something that already exists, or miss a critical constraint. Always audit first.
- **Greenfield vs brownfield confusion** — Phase 0 explicitly branches on this. If you don't check, you'll design services for infrastructure that doesn't exist yet.
- **Hardcoding container names** — Docker Compose auto-prefixes names with the project directory. Always discover containers by pattern, not hardcoded names. See `dind-discover-containers-by-pattern`.
- **Writing the plan before the design is approved** wastes effort on a plan for an approach that gets changed in review.
- **Not updating the design/plan after discovery** — if Phase 3 reveals something that invalidates the design, go BACK to Phase 1, don't forge ahead with a bad design.
- **Skipping verification criteria in the design doc** — without testable criteria, there's nothing to verify against.
- **Testing all integrations at once instead of incrementally** — wire one, test it, fix, then wire the next.
- **Batch too large** — if a batch exceeds 5 tasks or takes more than 15 minutes, it's too large for meaningful feedback. Default is 3 tasks.
- **Shell quoting in nested docker exec** — single-quote the Python block, pass env vars with `-e`, avoid double quotes that trigger host shell expansion.
- **Podman port forwarding** — `docker run -p` flags in a Podman-hosted DinD don't propagate ports to the host. Use a dedicated port-forwarding script. See `dind-port-forwarding`.

## Verification (of the workflow itself)

After applying ADD, confirm:
1. Audit matrix exists with WIRED/STUB/MISSING/BLOCKED classifications
2. Greenfield vs brownfield decision was made explicitly in Phase 0
3. Design doc exists at `docs/plans/YYYY-MM-DD-<topic>-design.md` with verification criteria and out-of-scope
4. Implementation plan exists at `docs/plans/YYYY-MM-DD-<topic>-impl.md` with exact code and commands
5. Each implementation commit corresponds to a plan task (traceable)
6. Human was asked for review at every phase gate — no auto-advance
7. All verification criteria from the design doc are addressed
8. Gotchas discovered during execution are documented somewhere findable
9. For new services: network placement was documented and compose entry was created
10. `bootstrap.sh verify` passes after completion