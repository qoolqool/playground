# Docker Playground

A containerized development environment for vibe coding with AI agents, supporting both cloud and local models.

## Quick Start

> ⚠️ **Important Git Setup**
> This repository uses submodules. Clone and initialize submodules first:
> ```bash
> git clone <repo-url>
> git submodule update --init --recursive
> ```

```bash
./start.sh           # First run: build and enter container
./start.sh           # Subsequent runs: attach to existing container
./start.sh -f        # Force rebuild
```

## Dynamic Configuration

`setenv.sh` auto-detects whether you're running **Docker** or **Podman** and sets the correct environment variables (`DOCKER_HOST`, socket path) used by `docker-compose.yml`. It is sourced automatically by `start.sh`.

- **Docker (Linux):** Uses `unix:///var/run/docker.sock` — no setup needed.
- **Podman (macOS):** Uses `tcp://<VM_IP>:2375`. Set `PODMAN_VM_IP` before running:

  ```bash
  export PODMAN_VM_IP=192.168.127.2   # or your Podman VM's IP
  ./start.sh
  ```

  You can also add the export to your shell profile (`~/.zshrc`, `~/.bashrc`) so it's always available.

> **Podman on macOS?** You'll need a running Podman VM in rootful mode with the REST API exposed on TCP port 2375. See [`setenv.sh`](setenv.sh) for the logic, or check the [Podman docs](https://podman.io/docs) for VM setup.

## Pi Coding Agent

