"""Starlette app serving the obs dashboard and API.

Endpoints (all under /obs):
    GET /obs          -> single-page dashboard HTML
    GET /obs/events   -> SSE stream of new events
    GET /obs/summary  -> aggregates for the last N minutes
    GET /obs/raw?n=   -> last N raw events (JSON array)
    GET /obs/health   -> {"status":"ok"}

Runs inside the tooling container on port 8080 (uvicorn obs.api:app).
"""
import asyncio
import json
import statistics
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from . import sampler, store

STATIC_DIR = Path(__file__).parent / "static"
SUMMARY_WINDOW_MIN = 10


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def _summary() -> dict:
    events = store.read_events(1000)
    cutoff = _now_ts() - SUMMARY_WINDOW_MIN * 60
    recent = []
    for e in events:
        try:
            ts = datetime.fromisoformat(e.get("ts", "")).timestamp()
        except (ValueError, TypeError):
            continue
        if ts >= cutoff:
            recent.append(e)

    latencies = [e.get("latency_ms") for e in recent
                 if isinstance(e.get("latency_ms"), (int, float))]
    used_flags = [e.get("used") for e in recent if e.get("used") is not None]

    samples = store.read_samples(1)
    current_mem = samples[-1].get("embed_memory_mb") if samples else None

    return {
        "window_min": SUMMARY_WINDOW_MIN,
        "search_count": len(recent),
        "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else None,
        "p95_latency_ms": round(statistics.quantiles(latencies, n=20)[18], 1) if len(latencies) >= 20 else None,
        "hit_rate": round(sum(1 for u in used_flags if u) / len(used_flags), 3) if used_flags else None,
        "embed_memory_mb": current_mem,
        "total_events": store.event_count(),
    }


async def _events_sse(request):
    """SSE stream: yield each new event as it's appended to the JSONL file."""
    async def gen():
        last_count = store.event_count()
        while True:
            count = store.event_count()
            if count > last_count:
                for e in store.read_events(count - last_count):
                    yield f"data: {json.dumps(e)}\n\n"
                last_count = count
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _index(request):
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


def _raw(request):
    n = int(request.query_params.get("n", 100))
    return JSONResponse(store.read_events(n))


def _summary_route(request):
    return JSONResponse(_summary())


def _health(request):
    return JSONResponse({"status": "ok", "service": "obs"})


routes = [
    Route("/obs", _index),
    Route("/obs/events", _events_sse),
    Route("/obs/summary", _summary_route),
    Route("/obs/raw", _raw),
    Route("/obs/health", _health),
]


@asynccontextmanager
async def lifespan(app):
    sampler.start_sampler()
    yield


app = Starlette(routes=routes, lifespan=lifespan)
