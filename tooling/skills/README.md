# Skills

This directory contains pi skills — reusable workflows that define how the
coding agent should behave for specific tasks.

## Structure

Each skill is a subdirectory containing at minimum a `SKILL.md` file:

```
tooling/skills/<skill-name>/
├── SKILL.md          # Required — metadata + agent instructions
├── install.sh        # Optional — post-install setup script (auto-run)
├── templates/        # Optional — template files for the skill
├── examples/         # Optional — example usage files
└── ...               # Any other supporting files
```

### SKILL.md Frontmatter

```yaml
---
name: <skill-name>
description: One-line what this skill does
---
```

The `name` field in frontmatter should match the directory name.

### install.sh (post-install hook)

If present, `install.sh` is run automatically after a skill is installed
via `install-skill.sh`. It can be used to install dependencies, set up
symlinks, or perform any one-time setup. Example:

```bash
#!/usr/bin/env bash
# install.sh for my-skill
pip install --break-system-packages some-dependency
```

## Installing Community Skills

```bash
./tooling/scripts/install-skill.sh https://github.com/user/my-awesome-skill
```

This will:
1. Clone the repository (`--depth 1`)
2. Validate it contains a `SKILL.md`
3. Copy it to `tooling/skills/<name>/`
4. Run `install.sh` if present
5. Symlink into `.pi/skills/` for immediate availability

### Installing from a Local Directory

```bash
./tooling/scripts/install-skill.sh ./path/to/skill-dir
```

## Creating a New Skill

1. Create a directory: `tooling/skills/my-skill/`
2. Write `SKILL.md`:
   ```yaml
   ---
   name: my-skill
   description: What this skill does
   ---
   # Instructions for the agent...
   ```
3. Optionally add `install.sh` for setup steps
4. Optionally add `templates/` and `examples/`
5. Restart the container or re-run entrypoint-wrapper to register it

> Skills under `tooling/skills/` survive image rebuilds because the
> directory is volume-mounted from the host (`- ./:/project`).

## Auto-Discovery

On every container start, `entrypoint-wrapper.sh` automatically scans
`tooling/skills/` and creates symlinks into `.pi/skills/` for all skill
directories. Skills installed via `install-skill.sh` are symlinked
immediately and don't require a restart.

## Bundled Skills

Some skills are bundled via the `skill-marketplace` git submodule
(`tooling/skill-marketplace/`). These are symlinked into `tooling/skills/`
at container start by `entrypoint-wrapper.sh`.