The container comes with [pi](https://pi.dev), a terminal-native coding agent, pre-installed
along with extensions for persistent memory and knowledge management:

| Feature | What it does | How to use |
|---------|-------------|------------|
| **Persistent Memory** | Remembers facts, preferences, and corrections across sessions | `memory_search`, auto-learns from corrections |
| **Session Search** | Full-text search across all past conversations | `session_search` |
| **Knowledge Graph** | Structural knowledge graph from code, docs, decisions, patterns — entities, relationships, communities | `/graphify .` then `/graphify query`, `/graphify explain`, `/graphify path` |
| **Atlassian Integration** | Search Confluence and Jira from the terminal | `atlassian-cli.py configure` then `confluence search` |
| **Skills** | Reusable workflows for the agent (debugging, code review, planning) | Auto-discovered from `tooling/skills/` |

### Proactive Knowledge Search

The agent is configured (via `.pi/AGENT.md`) to **always search the knowledgebase before starting work**. This prevents re-solving previously solved problems:

- **Conversational/semantic queries** → `/search-kb` — finds decisions, patterns, and gotchas by semantic similarity (preferred, works well with small LLMs)
- **Structural queries** → `/graphify query`, `/graphify explain`, `/graphify path` — finds relationships, communities, and cross-cutting connections (optional, heavier on context)

**Vector DB (`search-kb`) is the preferred search method.** It provides fast, deterministic, ranked results via cosine similarity over pre-computed embeddings. No large graph context needed — small LLMs process the output efficiently. Graphify is retained as an optional structural tool for capable models.

### Quick Setup

```bash
# Build a knowledge graph of the project (recommended — graphify is pre-installed)
/graphify .
```

After `/graphify .`, you can query the graph at any time:

```
/graphify query "what connects Docker to the embedding pipeline"
/graphify explain "bge-large Embedding Model"
/graphify path "Lean Container" "Knowledge Pipeline"
```

## Dual Model Support

The playground supports two model sources:

| Mode | Command | Use case |
|------|---------|----------|
| **Cloud** | `ollama launch pi --model <model>:cloud` | Ollama cloud models via browser auth |
| **Local** | `pi-local <model>` | Local models on host GPU (e.g., gemma4, qwen) |

- **Cloud models** use the container's Ollama server. No API key needed — ollama prompts for browser-based authentication on first run.
- **Local models** run on the host machine's GPU. The container connects to the host's Ollama via `host.docker.internal:11434`. The host IP is auto-detected at startup and available as `$HOST_IP`. Use the `pi-local` helper:

```bash
pi-local gemma4:e4b          # Launch pi with a local model
pi-local qwen3:14b           # Any model on your host's Ollama

# Or manually:
OLLAMA_HOST=$HOST_IP:11434 ollama launch pi --model <model>
```

## Multi-Project Workflow

Each project gets its own playground — an isolated container with its own `/project` workspace.

### Creating a new project

```bash
# Clone the repo for each project
git clone <repo-url> my-new-project
cd my-new-project

# Build and enter
./start.sh
```

`start.sh` handles naming automatically — if a `tooling` container already exists (from another project), it assigns `tooling-2`, `tooling-3`, and so on. Each project runs in its own container with its own workspace.

### What stays per-project

- Working directory (`/project`) is volume-mounted — files persist on the host
- Git config, editor settings, and installed plugins live inside the container
- pi sessions are container-scoped

### What's shared

- The Docker **image** is built once and reused across projects
- Host Ollama serves local models to all containers simultaneously

### Cleaning up

```bash
# Inside the container, type 'exit' to leave

# On the host — stop and remove the container
docker stop tooling && docker rm tooling

# Remove the Docker image (forced rebuild next time)
docker rmi $(docker images -q baseline-tooling)
```

## Architecture

```
┌─────────────────────────────────┐
│  Tooling Container              │
│  ┌───────────────────────────┐  │
│  │ Ollama (container)        │  │  Cloud model broker
│  │ localhost:11434           │  │  `ollama launch pi`
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ Ollama CLI ──────────────────┼──► host.docker.internal:11434
│  │ pi-local → OLLAMA_HOST    │  │  Host GPU models
│  └───────────────────────────┘  │
│                                 │
│  Neovim · Docker · pi           │
│  Starship · Git                 │
│  Graphify · distill-and-index   │
└─────────────────────────────────┘
         │ Docker socket mount
         ▼
   Host Docker daemon
```

## Docker Cheat Sheet

Common commands for working with this playground.

### Container lifecycle

```bash
# See running containers
docker ps

# See all containers (including stopped)
docker ps -a

# Start a stopped container
docker start tooling

# Stop a running container gracefully
docker stop tooling

# Remove a stopped container
docker rm tooling

# Force-remove a running container
docker rm -f tooling
```

### Images

```bash
# List images
docker images

# Remove an image
docker rmi baseline-tooling

# Rebuild from scratch (no cache)
docker compose build --no-cache
```

### Logs and debugging

```bash
# Follow container logs
docker compose logs -f

# View last 50 lines
docker compose logs --tail 50

# Open a shell inside a running container
docker exec -it tooling bash

# Run a one-off command inside the container
docker exec tooling ollama list    # list cloud models (container's Ollama)
```

### Volumes and cleanup

```bash
# Show Docker disk usage
docker system df

# Remove all stopped containers, unused networks, dangling images
docker system prune

# Nuclear option — remove everything (containers, images, volumes)
docker system prune -a
```

## Included Tools

- **Ollama** — Model launcher (cloud + local)
- **Neovim** — Lazy.nvim config with LSP, Telescope, Treesitter, nvim-tree, markdown preview, Mermaid
- **Docker CLI + Compose** — Socket-mounted from host
- **Starship** — Custom prompt
- **Pi** — AI coding agent with memory + session search + skill system
- **Graphify** — Knowledge graph builder and query engine (pre-installed)
- **Node.js / npm, Python, Chromium** — Runtime support

## Atlassian Integration

Search Confluence and Jira from the terminal via the pre-installed `atlassian-cli.py`.

### Setup

```bash
python3 /project/tooling/scripts/atlassian-cli.py configure
```

Prompts for Jira/Confluence URL, email, and API token. Credentials stored at `~/.secrets/mcp-atlassian.json` (chmod 600, not persisted across rebuilds).

Create an API token at https://id.atlassian.com/manage-profile/security/api-tokens.

### Usage

```bash
# Confluence — search with CQL
python3 /project/tooling/scripts/atlassian-cli.py confluence search 'text~"keyword" AND space=TEAM'
python3 /project/tooling/scripts/atlassian-cli.py confluence get <PAGE_ID>

# Jira — search with JQL
python3 /project/tooling/scripts/atlassian-cli.py jira search "project=PROJ AND status!=Done"
python3 /project/tooling/scripts/atlassian-cli.py jira get PROJ-123
python3 /project/tooling/scripts/atlassian-cli.py jira create PROJ "Summary" "Description"
```

### Search syntax

| System | Syntax | Example |
|--------|--------|--------|
| **CQL** (Confluence) | `text~"keyword"` | `text~"onboarding" AND space=TEAM` |
| **JQL** (Jira) | `field = value` | `project=PROJ AND status!=Done` |

> Free-text queries fail in CQL — always use operators like `text~`, `space=`, `type=`.

## Keybinds

See [Keybinds](doc/keybinds.md) for Neovim keymaps.

## Knowledge Tools

| Tool | Purpose | Search Method | Dependencies |
|------|---------|---------------|-------------|
| **search-kb** ✅ | Semantic vector search — cosine similarity over embeddings | `/search-kb "query"` | Ollama + bge-large (~670MB) |
| **graphify** 🔄 | Structural knowledge graph — entities, relationships, communities, paths | `/graphify query`, `/graphify explain`, `/graphify path` | None (self-contained JSON) |
| **distill-and-index** | Distill conversation → knowledgebase YAML → index | Automatic via `/distill-and-index` | Vector DB (preferred) or graphify |

**Vector DB (`search-kb`) is the preferred search backend.** It provides fast, ranked, fuzzy matching that small LLMs can consume efficiently. Graphify offers relationship traversal and community detection, but requires more model capacity; it is available as a structural fallback when installed.

**When to use each:**
- `/search-kb "X"` — "find documents semantically similar to X" (default, lightweight)
- `/graphify query "X"` — "how does X connect to Y?" "what communities overlap?" (optional, heavier)
- `/graphify explain "X"` — "tell me everything about X and what surrounds it"
- `/graphify path "A" "B"` — "trace the shortest connection from A to B"

### Embedding Model (Vector DB)

The preferred vector DB uses **`bge-large:latest`** (1024-dimensional vectors) via Ollama for embeddings. This model is pulled **unconditionally at container startup** — the `entrypoint-wrapper.sh` ensures it is available. Do **not** use `bge-small` (384-dim) — dimension mismatch corrupts the vector index.

> **Graphify fallback:** If graphify is installed and you explicitly want structural queries, no embedding model is needed. Graphify is self-contained.

### distill-and-index on Pi

On Pi, the `distill-and-index` skill **skips memory file writing** — `pi-hermes-memory` handles that. It only writes knowledgebase YAML files and indexes them via the vector DB (preferred) or graphify. This avoids duplicate/conflicting memory entries.

## Rebuilding

After changing `tooling/Dockerfile` or configs under `tooling/`:

```bash
./start.sh -f
```

## Project Structure

```
.
├── start.sh                 # Container lifecycle script
├── setenv.sh                # Dynamic env config (Docker vs Podman)
├── docker-compose.yml       # Container definition
├── doc/                     # Public documentation
│   └── keybinds.md          # Neovim keybind reference
└── tooling/
    ├── Dockerfile           # Image build (debian/ollama base)
    ├── entrypoint-wrapper.sh # First-run setup (nvim plugins, conditional bge-large pull)
    ├── config/              # Dotfiles (bashrc, nvim, starship, git)
    ├── scripts/             # Utility scripts (atlassian-cli, embed-server, vector search)
    ├── skill-marketplace/   # Bundled pi skills (distill-rag-bridge)
    └── skills/              # pi skills (atlassian, coo-advisor, etc.)
```

> **Runtime directories** (created locally, gitignored): `graphify-out/`, `knowledgebase/`, `docs/`, `apps/`, `memory/`, `.pi/`.

## Documentation

- [keybinds.md](doc/keybinds.md) — Neovim keybind reference
