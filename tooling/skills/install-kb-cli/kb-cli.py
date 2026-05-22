#!/usr/bin/env python3
"""
kb — Command-line client for the Central Knowledge Base server.

Works as a standalone CLI — no external package required. Auto-generates
embeddings via Ollama when submitting entries.

Configuration (env vars or flags):
  CENTRAL_KB_URL       Server URL  (default: auto-detected from gateway IP, port 9000)
  CENTRAL_KB_PROJECT   Project name (required for submit/pull/drift)
  KB_EMBED_MODEL       Ollama embedding model (default: bge-large:latest, 1024-dim)

Usage:
  kb submit --project <name>                  # Submit local KB YAML files
  kb submit --project <name> --dir /path      # Submit from custom directory
  kb pull --project <name>                     # Pull entries from server
  kb search "query" --scope <name>              # Semantic + FTS search
  kb drift --project <name>                     # Check for drift
  kb candidates                                  # List promotion candidates
  kb conflicts                                   # List conflicts
  kb conflicts <id> resolve --resolution <text> # Resolve a conflict
  kb health                                      # Check server health
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_host_url() -> str:
    """Auto-detect the Central KB server URL from the container host."""
    port = 9000
    # 1. Try host.containers.internal (Podman) and host.docker.internal (Docker)
    for hostname in ("host.containers.internal", "host.docker.internal"):
        url = f"http://{hostname}:{port}"
        try:
            req = urllib.request.Request(f"{url}/health", method="GET")
            urllib.request.urlopen(req, timeout=3)
            return url
        except Exception:
            continue
    # 2. Try default gateway from routing table
    try:
        import subprocess
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5,
        )
        for part in result.stdout.split():
            if part not in ("default", "via", "dev") and "." in part:
                url = f"http://{part}:{port}"
                try:
                    req = urllib.request.Request(f"{url}/health", method="GET")
                    urllib.request.urlopen(req, timeout=3)
                    return url
                except Exception:
                    continue
    except Exception:
        pass
    # 3. Last resort
    return f"http://localhost:{port}"


def server_url() -> str:
    env_val = os.environ.get("CENTRAL_KB_URL", "").rstrip("/")
    if env_val:
        return env_val
    return detect_host_url()


def project_name() -> str:
    return os.environ.get("CENTRAL_KB_PROJECT", "")


def embed_model() -> str:
    return os.environ.get("KB_EMBED_MODEL", "bge-large:latest")


# Embed-server HTTP sidecar: auto-detect and cache
_EMBED_HTTP_URL = None


def _detect_embed_http_url() -> str | None:
    """Auto-detect the Central KB embed-server HTTP endpoint."""
    for host in ("host.containers.internal", "host.docker.internal"):
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


def _embed_via_http(text: str) -> list[float] | None:
    """Try embed-server HTTP sidecar — ~100ms."""
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


def api(path: str, *, method: str = "GET", body: dict | None = None, timeout: int = 30) -> dict:
    """Call the Central KB API and return parsed JSON."""
    url = f"{server_url()}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8")
        try:
            detail = json.dumps(json.loads(detail), indent=2)
        except Exception:
            pass
        print(f"HTTP {e.code}: {detail}", file=sys.stderr)
        if e.code == 500:
            print("Server error (500) — this is a server-side issue, not a CLI problem.", file=sys.stderr)
            print("Possible causes: mixed vector dimensions in DB, server needs restart.", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        print(f"  Is the server running at {server_url()}?", file=sys.stderr)
        sys.exit(1)


def simhash_64(text: str) -> int:
    """Compute 64-bit simhash, guaranteed to fit in SQLite signed INT64."""
    import hashlib
    features = text.lower().split()
    v = [0] * 64
    for feature in features:
        h = int(hashlib.sha256(feature.encode()).hexdigest(), 16)
        for i in range(64):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    fingerprint = 0
    for i in range(64):
        if v[i] >= 0:
            fingerprint |= (1 << i)
    # Convert to signed int64 for SQLite compatibility
    if fingerprint >= (1 << 63):
        fingerprint -= (1 << 64)
    return fingerprint


def get_embedding(text: str) -> list[float]:
    """Generate embedding vector — tries embed-server HTTP, falls back to Ollama."""
    # 1. Try embed-server HTTP sidecar (~100ms)
    vec = _embed_via_http(text)
    if vec is not None:
        return vec
    # 2. Fallback to Ollama (~330ms)
    model = embed_model()
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:11434/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read())
        return result["embedding"]
    except urllib.error.URLError as e:
        print(f"Embedding error: {e.reason}", file=sys.stderr)
        print(f"  No embed-server HTTP or Ollama available. Tried:", file=sys.stderr)
        print(f"    1. embed-server HTTP sidecar (host.containers.internal:9001) — not reachable", file=sys.stderr)
        print(f"    2. Ollama localhost:11434 — {e.reason}", file=sys.stderr)
        print(f"  Fix: start embed-server OR run: ollama serve && ollama pull {model}", file=sys.stderr)
        sys.exit(1)
    except KeyError:
        print(f"Ollama returned unexpected response for model '{model}'", file=sys.stderr)
        print(f"  Try: ollama pull {model}", file=sys.stderr)
        sys.exit(1)


def load_kb_entries(kb_dir: Path) -> list[dict]:
    """Read YAML knowledge base entries from the standard directory layout."""
    entries: list[dict] = []
    for namespace in ("decisions", "patterns", "sessions"):
        ns_dir = kb_dir / namespace
        if not ns_dir.is_dir():
            continue
        for fname in sorted(ns_dir.iterdir()):
            if not fname.suffix in (".yaml", ".yml"):
                continue
            raw = fname.read_text()
            key = fname.stem
            title = ""
            for line in raw.splitlines():
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip("\"'")
                    break
            entries.append({
                "namespace": namespace,
                "key": key,
                "title": title,
                "content": raw,
            })
    return entries


def check_ollama_model(model: str) -> None:
    """Verify the embedding model is available in Ollama."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        names = [m.get("name", "") for m in data.get("models", [])]
        if not any(n.startswith(model.split(":")[0]) for n in names):
            print(f"⚠️  Embedding model '{model}' not found in Ollama. Pulling...")
            os.system(f"ollama pull {model}")
    except Exception:
        pass  # Will fail later when embedding is attempted


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_health(_args):
    result = api("/health")
    if result is None:
        return
    status = result.get("status", "?")
    version = result.get("version", "?")
    print(f"Central KB server: {status} v{version}")


