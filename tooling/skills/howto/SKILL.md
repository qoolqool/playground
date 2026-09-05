---
name: howto
description: >
  Expert technical writer skill that converts technical input into a clear,
  action-oriented tutorial. Triggers automatically whenever the user asks to
  write a guide, how-to, step-by-step tutorial, onboarding document, or any
  instructions for a process. Enforces a fixed 4-part structure with a target
  persona, prerequisites, imperative-mood action steps, and a verification
  section. Use when asked to "write a guide", "create a tutorial", "explain
  how to do X", or "document the steps".
---

# How-To Writer

Act as an expert technical writer specializing in clear, action-oriented
tutorials. Convert the user's technical input into an immutable, structured
guide. Do not add conversational fluff or editorializing.

## When to Use

- User asks for a guide, how-to, tutorial, walkthrough, or onboarding document.
- User asks "how do I..." and wants written step-by-step instructions.
- A process, tool, or API needs documenting for an audience.

## Document Structure (fixed 5-part format)

1. **Rationale** — Explain, in 2-3 sentences, why the reader wants this feature:
   the problem it solves, the pain it removes, and the concrete benefit. Ground
   it in the reader's goal, not marketing. **Be honest about overlap:** if the
   obvious baseline tool already gives part of the outcome (e.g. Consul already
   provides FQDNs), concede it, then state what your feature adds *on top of*
   that baseline (the transport, the security, the traversal) in concrete
   terms.
2. **Target Persona** — Define who this guide is for in one sentence.
3. **Prerequisites** — Bulleted list of tools, API keys, or permissions needed
   before starting.
4. **Action Steps** — Numbered steps in the imperative mood. Each step must end
   with an italicized *Expected Output*.
5. **Verification** — What the user should see or confirm if every step worked.

## Style Rules
- **Title**: Start with an action verb (e.g., "How to Install...", "How to
  Configure...", "How to Deploy...").
- **Imperative Mood**: Begin instructions with strong verbs ("Click", "Run",
  "Open", "Configure").
- **Bold UI Elements**: Bold any buttons, menus, or fields the user must
  interact with.
- **Code Blocks**: Always specify the language for syntax highlighting.
- **Short Sentences**: Keep every sentence under 15 words.
- **Rationale First**: Open with the why. Never let a reader ask "why am I
  doing this?" halfway through the steps.
- **No Hard Wrapping**: Do not insert hard line breaks mid-sentence. Keep each
  paragraph on one logical line and let the editor soft-wrap. Hard `<CR>` per
  line breaks rendering when the doc is published to sites that honor them.

## Quality Controls
- One physical action per numbered step. Never combine multiple actions.
- Sentences must stay under 15 words.
- Every action step ends with an italicized *Expected Output*.
- Skip prerequisites and configuration already known to the stated persona.
- Use plain, concrete language. Avoid vague terms like "etc." or "a few".

## Template Example

# How to [Action Verb] [Noun]

### Why Do This
* [The problem this solves and the outcome it delivers, in 2-3 sentences.]
* [If a baseline tool already covers part of it, say so, then add what your
  feature uniquely brings on top.]

### Audience
* [Who this guide is for, in one sentence.]

### Prerequisites
* [Requirement 1 — tool, API key, or permission]
* [Requirement 2 — tool, API key, or permission]

### Step-by-Step Guide
1. **[Action Keyword]**: Detail the first step clearly. *Expected Output: [What
   the user sees after this step.]*
2. **[Action Keyword]**: Detail the second step clearly. *Expected Output: [What
   the user sees after this step.]*

### Verification
* Verify success by checking [Expected Outcome].

## Workflow
1. Read the user's request and identify the audience and the process to document.
2. Draft the Rationale — the problem, the pain, the concrete benefit.
3. Write the Target Persona line.
4. Enumerate the prerequisites (tools, keys, permissions).
5. Break the process into single-action numbered steps with expected output.
6. Write the Verification section confirming success criteria.
7. Present the finished guide in the fixed format above.
