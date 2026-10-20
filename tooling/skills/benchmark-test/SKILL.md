---
name: "benchmark-test"
description: "Design, run and report a rigorous benchmark or A/B comparison so the result can be defended: find the binding constraint before measuring, keep the arms identical but for the variable, check the load generator is not the limit, use paired runs with alternating order, report an MDE and refuse to claim inside it, and state the regime each number came from. Use when asked to benchmark something, compare two variants (protocols, versions, configurations, services, libraries, algorithms), measure capacity or latency under load, measure behaviour under impairment or fault injection, review a performance claim, or explain why a benchmark disagrees with expectation."
version: 1
created: "2026-10-17"
updated: "2026-10-17"
---

# Benchmark Test

A benchmark is an experiment. It fails far more often for methodological reasons than for
statistical ones: the system was saturated, the harness was the real limit, the two arms differed
in more than the variable, or the metric being reported could not express the effect. This skill
is the procedure for avoiding those, and for reporting honestly when they cannot be avoided.

## When to Use

- Comparing two or more variants: protocols, versions, configurations, services, libraries.
- Measuring capacity, latency, tail latency or reliability under load.
- Measuring behaviour under impairment, fault injection or resource pressure.
- Reviewing someone else's performance claim, or defending your own.
- A benchmark result that contradicts intuition, which usually means the rig is measuring something
  other than what it says.

Not for unit-level micro-optimisation of a single function, and not for correctness testing.

## Core Principle

**A benchmark measures the variable only if nothing else is the binding constraint.**

Everything below follows from that. Before trusting any difference, you must be able to say what
was limiting each arm, and it must be the thing you varied.

## Procedure

### Phase 1: Define the question before building anything

1. Write the claim in one sentence, with the arm and the baseline named.
2. **Pre-register the hypotheses** with the direction you expect, before the first run. A result
   read after the fact can always be made to look expected.
3. State the **practical threshold**, not only the statistical one. For example: "a 15 percent
   capacity regression at or above 50 concurrent clients is disqualifying". The statistical MDE
   answers "can I see it"; the practical threshold answers "does it matter".
4. State what would **falsify** the claim, and what would make it inconclusive.

### Phase 2: Inventory the rig

List, explicitly:

| Category | Examples | Why it matters |
| --- | --- | --- |
| The variable | the one thing that differs between arms | anything else that differs invalidates the comparison |
| Shared and therefore cancelling | the upstream backend, the network path, the data set | shared components drop out of the difference |
| Silent differences | client library, connection pooling, protocol negotiation, defaults, stream or buffer limits, cache state, connection reuse, thread counts | these are the usual cause of a surprising result |
| Observability | a per-run identifier tying client, server and intermediate telemetry together | without it you cannot attribute anything |

Prefer **one load source for both arms**, switching only the variable. Two client implementations
means the result is a comparison of those implementations.

### Phase 3: Find the binding constraint before measuring

1. **Ladder the offered load** (concurrency or fixed arrival rate) and plot achieved throughput.
2. **Read every component's** CPU, memory and queue depth, not only the component you care about.
3. Identify the **ceiling** (where throughput stops rising) and the knee.
4. Decide which regime the question lives in:

| Regime | What a latency difference then means |
| --- | --- |
| The variable binds (unsaturated) | a real end-to-end effect |
| A downstream component binds (saturated) | queueing, not your variable |

5. **If the downstream is irrelevant to the question, remove it.** Put a null or deterministic
   backend behind the interface under test so the measured component is the only path. This is
   often the single highest-value change, because a saturated backend both swamps small differences
   and hides the perturbation's effect on the arm that sits at the ceiling.

### Phase 4: Check that the harness is not the limit

1. Measure the **load generator's own** resource use, from a source you trust (a container cgroup
   counter is more trustworthy than a summary field in an orchestrator's API, which can report
   nonsense).
2. Rule out **throttling and quota** explicitly rather than assuming.
3. The diagnostic: **if two configurations consume the same CPU and deliver different throughput,
   the generator is the constraint.** The throughput ratio then equals the ratio of work per unit
   CPU, and the difference belongs to the client stack, not the system under test.

### Phase 5: Build the measurement

