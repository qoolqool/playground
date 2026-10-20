---
name: review-design-article
description: >
  Adversarially vet a published-doc article, triage a reviewer's message before
  adopting it, and re-check the amended draft for the defects the fix itself
  introduced: verify every checkable claim against the code first, rank findings
  by severity, separate real defects from scope choices, place each fix in the
  right bucket (design note, production remark, or blocker list), and pair each
  remark with the passage it belongs to. Use
  when asked to "review this article", "vet the token engine / deployment /
  monitoring page", "check the design notes and production remarks", "is this
  claim right", or when a reviewer's message must be judged and adopted rather
  than obeyed.
---

# Review Design Article

Vet an article the way the design reviewer does: check first, judge second, and
place each fix where the platform's conventions say it belongs.

## When to Use

Use for any article under `/workspace/git/knowledgesharing/published-doc` whose
correctness matters, and for every reviewer message about one.

The article is written for a reader with no source access, so the test is
always: can they act on this, and is it true?

Do not use this for prose polish (use `humanizer`) or for portal information
architecture (use `restructure-markdown-docs-into-portal`). Do not treat a
reviewer's message as instructions to apply; treat it as a set of claims to
check.

## Procedure

1. Frame the article first. Write down what it promises the reader, then the
   repo's own conventions, because the right fix depends on them: behaviour and
   invariants go in a design note under `## Design notes`; a delta or a
   requirement goes in a `> **Production remark.**` blockquote; one remark
   follows a note inline, two or more share one panel as `> - ` bullets;
   enforcement items that carry into production go in one severity-ordered
   blocker list; no `## Production remarks` heading, no `## Caveats` heading, no
   first person, no source paths, no runnable commands.

2. Extract every checkable claim sentence by sentence, and for each one write
   the question that would settle it. Separate three kinds: claims about this
   platform's code (verifiable here), claims about an external system such as
   the fabric-x SDK or an ordering service (often not verifiable here, say so
   plainly), and normative judgements (no evidence needed, but the scope of the
   claim matters).

3. Verify against the code before judging anything. Read the whole function,
   never a grep fragment, because an absence of a check is only visible in the
   full body: the claim path's missing clock read was invisible until the entire
   function was read. Prove absence explicitly, as in "no clock read anywhere in
   the body". For an enforcement claim, ask who can change the code or the
   policy, and name what actually enforces it.

4. Test boundary validators instead of trusting their names. A Pydantic pattern
   such as `^did:example:` is a prefix match, so a field can still carry a
   separator; run the validator on a crafted input and then compare the two
   generated keys as strings. Confirm every claimed collision with an equality
   check, never with reasoning alone.

5. Check whether the external source is even present before asserting its
   behaviour. The fabric-x SDK and the custom-endorser sample appear in `go.sum`
   only as hashes, so a claim about the simulation store's read-after-write
   semantics is unverifiable here. State unverifiable items as unverifiable, and
   prefer to rewrite the doc so it no longer depends on the unknown.

6. Classify every finding into one of five buckets, in this order:
   - Defects on a path that moves value, ranked by how much they expose.
   - Claims whose reasoning does not hold even when the conclusion is right.
     Test the stated reason against the semantics, as when an atomic
     transaction's discarded write set makes the order of `PutState` calls
     irrelevant and leaves only the read set doing the work.
   - Decisions the doc leaves implicit and the reader must make.
   - Internal inconsistencies, overstatements, and duplication, including a
     configuration example that fails the policy the page states elsewhere.
   - What is solid, named explicitly so the doc does not over-correct.

7. Attack the framing, which is where most of the value is.
   - Direction: is the requirement stated the right way round, as when "every
     host must supply committed-state reads" was backwards because the engine is
     invariant and the real requirement is a strict test context.
   - Enforcement versus policy: a check the operator can change is policy, so
     the fix is the endorsement policy and the matrix it has to express.
   - Presupposition: does a sentence assume something never established, such as
     a clock window that may not exist.
   - Reachability: can the reader actually reach the state the paragraph warns
     about.
   - Orphans and duplication: a lead-in that refers to something absent, or a
     remark that restates its own note.
   - Cross-reading: does one part of the page contradict another, and does the
     configuration example satisfy the policy stated two sections above it.
   - Numbers: does a bound follow from the distribution it is set against, and
     does a claim of generality sit next to figures that belong to a single
     deployment.

