# Knowledge Pipeline

Two complementary skills manage the knowledge lifecycle in the playground:
**distill-and-index** (write) and **search-kb** (read).

## Architecture

```
Playground Container
│
├── Write Path
│   distill-and-index skill
│   → knowledgebase/*.yaml
│   → load-kb-to-memory.py (vector DB: agentdb.sqlite3)
│   → kb submit (central-kb)
│
├── Read Path
│   search-kb skill
│   → search-kb-memory.py (local vector DB)
│   → kb search/explain (central-kb)
│   → Agent synthesizes narrative
│
└── Embedding Sources (priority order)
    1. Central KB embed-server HTTP    ~100ms  (BAAI/bge-large-en-v1.5, 1024-dim)
    2. Ollama bge-large:latest          ~330ms  (fallback, auto-pulls if needed)
```

## Tools

| Tool | Purpose | Scope | Embeddings needed |
|------|---------|-------|-------------------|
| **search-kb** | Unified search across all backends | Local + shared | Only for local vector DB queries |
| **kb** | Submit, pull, search, explain, drift | Shared (central-kb) | For submit only (search is server-side) |
| **distill-and-index** | Distill conversation → knowledgebase → index | Both | Yes (sidecar or Ollama) |

## Proactive Knowledge Search

The agent is configured to **always search the knowledgebase before starting
work**. The `search-kb` skill automatically detects available backends:

| Tier | Scope | Command | Embeddings needed |
|------|-------|---------|-------------------|
| **Vector DB** | Local (this project) | `search-kb-memory.py "<query>"` | Yes (client-side) |
| **Central KB** | Shared (cross-project) | `kb search "<query>" --scope <project>` | No (server-side) |

## Embedding Details

- **Model:** `BAAI/bge-large-en-v1.5` (1024-dim) everywhere
- All sources produce compatible 1024-dim vectors (bge-large family)
- Fallback order: Central KB HTTP sidecar (~100ms) → Ollama (~330ms)
- No local sentence-transformers or embed-server daemon needed in the tooling container
- The Central KB sidecar handles embeddings; Ollama is a fallback only

### Embedding Cache

The pipeline includes an intelligent embedding cache. On first run, all entries
are embedded (showing progress per file). On subsequent runs, cached entries
skip embedding entirely — up to 19× faster.

## Gotchas

- **Never mix embedding dimensions.** Using `nomic-embed-text` (768-dim)
  against `bge-large` (1024-dim) entries corrupts the index.
- **All layers must use the same model.** bge-large across local vector DB,
  Central KB submit, and Central KB search ensures vector compatibility.
- Embedding cache uses a **separate** SQLite DB (`embed_cache.sqlite3`)
  to avoid connection contention with `agentdb.sqlite3`.
- Concurrent `CREATE TABLE` from two connections causes `database is locked`
  even in WAL mode — always use separate DB files for independent concerns.
- `kb submit` skips Ollama model download if the Central KB HTTP sidecar
  is reachable. Only falls back to `ollama pull bge-large:latest` if the
  sidecar is down.