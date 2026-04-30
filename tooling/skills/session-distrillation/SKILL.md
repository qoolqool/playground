---
name: session-distillation
description: >
  Distill long conversations into structured memory updates and knowledge base
  entries. Use when conversations are long, ending, or when important insights
  should persist. Writes files to disk — they survive context compaction.
---

# Session Distillation

## Purpose

Extract high-value, reusable information from a conversation and persist it so
future sessions can pick up where this one left off — without re-reading the
entire conversation history.

This is a **write-through** skill: it does not just produce output, it **writes
files** to memory and knowledge base storage. Written files survive context
compaction because they are on disk, not in conversation context.

---

## When to Use

Invoke this skill when:
- The conversation is long or nearing context limits
- A milestone, phase, or significant task has been completed
- The user asks for a summary, checkpoint, or memory update
- Important insights, decisions, or patterns should not be lost

### Auto-Invocation

Claude Code does not have a built-in pre-compaction hook. To auto-trigger this
skill before compaction, configure a hook in your project or user settings:

```json
// In .claude/settings.json (project-level) or ~/.claude/settings.json (user-level)
{
  "hooks": {
    "PreCompact": {
      "prompt": "Run the session-distillation skill. Distill the conversation into memory updates and knowledge base entries."
    }
  }
}
```

Without this hook, invoke manually: `/session-distillation`

### Duplicate Prevention

If this skill runs twice in the same session, the second run must:
1. **Read existing entries first** — Check memory files and KB entries before writing
2. **UPDATE, don't CREATE** — If a topic already has an entry, update it in-place
3. **Only write NEW findings** — Skip anything already captured in the first run
4. **Re-sync the index** — Remove stale pointers, add new ones, stay under size limits

---

## Project Adaptation

This skill is project-agnostic. Adapt these paths for your project:

| Resource | Default Location | How to Find |
|----------|-----------------|-------------|
| Memory directory | `~/.claude/projects/<project>/memory/` | Check `MEMORY.md` location |
| Memory index | `MEMORY.md` in memory directory | Always at root of memory dir |
| Knowledge base | `<project-root>/knowledgebase/` | Look for existing KB structure |
| KB index | `knowledgebase/index.yaml` or `index.json` | If it exists, follow its format |

