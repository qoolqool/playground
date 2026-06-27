# Agent Instructions

Behavioral rules have been moved to the relevant skill files:

- **Aha Capture** → `distill-and-index` SKILL.md (Phase 0a, mandatory before Phase 1)
- **Pre-Work KB Search** → Handled automatically by the `resume-handoff` extension
  (`agent_end` hook scans for troubleshooting, searches KB gotchas)

The global AGENTS.md was cleared to avoid competing with concrete skill instructions.
