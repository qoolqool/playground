# Central KB

The [central-kb](https://github.com/qoolqool/central-kb) server provides
cross-project knowledge sharing, simhash dedup, drift detection, and a
shared embedding sidecar.

> **Optional.** The playground falls back to local Ollama embeddings and
> local SQLite when central-kb is not running.

## Prerequisites

- Docker or Podman (same runtime as the playground)
- No GPU required — the embed-server uses CPU-only PyTorch

## Quick Start (one command)

```bash
# One-time: clone central-kb as a sibling directory
git clone https://github.com/qoolqool/central-kb ../central-kb

# Start central-kb, then build and enter the playground
./start.sh -k
```

The `-k` / `--setup-central-kb` flag:
1. Checks if central-kb is **already running** (ports 9000/9001)
2. Finds central-kb at `tooling/central-kb/` (submodule) or `../central-kb/` (sibling)
3. Starts `embed-server` and `tooling-central` via `docker compose up -d`
4. Waits for both services to become healthy (up to 60s for PyTorch model download)
5. Creates a `.central-kb-ready` marker and proceeds to build/start the playground

## Manual Setup

```bash
cd ../central-kb && docker compose up -d embed-server tooling-central
cd ../playground && ./start.sh   # auto-detects running central-kb
```

## Verify Connectivity

From inside the playground container:

```bash
curl -s http://host.containers.internal:9000/health
curl -s http://host.containers.internal:9001/health
kb search "test" --scope my-project
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `kb submit --project <name>` | Push local KB entries to central |
| `kb pull --project <name>` | Pull project entries from central |
| `kb search "query" --scope <name>` | Hybrid search (cosine + FTS5) |
| `kb explain "query" --scope <name>` | Structured narrative synthesis |
| `kb drift --project <name>` | Show cross-project drift report |
| `kb candidates` | List entries promoted to global |
| `kb promote <id> approve` | Approve a promotion candidate |

Full usage: [central-kb README](https://github.com/qoolqool/central-kb#cli-usage)
