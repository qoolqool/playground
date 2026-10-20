---
name: write-public-prototype-docs
description: >
  Write and maintain anonymous, public-ready documentation for a prototype,
  where the reader has no source and no local deployment. Covers the site
  structure, the page anatomy, the body-versus-remark split, the anonymity and
  style rules, and how to present measurements so they are not read as capacity.
  Use when asked to "write the documentation", "publish the prototype docs",
  "add a module guide", "make this page public-ready", or "check this page
  before release".
---

# Writing Public-Ready Prototype Documentation

Documentation for a prototype that is published to people who cannot read the
source, run the system, or ask you a question. Every page has to be true,
self-contained, and actionable on its own.

## When to Use

Use when starting a public documentation set for a prototype, adding a page or a
module guide to one, promoting an internal note to a public page, or reviewing a
page before release.

Do not use it for internal runbooks that legitimately name hosts, repositories,
or tickets; those are a different genre with a different audience. Do not use it
for prose polish (use `humanizer`) or for vetting an existing article's claims
for correctness (use `review-design-article`).

## The reader, and the two tests

The reader is an integrator, an operator, or an evaluator. They are competent and
sceptical, they cannot inspect the implementation, and they will build a system
against what they read. Two tests settle almost every decision:

1. **Can they act on this?** A reader with no source access must be able to
   configure, call, operate, or judge the thing from the page alone.
2. **Is it true?** A claim that has not been checked against the running system is
   a liability, because the reader cannot check it either.

Content that fails the first test because it is about your own repository, your
incidents, your test suite, or your internal defects does not belong in the body.
Reframe it as guidance or as a requirement, or leave it out.

## Anonymity rules

The set is published, so treat every identifier as public.

- No organisation, product, vendor, customer, or person names.
- No internal hostnames, service names, repository names, pipeline or project
  names, ticket identifiers, or file paths.
- No secrets, credentials, tokens, certificates, keys, or machine-local paths.
- No raw logs, dated dumps, or exported reports. Summarise the durable finding
  instead.
- Replace real identifiers with a reserved example namespace, and say that it is
  reserved so nobody mistakes it for a live one.
- Describe a host or a component by the role it plays, not by the name it has.
- Say which revision a page was written against, and state that the running
  system wins where the two disagree.
- Keep anything that is not part of the public reference out of both indexes.

## Self-containment

The set has to stand alone, because there is nothing else to read.

- Publish the interfaces: the machine contract, the message shapes, the error
  model, and every configuration variable, in the set itself.
- Publish no command a reader could run against your system. Snippets illustrate
  **shape and method only**: a configuration fragment, a JSON body, a SQL
  example, a language fragment, a text diagram. A shell snippet that would work
  is a support burden and an exposure.
- Define an abbreviation at first use, or keep a terminology page and link to it.
- Cross-reference by heading, never by position. "See above" breaks the moment a
  page is edited.

## Site structure

- **One front door.** A page that says what the prototype is, what it does not
  prove, and where each kind of reader should start.
- **Functional sections that mirror how the system is built.** Each opens with a
  short key-points page that gives the sixty-second version before the detail.
- **Reference sections** for facts a reader looks up rather than reads: the
  interface, the configuration, and a map of the modules.
- **Worked examples instead of a tutorial.** A reader who cannot install the
  system cannot follow a hands-on guide, so a walkthrough of one request or one
  flow takes its place.
- **Two indexes.** A human table of contents and a machine-readable list, both
  generated from the same set, both covering every public page.
- **One job per page**, and say which job it is: explanation, how-to, reference,
  or worked example.

## Page anatomy

1. An H1 naming the subject, in sentence case.
2. A short paragraph saying what the page is and who it is for.
3. The body, in sections that each carry one idea.
4. Where the page describes a design, a line that separates the design from what
   a production deployment needs.
5. A closing line of related links.

## The body and the remark

The body carries the design. The remark carries the intended design. Keeping
those two roles separate is what lets a prototype be published honestly without
reading as a defect list.

