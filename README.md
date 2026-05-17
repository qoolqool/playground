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

The container comes with [pi](https://pi.dev), a terminal-native coding agent, pre-installed along with extensions for persistent memory and knowledge management:

| Feature | What it does | How to use |
|---------|-------------|------------|
| **Persistent Memory** | Remembers facts, preferences, and corrections across sessions | `memory_search`, auto-learns from corrections |
| **Session Search** | Full-text search across all past conversations | `session_search` |
| **Knowledge Search** | Unified search across local + shared knowledge bases | `search-kb` skill |
| **Central KB** | Cross-project knowledge sharing via shared server | `kb submit`, `kb search`, `kb explain` |
| **Atlassian Integration** | Search Confluence and Jira from the terminal | `atlassian-cli.py configure` then `confluence search` |
| **Skills** | Reusable workflows for the agent (debugging, code review, planning) | Auto-discovered from `tooling/skills/` |

### Proactive Knowledge Search

The agent is configured (via `.pi/AGENT.md`) to **always search the knowledgebase before starting work**. This prevents re-solving previously solved problems. The `search-kb` skill automatically detects available backends and searches all of them:

| Tier | Scope | Command | Embeddings needed |
|------|-------|---------|-------------------|
| **Vector DB** | Local (this project) | `search-kb-memory.py "<query>"` | Yes (client-side, for query vector) |
| **Central KB** | Shared (cross-project) | `kb search "<query>" --scope <project>` | No (server generates query vectors) |

**In an agent session**, use `kb explain` without `--llm` — the agent itself synthesizes the narrative from structured results, far better than any local model.

## Knowledge Pipeline

Two complementary skills manage the knowledge lifecycle:

### `distill-and-index` — Write Pipeline

Distills conversation insights into durable knowledge files, then indexes them for search.

| Tier | Scope | Index Method | Embeddings |
|------|-------|-------------|------------|
| **Vector DB** | Local | `load-kb-to-memory.py` (cosine similarity over 1024-dim vectors) | Yes (embed-server or Ollama) |
| **Central KB** | Shared | `kb submit` (pushes to shared server) | Yes (for submit; search uses server-side) |

Embedding sources are tried in priority order:
1. **embed-server socket** (`/tmp/embed-server.sock`) — ~40ms
2. **embed-server HTTP sidecar** (`host.containers.internal:9001`) — ~100ms
3. **Ollama** (`localhost:11434`, `bge-large:latest`) — ~330ms

On a fresh clone with no local model pulled, the HTTP embed-server sidecar provides embeddings automatically — no download required.

### `search-kb` — Read Pipeline

Searches all available backends and synthesizes results into a coherent narrative.

```bash
# Step 1: Local search (if vector DB available)
python3 /project/scripts/search-kb-memory.py "embedding model" -n decisions

# Step 2: Central KB search (if server available)
kb search "embedding model" --scope my-project

# Step 3: Structured explain (agent synthesizes narrative)
kb explain "embedding model" --scope my-project
```

The agent synthesizes findings from all available backends, tracing how decisions evolved, highlighting cross-project insights, and answering the original query with specific entry references.

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
- **Central KB server** shares knowledge across all projects

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
┌──────────────────────────────────────────────────────────┐
│  Tooling Container                                        │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ Knowledge Pipeline                                  │ │
│  │                                                     │ │
│  │  Write:  distill-and-index → knowledgebase/*.yaml  │ │
│  │           → load-kb-to-memory.py → agentdb.sqlite3  │ │
│  │           → kb submit → Central KB server            │ │
│  │                                                     │ │
│  │  Read:   search-kb skill                            │ │
│  │           → search-kb-memory.py   (local results)  │ │
│  │           → kb search/explain     (shared results) │ │
│  │           → agent synthesizes narrative             │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ Ollama            │  │ embed-server sidecar          │  │
│  │ localhost:11434   │  │ host.containers.internal:9001 │  │
│  │ (local models)   │  │ (bge-large, 1024-dim)         │  │
│  └─────────────────┘  └──────────────────────────────┘  │
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ pi-local → OLLAMA_HOST=$HOST_IP:11434               │ │
│  │ Neovim · Docker · Starship · Git                    │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
         │ Docker socket mount
         ▼
   Host Docker daemon         ┌─────────────────────────┐
                               │ Central KB server        │
                               │ host.containers.internal │
                               │ :9000 (API)              │
                               │ :9001 (embed sidecar)    │
                               └─────────────────────────┘
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
- **kb** — Central Knowledge Base CLI (submit, pull, search, explain, drift, candidates, conflicts)
- **embed-server** — Local embedding daemon (bge-large, 1024-dim, ~40ms per vector)
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
|--------|--------|---------|
| **CQL** (Confluence) | `text~"keyword"` | `text~"onboarding" AND space=TEAM` |
| **JQL** (Jira) | `field = value` | `project=PROJ AND status!=Done` |

> Free-text queries fail in CQL — always use operators like `text~`, `space=`, `type=`.

## Keybinds

See [Keybinds](doc/keybinds.md) for Neovim keymaps.

## Knowledge Tools

| Tool | Purpose | Scope | Embeddings needed |
|------|---------|-------|-------------------|
| **search-kb** | Unified search across all backends | Local + shared | Only for local vector DB queries |
| **kb** | Submit, pull, search, explain, drift | Shared (Central KB) | For submit only (search is server-side) |
| **distill-and-index** | Distill conversation → knowledgebase → index | Both | Yes (embed-server or Ollama) |

### Embedding Model

The vector pipeline uses **`bge-large-en-v1.5`** (1024-dimensional vectors). Sources in priority order:

| Priority | Source | Speed | How |
|-----------|--------|-------|-----|
| 1 | embed-server socket | ~40ms | `/tmp/embed-server.sock`, uses `sentence-transformers` |
| 2 | embed-server HTTP sidecar | ~100ms | `host.containers.internal:9001`, Central KB sidecar |
| 3 | Ollama `bge-large:latest` | ~330ms | `localhost:11434/api/embeddings` |

On a fresh clone with no local model pulled, the HTTP embed-server sidecar provides embeddings automatically. No model download required.

> **Never mix embedding dimensions.** Using `nomic-embed-text` (768-dim) against a DB with `bge-large` (1024-dim) entries corrupts the index.

### distill-and-index on Pi

On Pi, the `distill-and-index` skill **skips memory file writing** — `pi-hermes-memory` handles that. It only writes knowledgebase YAML files and indexes them via Vector DB + Central KB. This avoids duplicate/conflicting memory entries.

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
    ├── entrypoint-wrapper.sh # First-run setup
    ├── config/              # Dotfiles (bashrc, nvim, starship, git)
    ├── scripts/             # Utility scripts
    │   ├── atlassian-cli.py # Confluence/Jira search
    │   ├── embed-server.py  # Local embedding daemon
    │   ├── load-kb-to-memory.py   # Index KB → vector DB
    │   └── search-kb-memory.py    # Search vector DB
    ├── skill-marketplace/   # Bundled pi skills (distill-rag-bridge)
    └── skills/              # pi skills (kb, atlassian, etc.)
```

> **Runtime directories** (created locally, gitignored): `knowledgebase/`, `docs/`, `apps/`, `memory/`, `.pi/`.