1. **Mint a per-run identifier** and stamp it on the request and on every metric series. Prefer a
   **request header** over time-window matching: window matching breaks on clock skew, on log
   rotation and on overlapping runs.
2. Collect, per run: the latency distribution, outcome counters (success, failure, error, retry,
   duplicate), and resource use.
3. **State the units.** A metric named in seconds read as milliseconds inverts a conclusion.
4. **Check the metric cannot be censored.** A histogram's top bucket is a ceiling: a p95 equal to
   the top bucket is a lower bound, not a measurement. Widen the buckets or report it as censored.
5. **Instrument the layer under test**, not only the client. A component's own view of the request
   (its internal service time, its queue, its connection reuse) is what separates your variable
   from everything else. Take care that it measures what you think: a metric that starts after a
   packet arrives cannot see delay before arrival.

### Phase 6: Validate the rig applies what you asked for

1. **Assert every perturbation is installed.** Read it back, do not request it and hope. A
   perturbation that silently no-ops makes every downstream result vacuous while looking fine.
2. State the direction of the perturbation. Delay applied to one direction only is not the same as
   network loss, and it does not treat protocols or retransmission strategies alike.
3. If the perturbation creates a queue, **set its limit explicitly** and log its drop and overlimit
   counters. Defaults can add loss nobody configured.
4. Match the perturbation to the mechanism under claim. If the hypothesis invokes bursty loss, a
   uniform loss model does not test it.

### Phase 7: Run it

1. **Paired arms, back to back**, with the order alternating across repeats. Whichever arm goes
   first also pays the warm-up, so a fixed order gives the second arm a head start on every cell.
2. **Balance the order**: an odd repeat count leaves one arm going first more often. Use an even
   count, or randomise, and check the balance.
3. Choose the repeat count from the **MDE you need**, not from convenience.
4. **Warm up**, and say whether the start of a window is discarded.
5. **One failing arm must not lose the matrix.** Record the failure, continue, and report it.
6. **Never treat a process exit code as a measurement result.** A strict client can exit non-zero
   on one error while delivering thousands of successful operations. Read the run's own counters.

### Phase 8: Analyse

1. **Paired differences**, not pooled distributions. Compute the difference per repeat.
2. Report the **MDE** per cell, and refuse to claim anything inside it. "Not resolved at this
   sample size" is a complete and honest finding.
3. For an **equivalence claim** ("the two are the same"), use an equivalence test with a stated
   margin. "Inside the MDE" is absence of evidence, not evidence of absence.
4. Check and state: **censored metrics**, **multiplicity** across many cells, **selection bias** if
   the confirmation set was chosen because it resolved, and **drift** (plot the metric against run
   index; a growing data set or cache can move things that alternating order only partly cancels).
5. Report the **regime** each number came from, and the units.

### Phase 9: Report

Structure that survives review:

1. **Summary**: the claim, the numbers, and the regime they came from.
2. **Environment**: versions, resources, topology, the perturbation model, what was shared.
3. **Method**: the fairness controls, what is measured and from where, the statistics, the
   decision rule.
4. **Criteria**: the pre-registered hypotheses with outcomes.
5. **Results**: per-cell numbers with units, MDE and verdict. Raw data, plus the analysis.
6. **Eliminations**: which alternative explanations were tested and killed, with how. This is the
   part that earns trust.
7. **Limitations**: what the sample size cannot resolve, what the rig could not control, what
   remains unexplained. State what a claim rests on rather than inventing the missing measurement.
8. **Artifacts**: where the data, the harness and the exact commands live.

Rules for the report: never present a censored number as a measurement; never present a saturated
regime as a transport or algorithm result; report cells that moved between runs rather than folding
them into the finding; and qualify any claim of generality that sits next to figures from one
deployment.

## Statistics Quick Rules

| n (repeats) | t for a 95 percent two-sided interval | Note |
| ---: | ---: | --- |
| 2 | 12.71 | effectively useless |
| 3 | 4.30 | a normal approximation understates the MDE by about 1.7x |
| 5 | 2.78 | a normal approximation understates by about 1.1x |
| 10 | 2.26 | |
| 30 | 2.05 | near the normal value |

