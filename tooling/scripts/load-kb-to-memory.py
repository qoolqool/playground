#!/usr/bin/env python3
"""
Load knowledgebase YAML files into a persistent vector database.
Uses Ollama bge-large:latest (1024-dim) for embeddings + SQLite for storage.
No external npm dependencies — uses only Python stdlib + ollama API.
"""
import json
import socket
import sqlite3
import struct
import sys
import urllib.request
from pathlib import Path

KB = Path("/project/knowledgebase")
DB_PATH = Path("/project/.claude/agentdb.sqlite3")
EMBED_SOCK = "/tmp/embed-server.sock"
OLLAMA = "http://localhost:11434/api/embeddings"
MODEL = "bge-large:latest"
VEC_DIM = 1024

# Embed-server HTTP sidecar: auto-detect host (cached on first call)
_EMBED_HTTP_URL = None


def _detect_embed_http_url() -> str | None:
    """Auto-detect the Central KB embed-server HTTP endpoint."""
    for host in ["host.containers.internal", "host.docker.internal"]:
        url = f"http://{host}:9001"
        try:
            req = urllib.request.Request(f"{url}/health", method="GET")
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read())
            if data.get("model_ready"):
                return url
        except Exception:
            continue
    return None


def embed_fast(text: str) -> list[float] | None:
    """Try the local embed daemon (Unix socket) first — ~40ms."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(EMBED_SOCK)
        sock.sendall(text[:512].encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        sock.close()
        result = json.loads(b"".join(chunks))
        if "error" in result:
            return None
        return result["embedding"]
    except Exception:
        return None


def embed_http(text: str) -> list[float] | None:
    """Try the Central KB embed-server HTTP sidecar — ~100ms."""
    global _EMBED_HTTP_URL
    if _EMBED_HTTP_URL is None:
        _EMBED_HTTP_URL = _detect_embed_http_url()
    if not _EMBED_HTTP_URL:
        return None
    try:
        payload = json.dumps({"text": text[:512]}).encode("utf-8")
        req = urllib.request.Request(
            f"{_EMBED_HTTP_URL}/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        if "error" in result:
            return None
        return result["embedding"]
    except Exception:
        return None


def embed_ollama(text: str) -> list[float] | None:
    """Fallback via Ollama HTTP — ~330ms. Returns None if unavailable."""
    data = json.dumps({"model": MODEL, "prompt": text[:256]}).encode()
    req = urllib.request.Request(OLLAMA, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        return result["embedding"]
    except Exception:
        return None


def embed(text: str) -> list[float]:
    """Generate embedding — tries all sources, raises with clear message if all fail."""
    emb = embed_fast(text)
    if emb is not None:
        return emb
    emb = embed_http(text)
    if emb is not None:
        return emb
    emb = embed_ollama(text)
    if emb is not None:
        return emb
    # All sources failed
    print("ERROR: No embedding source available.", file=sys.stderr)
    print("  Tried: 1) embed-server socket (/tmp/embed-server.sock)", file=sys.stderr)
    print("         2) embed-server HTTP (host.containers.internal:9001)", file=sys.stderr)
    print(f"         3) Ollama ({OLLAMA}, model {MODEL})", file=sys.stderr)
    print("  Fix: start embed-server OR run: ollama serve && ollama pull bge-large:latest", file=sys.stderr)
    sys.exit(1)

def pack_vector(vec: list[float]) -> bytes:
    """Pack float list into compact binary for SQLite BLOB."""
    return struct.pack(f"{len(vec)}f", *vec)

def unpack_vector(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob)//4}f", blob))

def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0

def parse_yaml_simple(text: str) -> dict:
    """Parse simple YAML flat keys and block scalars."""
    result = {}
    lines = text.split("\n")
    key = None
    buf = []
    in_block = False

    for line in lines:
        if in_block:
            if line and (line[0:2] == "  " or line.strip() == "" or line.startswith("    ")):
                buf.append(line[2:] if line.startswith("  ") and not line.startswith("    ") else line)
                continue
            else:
                result[key] = "\n".join(buf).strip()
                buf = []
                in_block = False
        m = None
        for sep in [": ", ":"]:
            idx = line.find(sep)
            if idx > 0 and not line.startswith(" "):
                m = (line[:idx], line[idx + len(sep):])
                break
        if m:
            key = m[0]
            val = m[1].strip()
            if val in (">", "|"):
                in_block = True
                buf = []
            elif val:
                result[key] = val
            else:
                result[key] = ""
    if in_block and key:
        result[key] = "\n".join(buf).strip()
    return result

def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            namespace TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}',
            vector BLOB NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(namespace, key)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_ns ON embeddings(namespace)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_key ON embeddings(namespace, key)")
    db.commit()
    return db

def store_all():
    print("[1/3] Initializing SQLite database...")
    db = init_db()

    namespaces = {
        "decisions": "decisions",
        "patterns": "patterns",
        "sessions": "sessions",
    }

    total = 0
    errors = 0

    for folder, ns in namespaces.items():
        dir_path = KB / folder
        files = sorted(dir_path.glob("*.yaml"))
        print(f"  {folder}/: {len(files)} files")

        for fpath in files:
            try:
                text = fpath.read_text()
                parsed = parse_yaml_simple(text)
                entry_key = fpath.stem
                title = parsed.get("title") or parsed.get("name") or parsed.get("id") or entry_key
                desc = parsed.get("description") or parsed.get("summary") or parsed.get("decision") or text[:200]

                metadata = {
                    "title": title,
                    "type": folder,
                    "file": fpath.name,
                    "source": str(fpath.relative_to(KB.parent)),
                }
                for meta_key in ("status", "date", "category", "firstSeen", "lastUpdated"):
                    if meta_key in parsed:
                        metadata[meta_key] = parsed[meta_key]

                content_full = f"{title}\n{desc}"

                # Generate embedding
                vec = embed(content_full)
                vec_blob = pack_vector(vec)

                db.execute(
                    "INSERT OR REPLACE INTO embeddings (key, namespace, content, metadata_json, vector) VALUES (?, ?, ?, ?, ?)",
                    (entry_key, ns, content_full, json.dumps(metadata), vec_blob),
                )
                total += 1
                if total % 20 == 0:
                    print(f"    ... {total} entries stored")
            except Exception as e:
                print(f"    ERROR {fpath.name}: {e}")
                errors += 1

    db.commit()

    print(f"\n[2/3] Stored: {total} entries, {errors} errors")

    # Verify
    count = db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    print(f"[3/3] Database: {count} rows in {DB_PATH} ({DB_PATH.stat().st_size} bytes)")

    db.close()
    return 0 if errors == 0 else 1

if __name__ == "__main__":
    sys.exit(store_all())
