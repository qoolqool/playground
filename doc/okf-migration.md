# OKF Migration Guide

This document describes the migration of the Central KB from its proprietary knowledge format to the **Open Knowledge Format (OKF) v0.1**.

## What is OKF?

The [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) is a vendor-neutral, open specification for representing knowledge as plain markdown files with YAML frontmatter. It was introduced by Google Cloud in June 2026 and is designed to be:

- **Human-readable** — open in any editor, renderable on GitHub
- **Agent-parseable** — no SDK required, just standard markdown + YAML
- **Portable** — ship as a tarball, host in git, mount on any filesystem
- **Diffable** — version control friendly, line-by-line diffs

## Format Changes

### Before (Legacy YAML)

```yaml
---
title: FastAPI Stack
description: All services use FastAPI with Pydantic
status: accepted
date: 2026-01-15
category: architecture
topics: [python, fastapi]
context: >
  The team needed a Python web framework...
consequences: >
  All services use the same patterns...
---
Content body...
```

### After (OKF Markdown)

```markdown
---
type: Decision
title: FastAPI as Primary Web Framework
description: All microservices will use FastAPI with Pydantic v2 for request validation and API documentation.
tags: [architecture, python, fastapi]
timestamp: 2026-01-15T10:30:00Z
status: accepted
---

# Context

The team needed a Python web framework...

# Decision

Use **FastAPI** with **Pydantic v2**...

# Consequences

All services use the same patterns...
```

## Directory Structure

### Before
```
knowledgebase/
├── decisions/
│   └── DEC-001-fastapi.yaml
├── patterns/
│   └── health-check.yaml
└── sessions/
    └── session-2026-01-15.yaml
```

### After (OKF)
```
knowledgebase/
├── index.md                    # Root index for progressive disclosure
├── decisions/
│   ├── index.md                # Directory listing
│   └── fastapi-stack.md        # OKF concept document
├── patterns/
│   ├── index.md
│   └── health-check.md
└── sessions/
    ├── index.md
    └── session-2026-01-15.md
```

## Field Mapping

| Legacy Field | OKF Field | Status | Notes |
|-------------|-----------|--------|-------|
| `title` | `title` | Recommended | Direct mapping |
| `description` | `description` | Recommended | Direct mapping |
| `topics` | `tags` | Recommended | Array of strings |
| `date` | `timestamp` | Recommended | Convert to ISO 8601 |
| `category` | `type` | **Required** | Maps to OKF type |
| `status` | `status` | Extra | Preserved as custom field |
| `context` | Body `# Context` | Conventional | Body section |
| `consequences` | Body `# Consequences` | Conventional | Body section |
| `implementation` | Body `# Implementation` | Conventional | Body section |
| `namespace` (folder) | Directory | Structural | `decisions/` → `decisions/` |
| `key` (filename) | Filename | Structural | `.yaml` → `.md` |

## API Changes

### Submit Endpoint

The `/submit` endpoint now accepts an additional `okf_entries` field:

```json
{
  "project": "my-project",
  "source": "local:cli",
  "okf_entries": [
    {
      "markdown": "---\ntype: Decision\ntitle: ...\n---\n\nBody...",
      "namespace": "decisions",
      "key": "my-decision"
    }
  ]
}
```

The server parses the OKF frontmatter, validates it, and stores the full markdown as the entry content. The legacy `entries` field is still supported for backward compatibility.

### Search Results

Search results now include OKF metadata:

```json
{
  "results": [
    {
      "fqn": "my-project:decisions:fastapi-stack",
      "title": "FastAPI as Primary Web Framework",
      "content": "---\ntype: Decision\n...",
      "score": 0.95,
      "okf_type": "Decision",
      "okf_tags": ["architecture", "python", "fastapi"],
      "okf_description": "All microservices will use FastAPI...",
      "okf_timestamp": "2026-01-15T10:30:00Z"
    }
  ]
}
```

## CLI Changes

### New Commands

| Command | Description |
|---------|-------------|
| `kb submit --okf-dir <path>` | Submit OKF markdown files from a directory |
| `kb convert <input> <output>` | Convert legacy YAML entries to OKF format |
| `kb validate <bundle-dir>` | Validate an OKF bundle for spec compliance |
| `kb health` | Check Central KB server health |

### Updated Commands

- `kb submit` — auto-detects OKF directory (`knowledgebase/`) or legacy SQLite
- `kb search` — displays OKF type, tags, and description in results

## Migration Steps

### 1. Convert Existing Entries

```bash
# Preview the migration
python3 /project/scripts/migrate-to-okf.py --dry-run

# Run the migration (converts in-place)
python3 /project/scripts/migrate-to-okf.py
```

### 2. Validate the Bundle

```bash
kb validate /project/knowledgebase
```

### 3. Submit to Central KB

```bash
kb submit --project my-project --okf-dir /project/knowledgebase
```

### 4. Verify Search

```bash
kb search "fastapi" --scope my-project
```

## OKF Conformance

A bundle is OKF v0.1 conformant if:

1. Every non-reserved `.md` file has parseable YAML frontmatter
2. Every frontmatter block has a non-empty `type` field
3. Reserved filenames (`index.md`, `log.md`) follow spec structure

Consumers MUST NOT reject bundles for:
- Missing optional frontmatter fields
- Unknown `type` values
- Unknown additional frontmatter keys
- Broken cross-links
- Missing `index.md` files

## Cross-References

OKF uses standard markdown links for cross-references:

```markdown
See the [FastAPI decision](/decisions/fastapi-stack.md) for details.
```

Links can be:
- **Absolute** (bundle-relative): `/decisions/fastapi-stack.md`
- **Relative**: `./fastapi-stack.md` or `../patterns/health-check.md`

## Embedding

Embeddings are generated from the **markdown body only** (after stripping YAML frontmatter). This ensures that:
- Embeddings capture semantic content, not metadata
- bge-large (1024-dim) compatibility is preserved
- Search quality remains consistent

## Sample Bundle

A sample OKF bundle is available at `/project/samples/okf-bundle/`:

```
samples/okf-bundle/
├── index.md
├── decisions/
│   ├── index.md
│   └── fastapi-stack.md
└── patterns/
    ├── index.md
    ├── health-check.md
    └── docker-compose.md
```

Validate it:
```bash
kb validate /project/samples/okf-bundle
```
