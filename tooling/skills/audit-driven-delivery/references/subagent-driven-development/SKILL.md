---
name: subagent-driven-development
description: Execute implementation plans by dispatching fresh subagents per task with two-stage review (spec compliance then code quality). Use during Phase 3 (EXECUTE) of ADD when tasks are mostly independent.
---

# Subagent-Driven Development (Reference)

Execute plan tasks by dispatching a fresh subagent per task, with two-stage review after each: spec compliance first, then code quality. This is the recommended approach for **Phase 3 (EXECUTE)** of the ADD pipeline when tasks are mostly independent.

**Core principle:** Fresh subagent per task + two-stage review (spec then quality) = high quality, fast iteration.

> **ADD integration:** The ADD audit (Phase 0) and design (Phase 1) must be complete before using this. The plan (Phase 2) defines the tasks this skill executes.

## Prerequisites

- Active branch (not main) or user-confirmed intent to work on main
- Approved implementation plan from ADD Phase 2 with clear task boundaries
- DinD context understood (commands run inside the DinD container)

## When to Use This vs. Manual Execution

| Factor | Subagent-Driven | Manual (ADD Phase 3 default) |
|--------|----------------|------------------------------|
| Task coupling | Mostly independent | Tightly coupled |
| Context isolation | Fresh subagent per task | Same agent context |
| Review cadence | Two-stage after each task | Per-batch human review |
| Speed | Fast iteration | Human-in-loop between batches |

**Dependent tasks:** For tasks with dependencies, include the previous task's implementation summary and relevant file paths in the next subagent's context. Track what each completed task produced so you can pass it forward.

## Process

### 1. Prepare

Read the plan, extract all tasks with full text, note context, and initialize tracking:

```markdown
Tasks:
1. [Task name] — [brief]
2. [Task name] — [brief]
...
```

### 2. Per-Task Cycle

For each task, follow this cycle:

```
┌─ Dispatch implementer subagent ─────────────────────┐
│  • Include full task text + context                  │
│  • Answer questions before they proceed              │
│  • Implement, test, commit, self-review              │
└──────────────────────┬───────────────────────────────┘
                       ↓
┌─ Spec compliance review ────────────────────────────┐
│  • Dispatch spec-reviewer subagent                   │
│  • Read actual code, compare to requirements         │
│  • Report missing or extra work                      │
└──────────────────────┬───────────────────────────────┘
          ┌────────────┴────────────┐
          ▼                        ▼
     Issues found             ✅ Compliant
          │                        │
          ▼                        ▼
  Implementer fixes           Code quality review
  → Re-review                    │
                          ┌──────┴──────┐
                          ▼             ▼
                     Issues found    ✅ Approved
                          │             │
                          ▼             ▼
                   Implementer     Mark task
                   fixes           complete
                   → Re-review
```

### 3. Final Review

After all tasks complete and are individually reviewed, dispatch a final code reviewer for the entire implementation.

### 4. Report

Stop and report to the user. Do NOT auto-proceed to finishing.

## Implementer Subagent

Dispatch an implementer subagent with full task text and context. The implementer:

1. Asks clarifying questions before starting
2. Determines TDD scenario:
   - New code → full TDD (failing test first)
   - Modifying tested code → run existing tests before and after
   - Trivial change → use judgment, run tests after
3. Implements exactly what the task specifies
4. Verifies implementation works
5. Commits work
6. Self-reviews
7. Reports back

### Implementer Prompt Template

Use `./implementer-prompt.md` as the template when dispatching.

```ts
subagent({
  agent: "implementer",
  task: "Full prompt text from implementer-prompt.md, filled with task specifics"
})
```

### If Implementer Fails

1. **Attempt 1:** Dispatch a NEW fix subagent with specific instructions about what went wrong and what needs to change. Include the error output and the original task text.
2. **Attempt 2:** If the fix subagent also fails, dispatch one more with a different approach or simplified scope.
3. **After 2 failed attempts: STOP.** Report the failure to the user and ask how to proceed.

**Never:** write code yourself to "help" or "finish up". You are the orchestrator, not an implementer.

## Spec Compliance Review

After each task is implemented, dispatch a spec-reviewer subagent. The reviewer:

- **Reads the actual code** — does NOT trust the implementer's report
- Compares implementation to requirements line by line
- Checks for missing pieces (claimed but not implemented)
- Checks for extra features (not in spec)

### Spec Reviewer Prompt Template

Use `./spec-reviewer-prompt.md` as the template.

```ts
subagent({
  agent: "spec-reviewer",
  task: "Full prompt text from spec-reviewer-prompt.md, filled with task requirements and implementer report"
})
```

### If Issues Found

1. Implementer (same subagent) fixes the spec gaps
2. Spec reviewer re-reviews
3. Repeat until ✅

**Never proceed to code quality review until spec compliance is ✅.**

## Code Quality Review

After spec compliance passes, dispatch a code-reviewer subagent. The reviewer:

- Reviews code quality, architecture, testing
- Categorizes issues by severity: Critical, Important, Minor
- Assesses production readiness

### Code Quality Reviewer Prompt Template

Use `./code-quality-reviewer-prompt.md` as the template (references the code reviewer format).

```ts
subagent({
  agent: "code-reviewer",
  task: "Full prompt text from code-quality-reviewer-prompt.md, filled with implementation details and git SHAs"
})
```

### If Issues Found

1. Implementer fixes the quality issues
2. Code reviewer re-reviews
3. Repeat until ✅

## Red Flags

**Never:**
- Skip reviews (spec compliance OR code quality)
- Proceed with unfixed issues
- Dispatch multiple implementation subagents in parallel (causes conflicts)
- Make subagent read plan file (provide full text instead)
- Skip scene-setting context
- Ignore subagent questions
- Start code quality review before spec compliance is ✅
- Write code yourself to "help" — you are the orchestrator

## DinD Integration

When running in a DinD environment, subagent commands must account for the nested execution context:

```bash
# Commands inside DinD
docker exec <dind-container> docker compose -f /workspace/docker-compose.yml up -d --build
docker exec <dind-container> docker exec <test-runner> python3 -m pytest tests/ -v
```

The implementer subagent should be told to work from the correct directory (the DinD workspace or the project root depending on the task).

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This reference skill |
| `implementer-prompt.md` | Prompt template for implementer subagents |
| `spec-reviewer-prompt.md` | Prompt template for spec compliance reviewers |
| `code-quality-reviewer-prompt.md` | Prompt template for code quality reviewers |