- **Write the body so the thing could be rebuilt from it.** It describes what the
  system does and why, in the voice of a design.
- **Put the target in a blockquoted production remark**: what a production
  deployment needs instead. Phrase it as the solution, not as a confession.
- **Do not present an environment shortcut as the design.** A workaround adopted
  so the prototype could run is not the design just because it is what runs. If
  it contradicts the design principle, it is a remark about the target, not a
  described behaviour.
- **One home each.** Facts, figures, and mechanism in the body; the requirement in
  the remark. If both carry it, delete one.
- **One remark after a passage stays inline. Two or more share one panel** as
  bullet points. Group only the remarks that qualify nothing in particular.
- **Declare the convention where the reader meets it**: once at site level, and
  on every page that carries a remark, so a reader who skips the blockquotes
  still knows the page marks gaps rather than describing settled design.

## What to say about scope

Keep one page that states, plainly:

- what the prototype demonstrates end to end;
- what it only simulates, in a table of what it does now against what production
  would require;
- the trust anchors that are weaker than they look at first glance, each with the
  condition that should trigger revisiting it;
- how to read a measurement from the set, before the reader meets any number.

State the revisit condition, not just the simplification. A simplification with a
trigger is a decision; without one it is an omission.

## Presenting measurements

- **Mark every figure with the configuration it came from.** An unqualified
  number is a claim about nothing.
- **Never present a development-hardware result as a capacity figure**, and say
  on the page where the numbers came from.
- **Report percentiles, not averages.** An average hides the tail that callers
  experience.
- **Report the bounding stage, not a product of stages.** If two stages are
  decoupled, end-to-end is the slower of them, and multiplying them describes
  nothing.
- **One experiment answers one question.** Say what each run was for.
- **Publish the negative results.** The configurations that changed nothing are
  what turn a table of numbers into an explanation.

## Style

- **No first person.** "The system does", not "we do". The reader has no
  relationship with your team.
- Sentence-case headings, active voice, short sentences.
- No em dashes, no curly quotes.
- Name the concrete thing and state the consequence, rather than inventing
  shorthand the reader has to decode.
- State the unit on every amount and the shape of every identifier.
- Call an identifier opaque when callers must not derive it, and say what is
  guaranteed about it instead.
- Prefer a table when the reader is comparing; prefer prose when they are
  following a reason.

## Pitfalls

- Do not publish a page that assumes a local checkout, an internal tool, or a
  colleague who can be asked.
- Do not let a snippet be runnable. Shape is the point, not execution.
- Do not leave a real name, host, path, or ticket in a diagram, an example, or a
  table column.
- Do not present a shortcut as the design, and do not write a remark as a defect
  report. The body is the design, the remark is the target.
- Do not let the body and a remark both carry the same requirement.
- Do not state a figure without the configuration behind it, and never imply a
  measurement that was not taken. Say what the claim rests on.
- Do not let a cross-reference name a container such as "the notes"; name the
  heading, because content moves.
- Do not publish a page that is absent from the indexes, or an index entry with no
  page.
- Do not describe an interface from memory. Verify every name, shape, and default
  against the system, and let the system win.

## Verification

1. A reader with no source access can act on every paragraph, or the paragraph is
   reframed as guidance or a requirement.
2. No organisation, host, path, repository, ticket, person, or secret appears
   anywhere in the set, including examples, diagrams, and tables.
3. No snippet is runnable against the system.
4. Every page appears in both indexes, and both indexes resolve.
5. Every figure names its configuration, and no development-hardware figure is
   presented as capacity.
6. The scope page states what is demonstrated, what is simulated, and the trigger
   for revisiting each simplification.
7. Every page that carries a remark declares the convention, and no remark
   restates its own body text.
8. No cross-reference names a container rather than a heading, and every link
   resolves.
9. Style holds across the set: no first person, no em dashes or curly quotes,
   sentence-case headings, a unit on every amount.
