# Containerize AI Assist Playground

A containerized development environment for vibe coding with AI agents,
supporting both cloud and local models. Knowledge is persisted as
**OKF v0.1** markdown files and indexed for search across sessions.

## Quick Start

> ⚠️ **Important:** this repo uses submodules. Clone and init first:
> ```bash
> git clone <repo-url> && cd <repo>
> git submodule update --init --recursive
> ```

```bash
./bootstrap.sh           # First run: build and enter container
./bootstrap.sh -p        # Pull prebuilt image from GHCR (skips local build)
./bootstrap.sh -k        # Start central-kb, then build and enter container
./bootstrap.sh           # Subsequent runs: attach to existing container
./bootstrap.sh -f        # Force rebuild (after Dockerfile/tooling changes)
./bootstrap.sh -q        # Check prerequisites before building
./bootstrap.sh --project <name>  # Mount a project directory as /workspace
./bootstrap.sh --stop            # Stop the container
```

> **Note:** `./bootstrap.sh -k` must be run from the **host OS**, not inside the
> tooling container. When run inside another container, the port bindings
> (9000/9001) are only reachable within that container's Docker network.
> On the host OS, Podman/Docker forwards the ports to `localhost`.

For **Podman on macOS**, see [Podman Setup](doc/podman.md).

## Project Mounting

Use `--project <name>` to mount a project directory as `/workspace` inside the
container, scoping the knowledgebase to that project.

### Setup

Add your projects to [`projects.yml`](projects.yml):

```yaml
projects:
  my-app: ~/lab/my-app
  another: /absolute/path/to/another
```

### Usage

```bash
./bootstrap.sh --project my-app              # Mount + enter
./bootstrap.sh --project my-app -k           # Start Central KB, then mount
./bootstrap.sh --project my-app -p           # Pull prebuilt image, then mount
./bootstrap.sh --project my-app -f           # Force rebuild and mount
./bootstrap.sh --project another -f          # Switch project (recreate required)
```

### How it works

| Scenario | `/workspace` mount | `/project` mount | `CENTRAL_KB_PROJECT` |
|----------|-------------------|-----------------|---------------------|
| `--project <name>` | Project dir → `rw` | Playground root → `rw` | Set to project name |
| No `--project` | Playground root → **`ro`** | Playground root → `rw` | Not set |

When `--project` is used, the project directory and playground root are different
paths, so both mounts are read-write. Without `--project`, both mounts point to
the same directory — `/workspace` is set to **read-only** to avoid dual writable
mounts of the same filesystem.

### Inside the container

When started with `--project my-app`, the container has:
- `/workspace` → `~/lab/my-app` (your project code)
- `/project` → playground root (tooling, scripts, docs)
- `$CENTRAL_KB_PROJECT` = `my-app` (kb CLI auto-scopes to this project)

## Stopping the Container

```bash
./bootstrap.sh --stop              # Stop the playground container
./bootstrap.sh --stop -k           # Stop container + central-kb services
```

The `--stop` flag stops the running playground container. With `-k`/`--setup-central-kb`,
it also stops the central-kb embed-server and tooling-central services.

## Host-Only Guard

`bootstrap.sh` detects if it's running inside a container and refuses to run.
This prevents accidentally running container lifecycle commands from within
the tooling container itself. To override (for testing):

```bash
PLAYGROUND_ALLOW_INSIDE=true ./bootstrap.sh
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Tooling Container                                   │
│  ┌────────────────────────────────────────────────┐  │
│  │ Knowledge Pipeline (OKF v0.1)                 │  │
│  │  Distill: session → knowledgebase/*.md         │  │
│  │  Index:   load-kb-to-memory.py (vector DB)    │  │
│  │  Submit:  kb submit --project <name>          │  │
│  │  Search:  kb search / search-kb-memory.py     │  │
│  │  Convert: kb convert / migrate-to-okf.py      │  │
│  │  Validate: kb validate <bundle>               │  │
│  ├────────────────────────────────────────────────┤  │
│  │ Ollama (localhost:11434) — local/cloud models  │  │
│  │ pi coding agent · Neovim · Docker CLI · Git    │  │
│  └────────────────────────────────────────────────┘  │
└────────────────────────┬─────────────────────────────┘
                         │
         host.containers.internal
                         │
         ┌───────────────┴──────────────────────────┐
         │  Central KB        (optional)            │
         │  API :9000 · Embed sidecar :9001         │
         │  ├── tooling-central (FastAPI, no ML)    │
         │  └── embed-server (sentence-transformers)│
         │  Cross-project knowledge sharing         │
         │  OKF v0.1 compliant                      │
         └──────────────────────────────────────────┘
```

[Knowledge pipeline details](doc/knowledge-pipeline.md)
[Central KB setup](doc/central-kb.md)

## Dual Model Support

| Mode | Command | Description |
|------|---------|-------------|
| **Cloud** | `ollama launch pi --model <model>:cloud` | Ollama cloud models via browser auth |
| **Local** | `pi-local <model>` | Local models on host GPU |

