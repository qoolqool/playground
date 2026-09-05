"""Read back events and samples from the JSONL files.

The obs server (separate process from the emitters) reads the same files the
emitters append to. read_events returns the last N events; read_samples returns
the last N memory samples.
"""
import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path

OBS_DIR = Path(os.environ.get("OBS_DIR", "/project/.agent/obs"))
EVENTS_FILE = OBS_DIR / "events.jsonl"
SAMPLES_FILE = OBS_DIR / "samples.jsonl"
LOCK_FILE = OBS_DIR / "events.lock"


@contextmanager
def _file_lock():
    """OS-level exclusive lock shared with emitter.emit (cross-process safe)."""
    OBS_DIR.mkdir(parents=True, exist_ok=True)
    f = open(LOCK_FILE, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def _read_jsonl(path: Path, n: int) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out[-n:] if n > 0 else out


def read_events(n: int = 100) -> list[dict]:
    """Return the last n events (newest last)."""
    return _read_jsonl(EVENTS_FILE, n)


def read_samples(n: int = 100) -> list[dict]:
    """Return the last n memory samples (newest last)."""
    return _read_jsonl(SAMPLES_FILE, n)


def event_count() -> int:
    """Total number of events ever recorded (for SSE diffing)."""
    if not EVENTS_FILE.exists():
        return 0
    count = 0
    with open(EVENTS_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def mark_used(
    event_id: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    query: str | None = None,
    all_matching: bool = False,
) -> int:
    """Mark matching events as used (used=true). Rewrites the JSONL in place.

    Matching precedence: event_id > (session_id+turn_id) > session_id > query.
    By default only the most recent match is marked; pass all_matching=True to
    mark every match. Returns the number of events newly marked.

    The read-modify-write is guarded by an OS-level file lock shared with
    emitter.emit so a concurrent append cannot be lost or corrupted.
    """
    with _file_lock():
        if not EVENTS_FILE.exists():
            return 0
        events: list[dict] = []
        with open(EVENTS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        def _match(ev: dict) -> bool:
            if event_id is not None:
                return ev.get("id") == event_id
            if session_id is not None and turn_id is not None:
                return ev.get("session_id") == session_id and ev.get("turn_id") == turn_id
            if session_id is not None:
                return ev.get("session_id") == session_id
            if query is not None:
                return ev.get("query_used") == query or ev.get("query_original") == query
            return False

        idxs = [i for i, ev in enumerate(events) if _match(ev)]
        if not idxs:
            return 0
        targets = idxs if all_matching else [idxs[-1]]
        marked = 0
        for i in targets:
            if events[i].get("used") is not True:
                events[i]["used"] = True
                marked += 1
        if marked:
            with open(EVENTS_FILE, "w", encoding="utf-8") as f:
                for ev in events:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return marked