- **MDE** as an absolute half-width: `t * s / sqrt(n)`, where `s` is the standard deviation of the
  paired differences. Express it against the **baseline value**, not against the difference itself:
  a relative form divides by a mean that is near zero when there is no real effect, and reports
  four-figure percentages.
- Keep a floor on the relative MDE (a few percent) so a suspiciously tidy sample is not read as a
  resolved difference.
- Rank tests do not rescue small samples: a signed-rank test at n=5 cannot go below a two-sided
  p of 0.0625.
- Prefer confidence intervals on the ratio (bootstrap or log-ratio) to a bare mean percentage.

## Pitfalls

- **Measuring a saturated system** and calling it a difference. Check the ceiling first.
- **The harness as the bottleneck.** Identical CPU with different throughput means the generator is
  the limit. This is the most common way a clean-path comparison silently becomes a client-stack
  comparison.
- **A perturbation that no-ops.** Verify it is installed and read its counters back.
- **One-directional impairment** described as network loss, which flatters whichever protocol
  handles lost acknowledgements worse.
- **A censored metric** reported as a measurement. A p95 equal to the histogram's top bucket is a
  lower bound.
- **Selecting the cells that resolved** and then treating the replication as independent evidence.
  It is a fine design, but the replicated effect sizes are biased upward and the report must say so.
- **Odd repeat counts** leaving the arm order unbalanced.
- **Process exit codes** as correctness signals, discarding good data from the cells that matter.
- **Time-window attribution** under clock skew, and log rotation that removes the window you need.
- **Results held only in an ephemeral container or a rotated log.** Persist them before any
  redeploy; a rebuild is the usual way a result is lost.
- **Trusting an orchestrator's per-task resource field.** Read the cgroup, and check the throttling
  counters rather than assuming.
- **Tool quirks that cost real time**: a command that truncates standard input at a few kilobytes
  (verify copies with a checksum), a duration printed in a compound form that a naive parse reads
  as its first field, and a summary line that appears per interval as well as once at the end, so
  taking the first match reads a progress line instead of the total.

## Worked Shape (abstracted)

A comparison of two variants of a message transport, end to end:

1. One load source for both arms, switching only the transport selection.
2. A first pass showed throughput flat from concurrency 5, with the downstream service at
   saturation: the concurrent cells were measuring a queue. **Finding the bottleneck changed the
   design.**
3. A null backend was placed behind the interface under test, which lifted the ceiling by two
   orders of magnitude and enlarged the measured effect from 20 to 60 percent into 70 to 85
   percent, because the arm that had been pinned at the ceiling could finally degrade visibly.
4. A resource check then showed the load generator saturating at about two cores, with both arms
   burning the same CPU for different throughput. That identified the clean-path difference as the
   client's cost per request rather than a property of the wire, and confirmed the impaired cells
   were unaffected because they used a small fraction of one core.
5. Each perturbation was verified as installed, its queue limit set explicitly, and its counters
   read back.
6. Two explanations were eliminated with experiments rather than argument: a connection-count
   hypothesis, by constraining one arm to a single connection, and a downstream-capacity
   hypothesis, by the null backend.

The reusable parts are steps 2, 4 and 6: find the constraint, check the harness, and eliminate
rival explanations with experiments.

## Verification

Before reporting a benchmark as done:

- [ ] The hypotheses and the practical threshold were written down before the first run.
- [ ] The arms differ in exactly one thing, and the silent differences listed in Phase 2 were
      checked rather than assumed.
- [ ] The binding constraint is known for each arm, in each regime reported.
- [ ] The load generator's own utilisation and throttling were measured, not assumed.
- [ ] Every perturbation was verified installed, with its counters read back.
- [ ] Per-run identifiers tie each number to its run, and to the component telemetry.
- [ ] The arms ran back to back with balanced, alternating order.
- [ ] Every reported cell has an MDE, and no claim sits inside it.
- [ ] No censored metric is presented as a measurement.
- [ ] Equivalence claims use an equivalence test with a margin.
- [ ] Rival explanations were eliminated by experiment, and the report says which.
- [ ] The raw data is persisted somewhere that survives a redeploy.
- [ ] The report states the regime, the units, the limitation, and what remains unexplained.