Before writing, **read the existing structure** to understand:
- What memory files already exist (check MEMORY.md)
- What KB format is used (check existing entries — YAML or JSON)
- What numbering scheme is used (DECISION#001, PATTERN#001, etc.)
- What the index file expects (if any)

If no knowledge base structure exists, create one using YAML (see Step 4). If
one exists with a different format (e.g., JSON), follow its conventions for
consistency — don't mix formats within the same project.

---

## What NOT to Save (Memory vs Knowledge Base)

Memory and Knowledge Base serve different purposes and have different
exclusion rules:

### Memory — Always-loaded, high-signal, short

Memory files are loaded into every conversation. They must be short and timeless.

**DO NOT save to memory:**
- Code patterns, conventions, architecture — derivable by reading files
- Git history, recent changes — `git log` / `git blame` are authoritative
- Debugging solutions or fix recipes — the fix is in the code
- Container IPs, port numbers, test counts — these change frequently
- Anything already documented in CLAUDE.md or README — always loaded
- Ephemeral task state — "currently working on X" (stale tomorrow)

**DO save to memory:**
- User preferences and corrections — how the user likes to work
- Architecture realities — gaps between docs and implementation
- Operational risks and gotchas — non-obvious things that cause debugging
- Cross-references — pointers to external systems (bug trackers, dashboards)

### Knowledge Base — On-demand, detailed, reusable

Knowledge base entries are loaded only when relevant. They can be longer and
include procedures and code examples.

**DO NOT save to knowledge base:**
- Ephemeral state — "currently working on X" (will be stale)
- Raw conversation logs — distill first, then save the insight
- Anything the user explicitly said not to save
- Information already in README, CLAUDE.md, or docs that won't go stale

**DO save to knowledge base:**
- Troubleshooting procedures — step-by-step diagnostic workflows
- Decision rationale — why a choice was made, alternatives rejected
- Patterns — reusable patterns with code examples
- Runbooks — operational procedures (how to diagnose, how to fix)
- Integration gotchas — non-obvious behaviors between components

---

## Step-by-Step Instructions

### Step 1 — Scan the Conversation

Read the full conversation and classify findings:

| Category | What to Look For | Persist To |
|----------|-----------------|------------|
| **Decisions** | Choices with rationale, rejected alternatives | KB (decision) |
| **Gotchas** | Non-obvious behaviors that caused debugging | Memory (project) + KB (pattern) |
| **Architecture realities** | Gaps between docs and implementation | Memory (project) |
| **User preferences** | How the user likes to work, corrections | Memory (user or feedback) |
| **Bug root causes** | Why something broke and how it was fixed | KB (pattern) |
| **Integration details** | How components actually connect | Memory (project) |
| **Troubleshooting procedures** | Step-by-step diagnostic workflows | KB (pattern) |
| **Operational risks** | Things that could go wrong in production | Memory (project) |

### Step 2 — Check for Existing Entries

Before writing anything, read the existing files:

1. **Read the memory index** (e.g., `MEMORY.md`) — Check what topics already have entries
2. **Read existing memory files** — Don't duplicate topics
3. **Check existing KB entries** — Don't create DECISION#012 if it already exists
4. **Check existing patterns** — Don't create PATTERN#005 if it already exists
5. **Check session log** — Don't add a duplicate session entry

If an entry already exists for a topic:
- **UPDATE it** with new information (change timestamps, add new details)
- **DO NOT create a new entry** for the same topic
- **DO NOT duplicate** pointers in the index

### Step 3 — Write Memory Entries

Use this frontmatter format for each memory file:

```markdown
---
name: <descriptive name — specific enough to judge relevance>
description: <one-line summary — used to decide relevance in future sessions>
type: user | feedback | project | reference
---

<content>

## For feedback type:
<rule>

**Why:** <reason the user gave or incident that triggered it>
**How to apply:** <when/where this guidance kicks in>

## For project type:
<fact or decision>

**Why:** <motivation — constraint, deadline, or stakeholder ask>
**How to apply:** <how this should shape future suggestions>
```

Then update the memory index (e.g., `MEMORY.md`):

```markdown
- [<Title>](<filename>.md) — one-line hook (~150 chars max)
```

Rules for the memory index:
- Keep under 200 lines total (it's always loaded into context)
- One line per entry, organized semantically (not chronologically)
- Remove or consolidate stale entries before adding new ones
- Do NOT duplicate — search before adding

### Step 4 — Write Knowledge Base Entries

#### Decisions

```yaml
# knowledgebase/decisions/DECISION#NNN.yaml
id: DECISION#NNN
title: <concise title>
status: ACCEPTED
date: YYYY-MM-DD
lastUpdated: YYYY-MM-DD

context: >
  What situation triggered this decision. Keep it focused on
  the problem, not the solution.

decision: >
  What was decided and why. Include the key rationale.

consequences:
  pros:
    - <benefit 1>
    - <benefit 2>
  cons:
    - <drawback 1>
    - <drawback 2>

alternatives:
  - option: <alternative considered>
    rejectedBecause: <why it was rejected>
  - option: <another alternative>
    rejectedBecause: <why it was rejected>

affectedFiles:
  - <path/to/file1>
  - <path/to/file2>

relatedDecisions:
  - DECISION#XXX
```

**Example:**

```yaml
# knowledgebase/decisions/DECISION#012.yaml
id: DECISION#012
title: StringBuilder pattern for pacs.002 and camt.054 generation
status: ACCEPTED
date: 2026-04-11
lastUpdated: 2026-04-11

context: >
  Need to generate pacs.002 and camt.054 XML but JAXB model classes
  (PaymentStatusReportV15) lack setters, making programmatic construction
  verbose and fragile.

decision: >
  Use StringBuilder-based builders (Pacs002Builder, Camt054Builder) consistent
  with Acmt023Builder, rather than modifying JAXB models or using template
  engines.

consequences:
  pros:
    - No cross-service dependency on JAXB model changes
    - Consistent with existing Acmt023Builder pattern
    - Simple to implement and test
  cons:
    - Not type-safe, manual XML construction
    - Risk of malformed XML if fields contain special characters (mitigated by escapeXml())

alternatives:
  - option: Add setters to JAXB model classes
    rejectedBecause: JAXB classes are generated, modifications would be overwritten
  - option: Use Velocity/FreeMarker templates
    rejectedBecause: Adds template engine dependency for simple XML generation

affectedFiles:
  - services/payment-service/src/main/java/com/nexus/payment/service/service/Pacs002Builder.java
  - services/payment-service/src/main/java/com/nexus/payment/service/service/Camt054Builder.java

relatedDecisions:
  - DECISION#010
```

#### Patterns (including troubleshooting procedures)

```yaml
# knowledgebase/patterns/PATTERN#NNN.yaml
id: PATTERN#NNN
name: <pattern name>
category: ARCHITECTURE | IMPLEMENTATION | TESTING | OPERATIONS | TROUBLESHOOTING
status: documented
firstSeen: YYYY-MM-DD
lastUpdated: YYYY-MM-DD

description: >
  What this pattern does and when to use it.

context: >
  When and where this pattern applies. What problem it solves.

implementation: >
  How to implement or follow this pattern. For troubleshooting,
  include step-by-step diagnostic procedures.

examples:
  - <concrete example with code or commands>

relatedPatterns:
  - PATTERN#XXX
```

**Example — Architecture Pattern:**

```yaml
# knowledgebase/patterns/PATTERN#005.yaml
id: PATTERN#005
name: On-Demand Message Retrieval
category: ARCHITECTURE
status: documented
firstSeen: 2026-04-11
lastUpdated: 2026-04-11

description: >
  Generate ISO 20022 messages (pacs.002, camt.054) on demand via REST GET
  endpoints rather than pushing them asynchronously via JMS or storing them
  eagerly.

context: >
  The Nexus spec requires pacs.002 to be delivered to Source PSP and camt.054
  to be generated periodically. However, JMS MDBs are not yet deployed and
  no scheduled generation infrastructure exists. The on-demand pattern provides
  immediate functionality with zero infrastructure cost.

implementation: >
  1. Builder class (Pacs002Builder, Camt054Builder) generates XML from Payment entity
  2. XML is stored in a TEXT column on the Payment entity at terminal state transitions
  3. REST GET endpoint retrieves stored XML, or generates on-demand if not yet stored
  4. For non-terminal states, return 400 Bad Request

examples:
  - |
    # Pacs002Builder generates ACCC on COMPLETED, RJCT on FAILED
    payment.setPacs002Xml(pacs002Builder.buildPacs002Xml(payment));

    # GET endpoint retrieves stored XML
    GET /api/v1/payments/{uetr}/status-report  → application/xml (pacs.002.001.15)
    GET /api/v1/payments/{uetr}/reconciliation  → application/xml (camt.054.001.11)

relatedPatterns:
  - PATTERN#001  # Two-Leg Settlement
```

**Example — Troubleshooting Pattern:**

```yaml
# knowledgebase/patterns/PATTERN#006.yaml
id: PATTERN#006
name: Debugging Payment State Machine Transitions
category: TROUBLESHOOTING
status: documented
firstSeen: 2026-04-11
lastUpdated: 2026-04-11

description: >
  Step-by-step procedure for diagnosing why a payment is stuck in an
  unexpected state or failing state transitions.

context: >
  The payment state machine has 15+ states with specific allowed transitions.
  Invalid transitions are silently rejected, making debugging difficult.

implementation: >
  1. Check current state: GET /api/v1/payments/{uetr}
  2. Check errorDescription field for failure reason
  3. Check which timestamps are populated (leg1ConfirmedAt, leg2ConfirmedAt, failedAt)
  4. Check fxQuoteId — if null, FX reservation failed
  5. Check leg1TransactionId — if null, Leg 1 never executed
  6. Check leg2TransactionId — if null, Leg 2 never executed
  7. For SANCTIONS_REVIEW: InstrPrty=NORM sets timeCritical=false
  8. For LEG2_FAILED: check CompensationService logs for reversal status
  9. Check PaymentStateMachine.getAllowedTransitions(currentState) for valid paths

examples:
  - |
    # Payment stuck in SANCTIONS_REVIEW
    # Cause: InstrPrty=NORM (timeCritical=false) defers Leg 2
    # Fix: Call SanctionsReviewService.handleSanctionsCleared() to resume
    # Or: Submit with InstrPrty=HIGH for time-critical path

    # Payment in FAILED with errorDescription "Leg 2 rejected"
    # Cause: Destination SAP returned insufficient funds
    # Fix: Check SAP-MYS FXP balance, CompensationService should have reversed Leg 1

relatedPatterns:
  - PATTERN#001  # Two-Leg Settlement
```

#### Sessions

```yaml
# knowledgebase/sessions/SESSION#YYYY-MM-DD#NNN.yaml
sessionId: SESSION#YYYY-MM-DD#NNN
date: YYYY-MM-DD
summary: >
  What was accomplished in this session.

decisions:
  - DECISION#XXX

filesChanged:
  - <path/to/key/file1>
  - <path/to/key/file2>

topics:
  - <relevant topic 1>
  - <relevant topic 2>
```

### Step 5 — Update the Index

After writing entries, update the project's index file (if one exists):

- Increment entry counts for affected categories
- Update the latest session reference
- Add new topic tags if new topics were introduced
- Update any "quick reference" or "gotchas" sections
- Verify totals match actual file counts

If no index file exists, create one following this structure:

```yaml
# knowledgebase/index.yaml
version: "1.0"
lastUpdated: YYYY-MM-DD
indexes:
  decisions:
    folder: knowledgebase/decisions/
    count: N
    latest: DECISION#NNN
  patterns:
    folder: knowledgebase/patterns/
    count: N
  sessions:
    folder: knowledgebase/sessions/
    count: N
    latest: SESSION#YYYY-MM-DD#NNN
quickReference:
  gotchas:
    - <non-obvious behavior 1>
    - <non-obvious behavior 2>
  implementationStatus:
    <ServiceName>: <status>
```

### Step 6 — Verify Consistency

Before finishing, verify:

1. **Memory files exist** — Every file referenced in the index exists on disk
2. **No duplicates** — No topic has two memory entries; no two decisions cover the same topic
3. **No stale entries** — If a memory entry contradicts the current codebase, update it
4. **KB files are valid** — Parse-check any new YAML files
5. **Index counts are accurate** — Count actual files in directories
6. **Memory index under limit** — If over 200 lines, consolidate low-value entries

### Step 7 — Report

Output a structured summary of what was written and what was intentionally skipped:

```
## Session Distillation Complete

### Memory Updates
- Created: `feedback_<topic>.md` — <one-line summary>
- Updated: `architecture-reality.md` — <what changed>
- Updated: `MEMORY.md` — <what was added/removed>

### Knowledge Base Entries
- Created: `DECISION#NNN.yaml` — <one-line summary>
- Created: `PATTERN#NNN.yaml` — <one-line summary>
- Created: `SESSION#YYYY-MM-DD#NNN.yaml` — <one-line summary>

### Index Updates
- Updated index.yaml: <what changed>

### Items Intentionally NOT Saved
(derivable from codebase — will remain current without persistence)
- <item 1> — visible in <file>
- <item 2> — visible in <file>
```

---

## Quick Reference: Memory Types

| Type | Purpose | Example | Size |
|------|---------|---------|------|
| `user` | User preferences, role, style | "Prefers terse responses" | 5-15 lines |
| `feedback` | Corrections, approaches to repeat/avoid | "Don't mock the DB in tests" | 5-20 lines |
| `project` | Architecture realities, risks, status | "All MDBs are stubs" | 10-50 lines |
| `reference` | Pointers to external systems | "Bugs tracked in Linear INGEST" | 3-10 lines |

## Quick Reference: KB Entry Types

| Type | Purpose | Example |
|------|---------|---------|
| `DECISION` | Design choice with rationale | "Use StringBuilder for XML generation" |
| `PATTERN` | Reusable solution or procedure | "Two-leg settlement pattern" |
| `SESSION` | Session summary for continuity | "Implemented auth module" |
| `TROUBLESHOOTING` | Diagnostic workflow | "How to debug payment state transitions" |