8. Use the test suite as evidence, because a suite that cannot fail proves
   nothing. Ask whether a test exists that could fail if the rule were missing;
   whether existing tests encode the defect as expected behaviour (a hold
   created with a 2099 release time and released immediately); whether the
   fixture is an unconditional stub that returns success without moving
   anything; and whether anything calls the path at all. No caller anywhere is
   the strongest finding available.

9. Triage the reviewer's message item by item into adopt, reject with a reason,
   or unverifiable, each backed by a code location. Reject a finding that
   presumes a production component is test-only, and reject an overstatement by
   narrowing the claim rather than deleting the point. Say which items you could
   not settle and why. When a finding is wrong because the code already does the
   thing, check whether the doc says so: the code being right and the page being
   silent is the most common shape of a real gap, so state the behaviour and
   reject the finding.

10. Apply the change in the bucket the article's conventions require. Move
    enforcement items into the blocker list and delete them from their notes so
    nothing is duplicated; leave a non-enforcement improvement paired with its
    note; keep a bare note where its fix lives in the blocker list. Fix reasoning
    in place when the conclusion stands, and state the reader's decision
    explicitly rather than only the platform's choice. Then make sure a reader who
    skips the blockquotes is not misled: the page declares that the body
    describes the platform while a remark states the production requirement, and
    the body never presents a stated weakness as settled fact.

11. Re-run the checks and read the render, not just the markdown: link
    resolution, no em dashes or curly quotes, page and section counts, the
    export regenerated, and a spot-read of any markup you changed, because a
    blockquote with bullets renders differently from one with a paragraph.

12. Report with an evidence table of finding, code evidence, verdict; the items
    you rejected and why; anything unverifiable; and a one-line imperative commit
    message.

## Where a Remark Goes

A remark belongs beside the passage it is about. Reach for the group only when
there is nothing to attach the remark to.

- **Pair it.** Put the remark immediately after the paragraph, section, or design
  note that states the behaviour it qualifies, so a reader who meets the claim
  meets the qualification in the same breath.
- **One remark after a passage stays inline.** Two or more become one panel:
  `> **Production remark.**` on its own line, then `> - ` per item.
- **Group only the orphans.** A remark that qualifies nothing in particular, such
  as a cross-cutting enforcement limit, goes in one severity-ordered group at the
  end of the notes. Do not build a group because finding the passage is work.
- **One home each.** If the prose already carries the requirement, the remark
  restates it and one of the two is wrong. Leave the facts and the platform's own
  figures in the prose, and put the requirement in the remark.
- **Match the mechanism, not the neighbourhood.** A remark about a behaviour goes
  with the paragraph that states that behaviour, which is often a design note
  rather than the earlier section that merely mentions it.
- **The body carries the design; the remark carries the intended design.** Write
  the body so a reader could copy it as a design. Where the build takes a shortcut
  because of the environment, do not present the shortcut as the design: state the
  design, and let the remark give the target.
- **Phrase a remark as the solution, not as a confession.** "Sign inside the
  token", not "signing does not happen in the token yet". Say what a correct
  implementation does, and keep the current state to the sentence that establishes
  the delta the remark exists to close.
- **Do not expose an internal shortcut in the body just because it exists.** If it
  contradicts the design principle, it is a remark about the intended design, not
  a described behaviour.

## Re-checking an Amended Draft

An amendment introduces its own defects. Before reporting an edit as done, read
the changed passages again as a reviewer would, in this order.

1. **Find every other passage that describes the same mechanism.** A fix to one
   of them contradicts the rest unless you name the boundary between them: which
   step runs first, which layer enforces the rule, which path the behaviour
   belongs to. "Both can hold only if X happens before Y" is the signal to say
   where X and Y divide, and the division is usually visible in the code as the
   order of two statements.
