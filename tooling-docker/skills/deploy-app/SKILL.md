---
name: deploy-app
description: Deploy any git repository by cloning it, inspecting its structure locally, and generating containerized deployment artifacts in /project/app.
command: deploy-app
---

## Important: Self-Executing Skill

**There is no script or external handler behind this skill.** There is only this
SKILL.md file. Do NOT call the Skill tool to "run" it — that does nothing.
Instead, read these instructions and carry them out using Bash, Read, and Write.

## Purpose

Clone a git repository and generate Docker deployment artifacts (Dockerfile,
docker-compose.yml, DEPLOY.md) by inspecting the local checkout directly. No
web fetching from GitHub raw URLs, no tool delegation, no guesswork about
branches.

## Execution Logic

### 1. Clone the repository
```
git clone <repo-url> /project/app
```
If `/project/app` already exists and is non-empty, remove it first.

### 2. Discover the runtime and dependencies
Start with these checks, in order. Stop each check as soon as you have an answer.

- **Runtime**: Read `/project/app/package.json` → `engines.node` (Node.js),
  or look for `requirements.txt` / `pyproject.toml` (Python),
  or `go.mod` (Go).
- **Package manager**: In `package.json`, check `packageManager` field
  (e.g. `yarn@4.13.0`). If absent, look for lock files —
  `yarn.lock`, `package-lock.json`, `pnpm-lock.yaml`.
- **External services**: Read `/project/app/.devcontainer/docker-compose.yml`
  if it exists. This is the highest-signal file for discovering required
  services (databases, caches, search engines) and their environment variables.
  Fall back to `/project/app/docker-compose.yml` if no devcontainer exists.
  Extract every image name, env var, port, and volume mount.
- **Build / start commands**: Check the `scripts` block in `package.json`
  for `build`, `dev`, `start`, or `serve`.

### 3. Generate `/project/app/Dockerfile`
- Use a slim base image matching the discovered runtime (e.g. `node:20-slim`).
- Set `WORKDIR /project/app`.
- Multi-stage builds are fine but not required.
- Write **raw Dockerfile content**, not markdown inside markdown.
- Include `EXPOSE <port>` (default 3000 for Node.js, 8080 for Go/Python).
- Set `CMD` to the start command discovered above.

### 4. Generate `/project/app/docker-compose.yml`
- Define an `app` service that builds from `.` (the Dockerfile) and exposes
  the app port.
- Add every external service discovered in step 2, using the exact images and
  env vars found.
- Add `depends_on` between app and its dependencies.
- Add healthchecks on databases (`pg_isready`, `redis-cli ping`).
- Add named volumes for persistent data stores.

### 5. Generate `/project/app/DEPLOY.md`
Cover these sections:
- **Prerequisites**: Docker and Docker Compose installed.
- **Quick start**: `docker compose up -d` then open `http://localhost:<port>`.
- **Environment variables**: Table of every env var and its purpose.
- **Services**: List each service, its image, and its port.
- **Verification**: `docker compose ps`, `docker compose logs app`,
  `curl http://localhost:<port>`.
- **Volumes**: Which paths persist data.

## Output Files
- `/project/app/Dockerfile`
- `/project/app/docker-compose.yml`
- `/project/app/DEPLOY.md`

## Anti-Patterns (Do NOT Do These)

- Do NOT use WebFetch on github.com or raw.githubusercontent.com — it is blocked.
- Do NOT guess the default branch or construct raw GitHub URLs — clone instead.
- Do NOT curl docs sites — they may not resolve (DNS failures).
- Do NOT search `/project/skills/` for deploy-app files — skills live in
  `/home/tool/.claude/skills/deploy-app/`.
- Do NOT call `which deploy-app` — no binary exists.
- Do NOT read session-distillation SKILL.md as a reference — it is a different
  skill for a different purpose.