def cmd_submit(args):
    proj = args.project or project_name()
    if not proj:
        print("ERROR: --project or CENTRAL_KB_PROJECT required", file=sys.stderr)
        sys.exit(1)

    # Determine KB directory
    kb_dir = Path(args.dir) if args.dir else Path.cwd() / "knowledgebase"
    if not kb_dir.is_dir():
        # Try parent (common when running from project root with knowledgebase/ as sibling)
        alt = Path.cwd() / "project" / "knowledgebase"
        if alt.is_dir():
            kb_dir = alt
        else:
            print(f"ERROR: No knowledgebase/ directory found at {kb_dir}", file=sys.stderr)
            sys.exit(1)

    entries = load_kb_entries(kb_dir)
    if not entries:
        print("No YAML entries found in knowledgebase/", file=sys.stderr)
        sys.exit(1)

    # Check embedding source — skip Ollama model check if sidecar is available
    model = embed_model()
    embed_http_url = _detect_embed_http_url()
    if embed_http_url:
        print(f"Using embed-server HTTP sidecar ({embed_http_url}) for embeddings")
    else:
        print(f"embed-server sidecar not reachable, falling back to Ollama ({model})")
        check_ollama_model(model)
    dim = None

    source = embed_http_url or f"ollama:{model}"
    print(f"Generating embeddings via {source} for {len(entries)} entries...")
    for i, entry in enumerate(entries):
        embed_text = f"{entry['title']}\n{entry['content'][:512]}"
        vec = get_embedding(embed_text)
        entry["vector"] = vec
        # Compute simhash to prevent server-side OverflowError
        entry["simhash"] = simhash_64(f"{entry['title']}\n{entry['content']}")
        if dim is None:
            dim = len(vec)
        print(f"  [{i+1}/{len(entries)}] {entry['namespace']}:{entry['key'][:48]}  (dim={len(vec)})")

    # Submit in batches of 5 to avoid large payloads
    batch_size = 5
    total_accepted = 0
    total_dup = 0
    total_conflict = 0
    total_error = 0

    for start in range(0, len(entries), batch_size):
        batch = entries[start : start + batch_size]
        payload = {
            "project": proj,
            "source": f"local:{kb_dir.name}",
            "entries": batch,
        }
        result = api("/submit", method="POST", body=payload, timeout=60)
        if not result:
            # api() returned empty (server error) — count entire batch as errors
            total_error += len(batch)
            for entry in batch:
                print(f"  ❌ {entry['namespace']}:{entry['key'][:48]}  server error")
            continue
        total_accepted += result.get("accepted", 0)
        total_dup += result.get("duplicates", 0)
        total_conflict += result.get("conflicted", 0)
        for detail in result.get("details", []):
            if detail.get("status") not in ("accepted", "duplicate"):
                total_error += 1
                print(f"  ⚠️  {detail.get('fqn', '?')}: {detail.get('status', '?')}")

    print(f"\n✅ Submitted {len(entries)} entries → {total_accepted} accepted, {total_dup} duplicates, {total_conflict} conflicts, {total_error} errors")