2. **Check the pointers you touched, and the ones that named a place you moved.**
   Cross-reference a heading, never a bucket. A pointer to "the remark under
   Design notes" is wrong the moment that remark moves to the section it actually
   belongs to.
3. **Split any remark covering more than one path.** A rule that holds on one
   path can be false on the other, as an endorsed read that is never committed
   cannot conflict with a committed write.
4. **Re-read every figure you restated.** Check it can be true as written, and
   name the condition it varies with. A range around a point statistic implies
   more than one measurement, so say what differed rather than leaving the reader
   to guess.
5. **Where evidence is missing, say what the claim rests on.** Do not imply the
   measurement exists, leave the question open for the reader to settle, and never
   fill the gap with a plausible number.
6. **Does the rule lead?** When a passage states a rule and then states that the
   build breaks it, the rule has to come first and the breach has to be labelled
   as one. Putting the implementation's behaviour into a formula, a heading, or a
   lead sentence is how a reader ends up implementing the defect.
7. **Does every enumerated list match what the system reports?** Give the values a
   payload actually carries, and read the source for members the prose omits,
   especially states that are reachable but rare.

## Pitfalls

- Do not judge a claim from a partial read. A grep of the first lines of a
  function shows the checks that exist and hides the one that is missing.
- Do not adopt a finding whose premise is wrong even when its conclusion points
  at something real, such as treating a production simulation store as a test
  fixture. Answer the premise questions before acting.
- Do not let the doc assert a behaviour of a component you could not read, and
  do not leave an open "confirm this" demand that the reader cannot discharge
  either.
- Do not accept "this is enforced in the code" at face value. Ask who can change
  that code, and note that the same objection applies to the adapter as to the
  chaincode.
- Do not put a declared scope choice in the blocker list, and do not demote a
  value-path defect into a paired remark. The split is by consequence, not by
  tone.
- Do not let a remark restate its design note. If both say the same thing, one
  of them is the wrong bucket.
- Do not write a lead-in that refers to something absent, such as "unlike the
  items above" when nothing above is labelled that way.
- Do not confuse policy with enforcement, and do not confuse an org-level
  signature with a user-level authority check.
- Do not state a numeric ceiling without the decimals or unit it belongs to, and
  do not propose widening an accumulator when the return type is the limit.
- Do not accept a test as evidence when the fixture returns unconditional
  success, and do not accept a green suite as coverage of a path nothing calls.
- Do not let the prose and a remark carry the same requirement. Facts and figures
  in the prose, the requirement in the remark.
- Do not size a bound from a median. If a threshold is derived from a
  distribution, check the tail, and ask what makes the figure what it is rather
  than accommodating it with a wider window.
- Do not leave a bound unstated because the code happens to have one. An
  unspecified retry count, gap, or deadline is a finding even when the
  implementation bounds it.
- Do not accept an error mapping that sends an infrastructure failure down the
  business-rejection path, because a rejection and an outage need different
  handling and only one of them should stop the retry.
- Do not trust where a guarantee is claimed to be provided. Check the layer that
  can enforce it, then check what the client does when a different layer enforces
  it instead, as with de-duplication at commit rather than at the router.
- Do not leave a permissive choice without its consequence named, such as a
  mixed TLS and signing identity that splits audit attribution.
- Turn the page's general warnings back on the system it describes. If it warns
  against a shared hot key, confirm the described design does not use one.
- Do not leave one mechanism described two ways in two places. Reconcile them,
  because the difference usually hides a failure mode.
- Do not fix one passage and leave a second describing the same mechanism in
  contradiction with it. If both can hold only with something in between, name
  the boundary rather than softening one of the two.
- Do not cross-reference a bucket such as "Design notes". Name the heading, and
  re-check the pointer whenever a remark moves.
- Do not let one remark cover two paths with different consequences. Say which
  path it means, or split it.
- Do not restate a figure without checking it can be true as written, and never
  invent the measurement that is missing. Say what the claim rests on instead.
