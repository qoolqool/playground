"""Event emitter — appends structured KB-search events to a JSONL file.

Pure stdlib, append-only, <1ms per emit. The file lives on the volume-mounted
/project so it survives container restarts. The obs server (separate process)
reads the same file via store.py.
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

OBS_DIR = Path(os.environ.get("OBS_DIR", "/project/.agent/obs"))
EVENTS_FILE = OBS_DIR / "events.jsonl"

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(event: dict) -> None:
    """Append one structured event as a single JSON line. Thread-safe, <1ms."""
    OBS_DIR.mkdir(parents=True, exist_ok=True)
    event.setdefault("ts", _now())
    line = json.dumps(event, ensure_ascii=False)
    with _lock:
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()


def emit_search(
    *,
    query_original: str,
    query_used: str,
    backend: str,
    latency_ms: float,
    top_k: int,
    results: list[dict],
    used: bool | None = None,
    error: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
) -> None:
    """Emit a full PRD-schema search event."""
    emit({
        "ts": _now(),
        "session_id": session_id,
        "turn_id": turn_id,
        "query_original": query_original,
        "query_used": query_used,
        "backend": backend,
        "latency_ms": round(latency_ms, 1),
        "top_k": top_k,
        "results": results,
        "used": used,
        "error": error,
    })