## Documentation

| Topic | File |
|-------|------|
| Central KB setup & CLI reference | [doc/central-kb.md](doc/central-kb.md) |
| OKF migration guide | [doc/okf-migration.md](doc/okf-migration.md) |
| Knowledge pipeline & search | [doc/knowledge-pipeline.md](doc/knowledge-pipeline.md) |
| Podman on macOS/Windows | [doc/podman.md](doc/podman.md) |
| Model & embedding configuration | [doc/models.md](doc/models.md) |
| Troubleshooting | [doc/troubleshooting.md](doc/troubleshooting.md) |
| Neovim keybinds | [doc/keybinds.md](doc/keybinds.md) |

## Included Tools

- **pi** — AI coding agent with memory + session search + skills
- **Ollama** — Model launcher (cloud + local)
- **Neovim** — Lazy.nvim with LSP, Telescope, Treesitter, Mermaid
- **kb** — Central Knowledge Base CLI (`kb submit|search|convert|validate|pull|drift`)
- **Docker CLI + Compose** — Socket-mounted from host
- **Python 3, Node.js 22, Chromium** — Runtime support
- **embed-server** — Local embedding daemon (bge-large, 1024-dim)
- **OKF v0.1** — Open Knowledge Format (markdown + YAML frontmatter, 5 namespaces)

## Quick Reference

```bash
# Container lifecycle
./bootstrap.sh              # Build + enter (first run) or attach
./bootstrap.sh -f           # Force rebuild
./bootstrap.sh -p           # Pull prebuilt image from GHCR instead of building
./bootstrap.sh -q           # Check prerequisites before building
./bootstrap.sh -k           # Start central-kb, then build + enter (run on host OS)
./bootstrap.sh --project <name>  # Mount a project directory as /workspace
./bootstrap.sh --stop             # Stop the container
# Model selection
ollama launch pi --model <model>:cloud   # Cloud model
pi-local <model>                         # Local model on host GPU

# Knowledge pipeline (OKF v0.1)
kb convert <legacy-dir> <okf-dir>         # Convert legacy YAML to OKF markdown
kb validate <okf-dir>                      # Validate OKF bundle compliance
kb submit --project <name>                 # Push local KB to central (auto-detect)
kb submit --okf-dir <path> --project <p>   # Submit OKF markdown files
kb search "query" --scope <name>           # Search central KB (returns OKF metadata)
kb pull --project <name>                   # Pull entries from central KB
kb drift --project <name>                  # Check for concept drift

# Local vector DB (session search)
python3 /project/tooling/scripts/search-kb-memory.py "<query>"
```

## Project Structure

```
.
├── bootstrap.sh          # Container lifecycle CLI
├── projects.yml          # Project directory mappings (for --project flag)
├── setenv.sh             # Dynamic env config (Docker vs Podman)
.github/               # CI/CD workflows and Dependabot config
├── docker-compose.yml    # Container definition
├── doc/                  # User-facing documentation
├── tooling/
│   ├── Dockerfile        # Image build
│   ├── config/           # Dotfiles (nvim, bash, starship, git)
│   ├── central-kb/       # Central KB server + CLI (FastAPI, OKF v0.1)
│   ├── scripts/          # Utility scripts (embedding, indexing)
│   ├── skills/           # pi skills (auto-discovered)
│   └── skill-marketplace/ # Bundled pi plugins (submodule)
├── scripts/
│   └── migrate-to-okf.py # Legacy YAML → OKF conversion
├── samples/
│   └── okf-bundle/       # Example OKF bundle (decisions, patterns)
├── knowledgebase/        # Local KB entries (OKF .md + legacy .yaml, gitignored)
└── .agent/               # Vector DB, session data (gitignored)
```

---

## CI/CD & Prebuilt Images

The tooling image is automatically built and pushed to **GitHub Container Registry**
when changes are pushed to `main` that affect the Dockerfile, config, scripts, or extensions.

### Using the Prebuilt Image

```bash
./bootstrap.sh -p       # Pull latest image from GHCR instead of building locally
```

On first run, this downloads the image in seconds instead of building for 5-15 minutes.
The image is built for both `linux/amd64` and `linux/arm64` - the correct architecture
is selected automatically via multi-arch manifests.

### Manual Build Trigger

If you need to trigger a build without pushing to `main`:
1. Go to **Actions > Build & Push Tooling Image > Run workflow**
2. Optionally specify a custom tag

### Dependency Scanning

- **Dependabot:** Runs weekly, scanning GitHub Actions workflows and the base Docker image.
  Opens automated PRs for version updates.
- **Trivy:** Runs weekly, scanning the built image for HIGH/CRITICAL vulnerabilities in
  all packages (including inline pip/npm installs). Results appear in the GitHub Security tab.

### Pulling Without Authentication

The image is public - no GHCR login is required for `./bootstrap.sh -p`. If you hit
rate limits (anonymous: 100 pulls/6h per IP), authenticate with:

```bash
docker login ghcr.io
```