def cmd_pull(args):
    proj = args.project or project_name()
    if not proj:
        print("ERROR: --project or CENTRAL_KB_PROJECT required", file=sys.stderr)
        sys.exit(1)

    params = f"?project={proj}"
    if args.after_version:
        params += f"&after_version={args.after_version}"
    if args.scope:
        params += f"&scope={args.scope}"

    result = api(f"/pull{params}")
    if result is None:
        return
    entries = result.get("entries", [])
    drift_warnings = result.get("drift_warnings", [])

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Pulled {len(entries)} entries from project '{proj}'")
        for e in entries:
            print(f"  {e.get('fqn', '?')}  v{e.get('version', '?')}  [{e.get('namespace', '?')}] {e.get('title', '?')[:60]}")
        if drift_warnings:
            print(f"\n⚠️  {len(drift_warnings)} drift warnings:")
            for w in drift_warnings:
                print(f"  Your: {w.get('your_entry', '?')} → {w.get('your_conclusion', '?')[:50]}")
                print(f"  Other: {w.get('other_entry', '?')} → {w.get('other_conclusion', '?')[:50]}")


def cmd_search(args):
    params = f"?q={urllib.request.quote(args.query)}"
    if args.scope:
        params += f"&scope={args.scope}"
    if args.namespace:
        params += f"&namespace={args.namespace}"
    if args.alpha is not None:
        params += f"&alpha={args.alpha}"
    if args.limit:
        params += f"&limit={args.limit}"

    result = api(f"/search{params}")
    if result is None:
        return

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        results = result.get("results", [])
        print(f"Search: \"{args.query}\"  ({len(results)} results)")
        for r in results:
            score = r.get("score", 0)
            cos = r.get("cosine_score", 0)
            fts = r.get("fts_score", 0)
            title = r.get("title", "")[:60] or "(no title)"
            print(f"  {r.get('fqn', '?'):55s}  score={score:.3f} (cos={cos:.3f} fts={fts:.3f})  {title}")


def cmd_drift(args):
    proj = args.project or project_name()
    if not proj:
        print("ERROR: --project or CENTRAL_KB_PROJECT required", file=sys.stderr)
        sys.exit(1)

    result = api(f"/drift?project={proj}")
    if result is None:
        return
    items = result.get("drift_items", [])
    if items:
        print(f"⚠️  {len(items)} drift items detected:")
        for item in items:
            print(f"  {item}")
    else:
        print(f"✅ No drift detected for project '{proj}'")


def cmd_candidates(_args):
    result = api("/candidates")
    if result is None:
        return
    cands = result.get("candidates", [])
    if not cands:
        print("No promotion candidates")
    else:
        print(f"{len(cands)} promotion candidates:")
        for c in cands:
            print(f"  #{c['id']}  {c['candidate_fqn']}  sim={c.get('avg_similarity', 0):.3f}  projects={c.get('project_count', 0)}  [{c.get('status', '?')}]")



