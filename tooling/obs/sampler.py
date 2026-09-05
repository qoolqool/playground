"""Background sampler — records embed-server memory every N seconds.

The embed-server is a separate container (central-kb-embed). The tooling
container has the Docker socket mounted, so we query its memory via
`docker stats` (no psutil, no /proc cross-container access needed).
"""
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

OBS_DIR = Path(os.environ.get("OBS_DIR", "/project/.agent/obs"))
SAMPLES_FILE = OBS_DIR / "samples.jsonl"
EMBED_CONTAINER = os.environ.get("EMBED_CONTAINER", "central-kb-embed")
INTERVAL = float(os.environ.get("OBS_SAMPLE_INTERVAL", "30"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def embed_memory_mb() -> float | None:
    """Return embed-server RSS in MB via `docker stats`, or None on failure."""
    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", EMBED_CONTAINER],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if "/" not in out:
            return None
        used = out.split("/")[0].strip()
        if used.endswith("MiB"):
            return round(float(used[:-3]), 1)
        if used.endswith("GiB"):
            return round(float(used[:-3]) * 1024, 1)
        return None
    except Exception:
        return None


def sample_once() -> None:
    """Record one memory sample if the embed-server is reachable."""
    mem = embed_memory_mb()
    if mem is None:
        return
    OBS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SAMPLES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _now(), "embed_memory_mb": mem}) + "\n")


def start_sampler(interval: float = INTERVAL) -> threading.Thread:
    """Start the background sampler thread (daemon). Returns the thread."""
    def _run():
        while True:
            try:
                sample_once()
            except Exception:
                pass
            time.sleep(interval)

    t = threading.Thread(target=_run, daemon=True, name="obs-sampler")
    t.start()
    return t


def main(interval: float = INTERVAL) -> None:
    """Run the sampler loop in the foreground (sidecar container entrypoint)."""
    while True:
        try:
            sample_once()
        except Exception:
            pass
        time.sleep(interval)


if __name__ == "__main__":
    main()
