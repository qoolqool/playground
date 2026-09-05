---
name: code-reviewer
description: >
  Senior code review skill covering correctness, security, performance, and
  maintainability across multiple languages. Establishes diff scope, runs
  automated pre-checks, applies a diff-first reading strategy, and produces a
  severity-tagged review (CRITICAL/HIGH/MEDIUM/LOW) with a merge recommendation.
  Use when reviewing pull requests, diffs, or changed files, or when asked to
  "review this code", "review this PR", or "check this diff".
---

# Code Reviewer

Act as a senior code reviewer with expertise in identifying code quality issues,
security vulnerabilities, and optimization opportunities across multiple
programming languages. Focus spans correctness, performance, maintainability,
and security, with emphasis on constructive feedback, best-practice
enforcement, and continuous improvement.

## When to Use

- Reviewing a pull request, diff, or set of changed files
- Asked to "review this code", "review this PR", "check this diff", or "review my changes"
- Before merging to main, after a major feature, or after each task in subagent-driven development
- When stuck (fresh perspective) or before a refactor (baseline check)

**Do NOT use** for: writing new code, one-off explanations, or generic questions
that don't involve reviewing existing code.

## Procedure

### 1. Establish the diff scope

- Run `git diff --name-only HEAD~1` (or `git diff --name-only origin/main...HEAD`) to list changed files, or read the specified files directly.
- Identify the primary concern (security, correctness, performance, or style).
- Note team conventions from `CLAUDE.md`, `.editorconfig`, or stated standards.

### 2. Run automated pre-checks (skip any tool not available; never fail the review for a missing tool)

- **Dependency CVEs:** `npm audit`, `pip-audit`, or `cargo audit` depending on the project.
- **Hardcoded secrets:** `grep -rE "(api_key|secret|password|token)\s*=\s*['\"][^'\"]{8,}" --include="*.py" --include="*.ts" --include="*.js"` on changed files.
- **Recent commit context:** `git log --oneline -5` to understand what changed and why.

### 3. Apply a diff-first reading strategy (scale to change size)

- **Under 20 files:** read each changed file in full before forming any opinion.
- **20–100 files:** read the diff first (`git diff HEAD~1`), then deep-read high-risk files — auth, payment, config, migration, and files touching shared utilities.
- **Over 100 files:** ask the user to narrow the scope to a specific module or risk area before proceeding.

### 4. Run the review checklist

**Security**
- Scan for injection vulnerabilities (SQL, command, path traversal) wherever user input touches a query or file operation.
- Verify authentication checks are present and cannot be bypassed.
- Confirm sensitive data (tokens, passwords, PII) is never logged or returned in responses.
- Check cryptographic primitives are standard-library functions, not hand-rolled.

**Error Handling**
- Verify every external call (network, database, file I/O) has explicit error handling.
- Confirm errors are logged with enough context to diagnose without leaking internals to callers.
- Check that resource cleanup (files, connections, locks) happens in `finally` blocks or equivalent.

**Tests**
- Read existing tests to confirm they assert behavior, not implementation.
- Check for missing edge cases: empty inputs, boundary values, concurrent access if relevant.
- Verify mocks are isolated and do not bleed state between tests.

**Dependencies**
- Cross-reference new/updated packages against the audit output from pre-checks.
- Flag packages with no recent activity or suspicious version jumps.
- Note license changes that may conflict with the project's license.

**Performance**
- Identify database queries inside loops (N+1 pattern).
- Check that large collections are paginated or streamed rather than loaded entirely into memory.
- Note missing indexes on foreign keys referenced in queries.

### 5. Apply language-specific checks

**TypeScript**
- Flag every use of `any` — require a typed alternative or an explicit suppression comment explaining why.
- Confirm `strict: true` is present in tsconfig; report if absent.
- Verify Promises are awaited or explicitly handled; search for floating Promise chains.
- Check that null/undefined are handled before property access in critical paths.

**Python**
- Flag mutable default arguments (`def fn(items=[])`) — these cause shared-state bugs.
- Flag bare `except:` clauses — require at least `except Exception`.
- Require type hints on all public function signatures.
- Flag `eval()` and `exec()` on any user-supplied input.

**Rust**
- Flag `.unwrap()` and `.expect()` outside of test modules — require `?` propagation or explicit match.
- Require `// SAFETY:` comments on every `unsafe` block explaining the invariant being upheld.
- Flag missing lifetime annotations on public API functions that return references.

**Go**
- Flag every error return discarded with `_` in non-trivial paths.
- Check for goroutines launched without a cancellation path (missing `ctx` propagation).
- Flag `defer` inside loops — defer does not run until the surrounding function returns.

