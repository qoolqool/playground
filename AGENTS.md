# Agent Instructions

Working rules for agents in this repo. The repo is mounted at `/project` and the
agent runs inside the tooling image built from `tooling/Dockerfile`.

## Stay in scope

- Work inside `/project`. Do not read other checkouts on the host unless the user
  names them in this session.
- Take committed facts from the repo in front of you, not from memory of another
  project.

## Never touch the tooling container

- NEVER reboot, restart, stop, remove, recreate, or prune `playground-tooling`
  (the `tooling` compose service). It hosts local orchestration state and a
  testbed, and a restart wipes both. That rules out `docker restart`,
  `docker stop`, `docker rm`, `docker compose down`, and any prune or cleanup
  that could reach it. Treat it as untouchable and read-only.
- Do not restart the Docker/podman machine itself without explicit permission.
- If a change needs the container recreated, edit the files, then say which
  container has to be recreated and why, and let the user do it.

## Git

- Never push or force-push without explicit consent. Local commits are fine.
- Run `git branch --show-current` immediately before every `git commit`. If it
  shows the trunk branch (`main` or `master`), create or switch to a feature
  branch first: the checkout can move to trunk on its own between commands, so
  checking once at the start of a session is not enough.
- When a feature branch shows "no diff vs trunk", it was most likely already
  merged and trunk now contains its commits. Check the reflog before concluding
  that work was lost.
- Before modifying tracked files, run `git fetch origin` and check the branch is
  not behind trunk. If trunk has moved, rebase onto it and re-apply only your
  delta.
- After any change worth committing, suggest a one-line imperative commit
  message (for example `install pi in tooling image via pinned managed
  installer`) so the user can commit without drafting one.

## Infrastructure commands

- Orchestration and infrastructure CLIs: use read-only subcommands only, such as
  `status`, `inspect`, `logs`, `fs` in read-only mode, `members`, and `version`.
- If a command might mutate state and you are not certain it is read-only, ask
  the user before running it.

## Runbooks

- When a symptom matches a runbook or procedure under `docs/`, follow it instead
  of improvising a sequence of commands.

## Where files belong

- The repo is the committed source of truth.
- Dev and runtime artifacts (compose overrides, local job specs, generated
  configs, tool output) do not belong in git; keep them in a dev workspace
  outside the repo, for example `/workspace/dev`.
- A container that talks to the host daemon needs the daemon-visible host path,
  not a container-local one.
- `.pi/` and `knowledgebase/` are gitignored runtime state. Do not force-add
  them.

## Images and deployment

- Do not build, push, or deploy images. The user owns image build and deploy.
- Put the Dockerfile (and any patch files it applies) where it belongs, then say
  what has to be rebuilt.
- A Dockerfile that needs an upstream source change should clone the upstream
  repo and `git apply` a committed `.patch` kept beside the Dockerfile, rather
  than expecting a pre-modified source tree.

## Container resources

- Every container MUST have an explicit memory limit: `mem_limit` in compose,
  `--memory` and `--memory-swap` for `docker create` or `docker run`.
- The host has limited RAM (about 18G) shared with the Docker daemon. One
  uncapped container can balloon until the host OOMs and the daemon hangs.
- Size a limit to the service's real working set, not "give it everything".
- Keep the host lean: prune dangling images and stopped containers
  periodically. A bloated image store slows the daemon and looks like an OOM.
- Restarting a container to apply a limit is fine. The machine is not; see above.

## Container entrypoint hygiene

- Before adding a command to an `ENTRYPOINT` or `entrypoint.sh`, confirm the
  binary is installed in that image (check the Dockerfile's package list). If it
  is not, the container fails at `runc create` with
  `exec: "<bin>": stat <bin>: no such file or directory`.
- Do not add an init or supervisor binary (tini and friends) just to fix
  zombies. Remove the cause instead, such as a health check that spawns
  subprocesses under a PID 1 that does not reap. Orchestrator-side checks run
  outside the container's PID namespace and do not leak processes into it.

## Skills

- Project skills live in `tooling/skills/<name>/SKILL.md`. The entrypoint
  symlinks them into `.pi/skills` at container start, so add them there and never
  into `.pi/` by hand.
- Third-party skills are declared in `tooling/Dockerfile` (via skills.sh or
  `pi install`) instead of being vendored into git.
- Keep a skill generic before committing it: no project-specific hosts, absolute
  home or workspace paths, document names, customer data, or internal URLs.
  Methodology and procedure travel; local values do not.

## Document writing

- When writing any document (guide, how-to, report, onboarding, proposal), apply
  the `humanizer` skill before finalizing. Remove inflated wording, em-dash
  overuse, rule-of-three lists, passive voice, and filler so the text reads
  natural. Do not skip this for anything published or shared.
- When a document contains ASCII or box-drawing diagrams, also apply the
  `humanizer` skill's ASCII Diagram Repair section: align every line in a
  `text`/`ascii` block to equal width, use spaces rather than tabs, keep
  box-drawing glyphs (─ ┌ ┐ └ ┘ ├ ┤ ┼) aligned across rows, and re-check arrow
  alignment after any edit.

## Knowledgebase

- The knowledgebase is `knowledgebase/`, with the existing categories
  `decisions/`, `patterns/`, `sessions/`, `gotchas/`, `facts/`, `concepts/`, and
  `handoffs/`. Write new entries into those.
- Keep one knowledgebase. Do not create a second one elsewhere in the tree, and
  do not use stale copies as if they were current.