def _detect_chat_model():
    """Auto-detect an available Ollama chat model."""
    # Priority: user-configured models first, then common small chat models
    preferred = ["qwen2.5:0.5b", "qwen2.5:1.5b", "gemma3:4b", "llama3.2:1b", "phi3:mini"]
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        available = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
        for candidate in preferred:
            if any(candidate.split(":")[0] == a for a in available):
                # Return the exact name from available models
                for m in data.get("models", []):
                    if m.get("name", "").split(":")[0] == candidate.split(":")[0]:
                        return m["name"]
    except Exception:
        pass
    return None


def cmd_explain(args):
    """Search the KB and synthesize a narrative explanation."""
    proj = args.project or project_name()
    if not proj:
        print("ERROR: --project or CENTRAL_KB_PROJECT required", file=sys.stderr)
        sys.exit(1)

    # 1. Search
    params = f"?q={urllib.request.quote(args.query)}"
    if proj:
        params += f"&scope={proj}"
    if args.namespace:
        params += f"&namespace={args.namespace}"
    limit = args.limit or (5 if args.llm else 10)
    params += f"&limit={limit}"

    result = api(f"/search{params}")
    if result is None:
        return
    results = result.get("results", [])
    if not results:
        print(f'No results for "{args.query}"')
        return

    # 2. Build context from results
    context_parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(no title)")
        fqn = r.get("fqn", "?")
        score = r.get("score", 0)
        cos = r.get("cosine_score", 0)
        fts = r.get("fts_score", 0)
        content = r.get("content", "")
        entry_text = (
            "--- Entry " + str(i) + ": " + fqn + " ---" + chr(10) +
            "Title: " + title + chr(10) +
            "Relevance: score=" + f"{score:.3f}" + " (cosine=" + f"{cos:.3f}" + " fts=" + f"{fts:.3f}" + ")" + chr(10) +
            "Content:" + chr(10) + content
        )
        context_parts.append(entry_text)
    context = (chr(10) + chr(10)).join(context_parts)

    # 3. Generate explanation
    model = args.model or os.environ.get("KB_LLM_MODEL", "") or _detect_chat_model()

    if args.llm:
        system_prompt = (
            "You are a knowledge management assistant. Given search results from a "
            "team knowledge base, produce a clear, structured narrative that explains "
            "how the entries relate to each other, trace their evolution over time, "
            "and connect them to the project context. Focus on causal chains, "
            "superseding decisions, and practical implications. Use specific entry IDs "
            "and dates. Avoid generic summaries. Explain why and what changed."
        )
        user_prompt = (
            "Explain the topic "" + args.query + "" in the context of this project knowledge base. " +
            "Here are the search results:" + chr(10) + chr(10) + context
        )
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            resp = urllib.request.urlopen(req, timeout=120)
            llm_result = json.loads(resp.read())
            explanation = llm_result.get("message", {}).get("content", "")
            if not explanation:
                explanation = llm_result.get("response", "(no response)")
            print(explanation)
        except urllib.error.URLError as e:
            print(f"LLM error: {e.reason}", file=sys.stderr)
            print(f"Falling back to structured output. Try: ollama pull qwen2.5:0.5b", file=sys.stderr)
            _print_structured_explain(args.query, results)
    else:
        _print_structured_explain(args.query, results)


def _print_structured_explain(query, results):
    """Print search results in a structured explain format without LLM."""
    print()
    print(f"=== Explain: \"{query}\" ({len(results)} entries) ===")
    print()
    for i, r in enumerate(results, 1):
        title = r.get("title", "(no title)")
        fqn = r.get("fqn", "?")
        score = r.get("score", 0)
        cos = r.get("cosine_score", 0)
        fts = r.get("fts_score", 0)
        content = r.get("content", "")
        preview_lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("id:")][:3]
        preview = " | ".join(preview_lines) if preview_lines else title
        print(f"{i}. {fqn}")
        print(f"   Title: {title}")
        print(f"   Score: {score:.3f} (cosine={cos:.3f}, fts={fts:.3f})")
        print(f"   Key:   {preview[:120]}")
        print()
    print("Tip: Use --llm to get a synthesized narrative explanation.")


