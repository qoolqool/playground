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
    1. embed-server socket            ~40ms
    2. embed-server HTTP (sidecar)    ~100ms
    3. Ollama bge-large               ~330ms
```

## Tools

| Tool | Purpose | Scope | Embeddings needed |
|------|---------|-------|-------------------|
| **search-kb** | Unified search across all backends | Local + shared | Only for local vector DB queries |
| **kb** | Submit, pull, search, explain, drift | Shared (central-kb) | For submit only (search is server-side) |
| **distill-and-index** | Distill conversation → knowledgebase → index | Both | Yes (embed-server or Ollama) |

## Proactive Knowledge Search

The agent is configured to **always search the knowledgebase before starting
work**. The `search-kb` skill automatically detects available backends:

| Tier | Scope | Command | Embeddings needed |
|------|-------|---------|-------------------|
| **Vector DB** | Local (this project) | `search-kb-memory.py "<query>"` | Yes (client-side) |
| **Central KB** | Shared (cross-project) | `kb search "<query>" --scope <project>` | No (server-side) |

## Embedding Details

- **Model:** `bge-large-en-v1.5` (1024-dimensional)
- Sources tried in priority: socket (~40ms) → HTTP (~100ms) → Ollama (~330ms)
- On a fresh clone, the HTTP embed-server sidecar provides embeddings automatically
- No model download required (handled by central-kb embed-server)

### Embedding Cache

The pipeline includes an intelligent embedding cache. On first run, all entries
are embedded (showing progress per file). On subsequent runs, cached entries
skip embedding entirely — up to 19× faster.

## Gotchas

- **Never mix embedding dimensions.** Using `nomic-embed-text` (768-dim)
  against `bge-large` (1024-dim) entries corrupts the index.
- Embedding cache uses a **separate** SQLite DB (`embed_cache.sqlite3`)
  to avoid connection contention with `agentdb.sqlite3`.
- Concurrent `CREATE TABLE` from two connections causes `database is locked`
  even in WAL mode — always use separate DB files for independent concerns.
