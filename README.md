# Docker Playground

A containerized development environment for vibe coding with AI agents, supporting both cloud and local models.

## Quick Start

```bash
./start.sh           # First run: build and enter container
./start.sh           # Subsequent runs: attach to existing container
./start.sh -f        # Force rebuild
```

> **Using Podman on macOS?** See [PODMAN.md](PODMAN.md) for setup instructions — you'll need to configure the Podman REST API and set `PODMAN_VM_IP`.

## Dual Model Support

The playground supports two model sources:

| Mode | Command | Use case |
|------|---------|----------|
| **Cloud** | `ollama launch claude --model <model>:cloud` | Anthropic Claude models via browser auth |
| **Local** | `ollama-local run <model>` | Local models on host GPU (e.g., gemma4, qwen) |

- **Cloud models** use the container's Ollama server. No API key needed — Claude Code prompts for browser-based authentication on first run.
- **Local models** run on the host machine's GPU. The container connects to the host's Ollama via `host.docker.internal:11434`. Use `ollama-local` to interact with host models:

```bash
ollama-local list              # List available local models
ollama-local run gemma4:e4b    # Run a local model
ollama-local pull <model>      # Pull a new model to host
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
- Claude Code sessions are container-scoped

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
│  │ localhost:11434           │  │  `ollama launch claude`
│  └───────────────────────────┘  │
│                                  │
│  ┌───────────────────────────┐  │
│  │ Ollama CLI ──────────────────┼──► host.docker.internal:11434
│  │ (ollama-local)            │  │  Host GPU models
│  └───────────────────────────┘  │
│                                  │
│  Neovim · Docker · Claude Code  │
│  Starship · Git                  │
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
docker exec tooling ollama-local list
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
- **Claude Code** — AI coding agent (`claude`)
- **Neovim** — Lazy.nvim config with LSP, Telescope, Treesitter, nvim-tree, markdown preview, Mermaid
- **Docker CLI + Compose** — Socket-mounted from host
- **Starship** — Custom prompt
- **Node.js / npm, Python, Chromium** — Runtime support

## Keybinds

See [SHORTCUTS.md](tooling/config/SHORTCUTS.md) for Neovim keymaps.

## Rebuilding

After changing `tooling/Dockerfile` or configs under `tooling/`:

```bash
./start.sh -f
```

## Project Structure

```
.
├── start.sh                 # Container lifecycle script
├── docker-compose.yml       # Container definition
├── apps/                    # Deployed app targets
├── scripts/                 # Custom scripts
└── tooling/
    ├── Dockerfile           # Image build (alpine/ollama base)
    ├── entrypoint.sh        # First-run setup + health checks
    ├── config/              # Dotfiles (bashrc, nvim, starship, git)
    └── skills/              # Claude Code skills (deploy-app)
```