def cmd_conflicts(args):
    if args.conflict_id and args.resolve:
        # Resolve a conflict
        body = {"resolution": args.resolve}
        result = api(f"/conflicts/{args.conflict_id}/resolve", method="POST", body=body)
        if result is None:
            return
        print(f"Conflict {args.conflict_id} resolved: {args.resolve}")
    else:
        # List conflicts
        result = api("/conflicts")
        if result is None:
            return
        conflicts = result.get("conflicts", [])
        if not conflicts:
            print("No conflicts")
        else:
            print(f"{len(conflicts)} conflicts:")
            for c in conflicts:
                print(f"  #{c['id']}  existing={c['existing_fqn']}  proposed={c['proposed_fqn']}  sim={c.get('similarity', 0):.3f}  [{c.get('status', '?')}]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="kb",
        description="Central Knowledge Base CLI — submit, pull, search, and manage KB entries",
    )
    parser.add_argument("--url", default=None, help="Server URL (default: CENTRAL_KB_URL env)")
    sub = parser.add_subparsers(dest="command", required=True)

    # health
    p = sub.add_parser("health", help="Check server health")

    # submit
    p = sub.add_parser("submit", help="Submit local KB YAML entries to server")
    p.add_argument("--project", "-p", default=None, help="Project name (or set CENTRAL_KB_PROJECT)")
    p.add_argument("--dir", default=None, help="Knowledge base directory (default: ./knowledgebase)")

    # pull
    p = sub.add_parser("pull", help="Pull entries from server")
    p.add_argument("--project", "-p", default=None, help="Project name")
    p.add_argument("--scope", "-s", default=None, help="Filter by scope")
    p.add_argument("--after-version", type=int, default=None, help="Pull entries after this version")
    p.add_argument("--json", dest="json_output", action="store_true", help="Output raw JSON")

    # search
    p = sub.add_parser("search", help="Search entries (semantic + full-text)")
    p.add_argument("query", help="Search query")
    p.add_argument("--scope", "-s", default=None, help="Filter by scope/project")
    p.add_argument("--namespace", "-n", default=None, help="Filter by namespace")
    p.add_argument("--alpha", type=float, default=None, help="Hybrid search weight (0=FTS, 1=vector)")
    p.add_argument("--limit", "-l", type=int, default=None, help="Max results")
    p.add_argument("--json", dest="json_output", action="store_true", help="Output raw JSON")

    # drift
    p = sub.add_parser("drift", help="Check for conceptual drift")
    p.add_argument("--project", "-p", default=None, help="Project name")

    # candidates
    p = sub.add_parser("candidates", help="List promotion candidates")

    # explain
    p = sub.add_parser("explain", help="Search KB and explain how entries relate (use --llm for narrative)")
    p.add_argument("query", help="Topic to explain")
    p.add_argument("--project", "-p", default=None, help="Project name")
    p.add_argument("--scope", "-s", default=None, help="Filter by scope/project")
    p.add_argument("--namespace", "-n", default=None, help="Filter by namespace")
    p.add_argument("--limit", "-l", type=int, default=None, help="Max results (default 10)")
    p.add_argument("--llm", action="store_true", help="Use Ollama LLM to synthesize narrative explanation")
    p.add_argument("--model", "-m", default=None, help="Ollama model for --llm (default: auto-detect)")

    # conflicts
    p = sub.add_parser("conflicts", help="List or resolve conflicts")
    p.add_argument("conflict_id", type=int, nargs="?", default=None, help="Conflict ID to resolve")
    p.add_argument("--resolve", "-r", default=None, help="Resolution text (triggers resolve action)")

    args = parser.parse_args()

    # Override URL if flag given
    if args.url:
        os.environ["CENTRAL_KB_URL"] = args.url

    commands = {
        "health": cmd_health,
        "submit": cmd_submit,
        "pull": cmd_pull,
        "search": cmd_search,
        "drift": cmd_drift,
        "candidates": cmd_candidates,
        "explain": cmd_explain,
        "conflicts": cmd_conflicts,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()