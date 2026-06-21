# Central KB

The [central-kb](https://github.com/qoolqool/central-kb) server provides
cross-project knowledge sharing, simhash dedup, drift detection, and a
shared embedding sidecar.

All knowledge is stored in the **Open Knowledge Format (OKF) v0.1** —
markdown files with YAML frontmatter. See [OKF Migration](okf-migration.md)
for details.

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
# ⚠️  Must be run from the host OS, not inside the tooling container
./start.sh -k
```

The `-k` / `--setup-central-kb` flag:
1. Checks if central-kb is **already running** (ports 9000/9001)
2. Finds central-kb at `tooling/central-kb/` (submodule) or `../central-kb/` (sibling)
3. Starts `embed-server` and `tooling-central` via `docker compose up -d`
4. Waits for both services to become healthy (up to 60s for PyTorch model download)
5. Creates a `.central-kb-ready` marker and proceeds to build/start the playground

> **Important:** `./start.sh -k` must be run from the **host OS**. When run inside
> the tooling container, Docker/Podman port bindings (9000/9001) only exist in
> that container's network namespace — the host OS cannot reach them. From the
> host OS, the services are accessible at `localhost:9000` and `localhost:9001`.

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
| `kb submit --project <name>` | Push local KB entries to central (auto-detects OKF dir or legacy DB) |
| `kb submit --okf-dir <path>` | Submit OKF markdown files from a directory |
| `kb pull --project <name>` | Pull project entries from central |
| `kb search "query" --scope <name>` | Hybrid search (cosine + FTS5) with OKF metadata |
| `kb explain "query" --scope <name>` | Structured narrative synthesis |
| `kb convert <input> <output>` | Convert legacy YAML entries to OKF format |
| `kb validate <bundle-dir>` | Validate OKF bundle compliance |
| `kb health` | Check Central KB server health |
| `kb drift --project <name>` | Show cross-project drift report |
| `kb candidates` | List entries promoted to global |
| `kb promote <id> approve` | Approve a promotion candidate |

## OKF Submission

The `/submit` endpoint now accepts OKF markdown entries:

```json
{
  "project": "my-project",
  "source": "local:cli",
  "okf_entries": [
    {
      "markdown": "---\ntype: Decision\ntitle: ...\n---\n\nBody..."
    }
  ]
}
```

The server parses the YAML frontmatter, validates the required `type` field,
and stores the full markdown as the entry content. The legacy `entries` field
is still supported for backward compatibility.

Full usage: [central-kb README](https://github.com/qoolqool/central-kb#cli-usage)
