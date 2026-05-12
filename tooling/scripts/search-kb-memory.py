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


def embed_fast(text: str) -> list[float] | None:
    """Try the local embed daemon first — ~40ms."""
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


def embed_ollama(text: str) -> list[float]:
    """Fallback via Ollama HTTP — ~330ms."""
    data = json.dumps({"model": MODEL, "prompt": text[:256]}).encode()
    req = urllib.request.Request(OLLAMA, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["embedding"]


def embed(text: str) -> list[float]:
    emb = embed_fast(text)
    if emb is not None:
        return emb
    return embed_ollama(text)


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
