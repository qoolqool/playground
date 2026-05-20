#!/usr/bin/env python3
"""Search the knowledgebase vector database semantically."""
import json
import sqlite3
import sys
from pathlib import Path

from kb_common import embed_cached, unpack_vector, cosine

DB_PATH = Path("/project/.agent/agentdb.sqlite3")

# Ensure .agent/ directory exists before opening any DB connection
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def search(query: str, namespace: str | None = None, limit: int = 5):
    db = sqlite3.connect(str(DB_PATH))
    qvec = embed_cached(query)

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
