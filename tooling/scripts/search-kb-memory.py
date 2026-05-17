#!/usr/bin/env python3
"""Search the knowledgebase vector database semantically."""
import json
import socket
import sqlite3
import struct
import sys
import urllib.request
from pathlib import Path

DB_PATH = Path("/project/.claude/agentdb.sqlite3")
EMBED_SOCK = "/tmp/embed-server.sock"
OLLAMA = "http://localhost:11434/api/embeddings"
MODEL = "bge-large:latest"

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


def unpack_vector(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def search(query: str, namespace: str | None = None, limit: int = 5):
    db = sqlite3.connect(str(DB_PATH))
    qvec = embed(query)

    where = "WHERE namespace = ?" if namespace else ""
    params = (namespace,) if namespace else ()
    rows = db.execute(f"SELECT key, namespace, content, metadata_json, vector FROM embeddings {where}", params).fetchall()

    scored = []
    for key, ns, content, meta_json, vec_blob in rows:
        vec = unpack_vector(vec_blob)
        score = cosine(qvec, vec)
        scored.append((score, key, ns, content, json.loads(meta_json)))

    scored.sort(key=lambda x: x[0], reverse=True)

    print(f"Search: \"{query}\"")
    if namespace:
        print(f"  Namespace: {namespace}")
    print(f"  Results: {len(scored)} candidates, top {limit}:\n")

    for i, (score, key, ns, content, meta) in enumerate(scored[:limit]):
        title = meta.get("title", key)
        print(f"  {i + 1}. [{ns}] {title}  (score: {score:.4f})")
        print(f"     {content[:120]}...")
        print()

    db.close()


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("query", nargs="+")
    p.add_argument("-n", "--namespace")
    p.add_argument("-l", "--limit", type=int, default=5)
    args = p.parse_args()

    search(" ".join(args.query), args.namespace, args.limit)
