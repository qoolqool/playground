#!/usr/bin/env python3
"""Wrapper for search-kb-memory.py that emits an obs event.

Runs the real submodule search script (unchanged), times it, best-effort parses
the printed results, and emits a structured event to the obs dashboard. This is
the 1B shim: the submodule script itself is never modified.

The entrypoint symlinks `tooling/scripts/search-kb-memory.py` -> this file.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

# Make the obs package importable (this file lives in tooling/obs/, so the
# package root is one level up).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obs import emit_search  # noqa: E402

# The real submodule search script (never modified).
REAL_SCRIPT = Path(
    "/project/tooling/skill-marketplace/plugins/distill-rag-bridge/"
    "skills/search-kb/search-kb-memory.py"
)

_SCORE_RE = re.compile(r"^\s+\d+\.\s+.*\(score:\s+([\d.]+)\)")


def parse_results(stdout: str) -> list[dict]:
    """Best-effort parse of the printed result lines into {score} dicts."""
    results = []
    for line in stdout.splitlines():
        m = _SCORE_RE.match(line)
        if m:
            results.append({"score": float(m.group(1))})
    return results


def main() -> int:
    # Parse the same args as the real script so we can extract the query.
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("query", nargs="*")
    p.add_argument("-n", "--namespace")
    p.add_argument("-l", "--limit", type=int)
    p.add_argument("--context")
    try:
        ns, _ = p.parse_known_args()
    except SystemExit:
        ns = argparse.Namespace(query=[], namespace=None, limit=None, context=None)

    query_used = " ".join(ns.query) if ns.query else ""

    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(REAL_SCRIPT)] + sys.argv[1:],
            capture_output=True, text=True,
        )
    except Exception as e:  # pragma: no cover
        emit_search(query_original=query_used, query_used=query_used,
                    backend="local-vector", latency_ms=(time.time() - t0) * 1000,
                    top_k=0, results=[], error=f"wrapper: {e}")
        return 1

    latency_ms = (time.time() - t0) * 1000
    results = parse_results(proc.stdout)
    top_k = ns.limit or 5

    emit_search(
        query_original=query_used,
        query_used=query_used,
        backend="local-vector",
        latency_ms=latency_ms,
        top_k=top_k,
        results=results,
        error=None if proc.returncode == 0 else (proc.stderr.strip() or "search failed"),
    )

    # Reproduce the real script's output exactly (stdout + stderr).
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