**SQL**
- Flag any `UPDATE` or `DELETE` statement missing a `WHERE` clause.
- Identify N+1 query patterns — a query inside a loop that could be a single JOIN or batch query.
- Check foreign key columns referenced in `JOIN` or `WHERE` clauses have an index.

### 6. Two-pass review (prioritize what blocks merge)

**Pass 1 — CRITICAL (blocks merge)**
- **SQL & data safety:** string interpolation in SQL (use parameterized queries); TOCTOU races (check-then-set should be atomic); N+1 queries (missing eager loading in loops).
- **Race conditions & concurrency:** `findOrCreate` without a unique DB index (concurrent dups); status transitions without atomic `WHERE old → UPDATE new`; unescaped HTML rendering on user-controlled data (XSS).
- **LLM output trust boundary:** LLM-generated values (emails, URLs, names) written to DB without validation; structured tool output accepted without type/shape checks. Guards needed: `EMAIL_REGEXP`, `URI.parse`, `.strip`, JSON schema.

**Pass 2 — INFORMATIONAL (in PR body, non-blocking)**
- Dead code, magic numbers, string coupling.
- Test gaps (negative paths, format assertions).
- Time window mismatches, type coercion at boundaries.
- Crypto: `Math.random()` for secrets → use `crypto.randomUUID()`.

**Suppressions — DO NOT flag these**
- Redundant checks that aid readability (e.g., `!= null` when already checked).
- "Add a comment explaining this threshold" — thresholds change, comments rot.
- Consistency-only changes (wrapping a value in a conditional to match another).
- Eval threshold changes — tuned empirically.
- Harmless no-ops (e.g., `.filter` on an element never in the array).
- Anything already addressed in the diff being reviewed.

### 7. Assess quality, design, docs, and debt

- **Code quality:** logic correctness, error handling, resource management, naming, organization, function complexity, duplication, readability.
- **Design patterns:** SOLID, DRY, pattern appropriateness, abstraction levels, coupling, cohesion, interface design, extensibility.
- **Documentation:** code comments, API docs, README, architecture docs, inline docs, example usage, change logs, migration guides.
- **Technical debt:** code smells, outdated patterns, TODO items, deprecated usage, refactoring needs, modernization opportunities, cleanup priorities, migration planning.

### 8. Produce the output

Every finding must follow this structure:

```
[CRITICAL] file:line — short description
  Risk: what can go wrong if this is not fixed
  Fix: concrete code change or approach to resolve it

[HIGH] file:line — short description
  Risk: ...
  Fix: ...

[MEDIUM] file:line — short description
  Risk: ...
  Fix: ...

[LOW / SUGGESTION] file:line — short description
  Risk: ...
  Fix: ...
```

Close every review with:

```
Review Summary: examined [N] files, found [N] CRITICAL, [N] HIGH, [N] MEDIUM, [N] LOW findings.
Top priority: [brief description of most important finding].
Merge recommendation: BLOCK / APPROVE WITH SUGGESTIONS / APPROVE.
```

### 9. Give constructive feedback

- Provide specific examples for every finding.
- Explain the risk, not just the rule violated.
- Offer an alternative solution, not just a critique.
- Acknowledge code that is correct and well-structured.
- Indicate priority so developers know what to fix first.
- Follow up on previously raised issues when reviewing updated code.

## Pitfalls

- **Skipping the diff scope** — reviewing without knowing what changed leads to noise and missed context.
- **Failing to scale the reading strategy** — reading 100+ files in full is wasteful; ask to narrow scope.
- **Flagging suppressed items** — don't flag readability aids, threshold-comment requests, consistency-only changes, or anything already addressed in the diff.
- **Missing the LLM trust boundary** — LLM-generated or tool-returned values written to DB without validation is a CRITICAL-class issue.
- **Reviewing implementation, not behavior** — tests should assert behavior; don't praise tests that only check internals.
- **No merge recommendation** — always end with the summary line and a clear BLOCK / APPROVE WITH SUGGESTIONS / APPROVE.
- **Ignoring pre-check tooling** — run audits and secret greps first; they surface quick wins cheaply.

## Verification

- [ ] Diff scope established (changed files enumerated) before reading code
- [ ] Pre-checks run (audit, secret grep, recent commit log) or explicitly skipped as unavailable
- [ ] Reading strategy scaled to change size (full read / diff+deep-read / narrowed scope)
- [ ] Every finding tagged with severity and includes Risk + Fix
- [ ] Review ends with the summary line and a merge recommendation
- [ ] Suppression list respected (no readability/threshold/consistency-only noise)
- [ ] Constructive feedback: specific examples, risk explained, alternative offered, strengths acknowledged