- Do not leave a body sentence that a remark contradicts reading as settled fact.
  A reader who skips the blockquotes must still be told the page marks known
  weaknesses, so the convention is declared where the reader meets it, on the
  page as well as in the site's own guide.
- Do not let the body confess a shortcut that contradicts the design principle.
  The body is the design, the remark is the target, and a workaround adopted for
  the environment is not the design just because it is what runs.
- Do not write a remark as a defect report about the build. State what the correct
  design does, and mention the current state only as the delta.
- Do not lead with the delta. Where the rule and the implementation differ, the
  rule is the rule, and the implementation is the exception to it, named as one.
- Do not let a remark open by re-describing the behaviour above it. Cut that
  clause, because the remark is the prescription and the note is the behaviour.
- Do not tell the reader to pass "one", "the field", or "an explicit value". Name
  the parameter and the shape it takes.
- Do not list values in prose and leave the reader to map them to a payload. Give
  the wire values, and include the members the prose forgets.
- Do not leave a guard's lifetime unexamined. A guard that is a row in a queue
  ends when the queue drains, so compare that lifetime with the caller's retry
  window before calling the operation idempotent.
- Do not assume an operation that walks a partition also covers it. Check whether
  one partition can satisfy the whole amount, and what the caller sees when none
  can, because a walk that requires a single holder caps the request size.
- Do not accept a recovery formula that subtracts a pending set. Ask whether any
  member of that set is already reflected in the value it is subtracted from, and
  name the crash window between the external effect and the local mark.
- Do not document a silent fallback as a quirk. A request that lands on a system
  other than the one asked for is a defect with a target, not a note.
- Do not let a default carry economic meaning. A rate, a fee, or a price that
  defaults is a value the caller picks by leaving a field empty.
- Do not treat a remark as a fix. A defect on a path that moves value is reported
  to the author as a code item as well as stated as a target.

## Verification

1. Every finding in the report maps to a code location you actually read, or is
   labelled unverifiable with the reason.
2. Each adopted change sits in the bucket the conventions require: behaviour in a
   design note, requirement in a production remark, enforcement in the blocker
   list, with no duplication between them.
3. No remark restates its note, no lead-in is orphaned, and no note contradicts a
   remark about the same key, path, or host.
4. The blocker list is severity-ordered and includes every item that is
   enforcement on a path that moves value, and nothing that is a declared scope
   choice.
5. Unverifiable claims are either removed from the article or rewritten so the
   article no longer depends on them.
6. Checks pass: all links resolve, no em dashes or curly quotes, the note and
   remark counts match the intended structure, and the export is regenerated and
   spot-read where markup changed.
7. The article still passes the reader-actionability test: a reader with no
   source access can act on every paragraph, and anything about this repo, its
   incidents, or its defects is reframed as guidance or a production remark.
8. Each remark sits beside the passage that states the behaviour it qualifies,
   and the group holds only remarks with no such passage.
9. No requirement is carried twice, once in the prose and once in a remark.
10. Every claim of generality is qualified where it meets a figure or a fact that
    belongs to one deployment.
11. Every passage that describes a mechanism an amendment touched still agrees
    with it, and any boundary between them is named.
12. Every cross-reference names a heading that exists, and no pointer refers to a
    bucket rather than a heading.
13. Every restated figure can be true as written and names the condition it
    varies with, and any claim without evidence says what it rests on.
14. A reader who skips the blockquotes is not misled: the page declares that the
    body describes the platform while a remark states the production requirement,
    and no body sentence reads as settled where a remark contradicts it.
15. The body reads as a design a reader could copy, and no body sentence presents
    an environment shortcut as if it were the design; each remark states the
    target rather than reporting the build's current state.
16. Every rule the page states comes before any deviation from it, and the
    deviation is labelled as one rather than stated as the rule.
17. Every enumerated list gives the values the system reports and includes the
    reachable members, not only the common ones.
18. No remark restates the behaviour above it, and every parameter a reader is
    told to pass is named.
