"""Read back events and samples from the JSONL files.

The obs server (separate process from the emitters) reads the same files the
emitters append to. read_events returns the last N events; read_samples returns
the last N memory samples.
"""
import json
import os
from pathlib import Path

OBS_DIR = Path(os.environ.get("OBS_DIR", "/project/.agent/obs"))
EVENTS_FILE = OBS_DIR / "events.jsonl"
SAMPLES_FILE = OBS_DIR / "samples.jsonl"


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
