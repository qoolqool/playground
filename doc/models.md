# Models

The playground supports two model sources for the AI coding agent (pi).
Models for **embeddings** are handled separately via the embed-server.

## Dual Model Support

| Mode | Command | Use case |
|------|---------|----------|
| **Cloud** | `ollama launch pi --model <model>:cloud` | Ollama cloud models via browser auth |
| **Local** | `pi-local <model>` | Local models on host GPU |

### Cloud Models

Uses the container's built-in Ollama server. No API key needed — ollama
prompts for browser-based authentication on first run.

```bash
ollama launch pi --model sonnet:cloud
```

### Local Models

Runs on the host machine's GPU. The container connects to the host's
Ollama via `host.docker.internal:11434`. The host IP is auto-detected
at startup and available as `$HOST_IP`.

```bash
pi-local gemma4:e4b          # Launch pi with a local model
pi-local qwen3:14b           # Any model on your host's Ollama

# Or manually:
OLLAMA_HOST=$HOST_IP:11434 ollama launch pi --model <model>
```

## Embedding Model

The vector pipeline uses **`bge-large-en-v1.5`** (1024-dimensional vectors).
Sources in priority order:

| Priority | Source | Speed | How |
|----------|--------|-------|-----|
| 1 | embed-server socket | ~40ms | `/tmp/embed-server.sock`, uses `sentence-transformers` |
| 2 | embed-server HTTP sidecar | ~100ms | `host.containers.internal:9001`, Central KB sidecar |
| 3 | Ollama `bge-large:latest` | ~330ms | `localhost:11434/api/embeddings` |

> **Never mix embedding dimensions.** Using `nomic-embed-text` (768-dim)
> against a DB with `bge-large` (1024-dim) entries corrupts the index.
