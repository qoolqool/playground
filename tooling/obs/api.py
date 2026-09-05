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
import os
import secrets
import statistics
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from starlette.routing import Route

from . import store

STATIC_DIR = Path(__file__).parent / "static"
SUMMARY_WINDOW_MIN = 10

# Optional shared-secret auth. If OBS_TOKEN is unset the API is open (rely on
# loopback-only binding in entrypoint). If set, every route except /obs/health
# requires `Authorization: Bearer <OBS_TOKEN>`.
OBS_TOKEN = os.environ.get("OBS_TOKEN", "")

# Cap concurrent SSE clients to bound resource use (unauthenticated DoS guard).
MAX_SSE_CLIENTS = 20
_sse_clients = 0
_sse_clients_lock = asyncio.Lock()


def _check_auth(request):
    """Return an error response if the request is unauthorized, else None."""
    if not OBS_TOKEN:
        return None
    supplied = request.headers.get("Authorization", "")
    if secrets.compare_digest(supplied, f"Bearer {OBS_TOKEN}"):
        return None
    return JSONResponse({"error": "unauthorized"}, status_code=401)


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
    auth = _check_auth(request)
    if auth is not None:
        return auth

    global _sse_clients
    async with _sse_clients_lock:
        if _sse_clients >= MAX_SSE_CLIENTS:
            return JSONResponse({"error": "too many connections"}, status_code=429)
        _sse_clients += 1

    async def gen():
        global _sse_clients
        try:
            last_count = store.event_count()
            while True:
                if await request.is_disconnected():
                    break
                count = store.event_count()
                if count > last_count:
                    for e in store.read_events(count - last_count):
                        yield f"data: {json.dumps(e)}\n\n"
                    last_count = count
                await asyncio.sleep(1)
        finally:
            async with _sse_clients_lock:
                _sse_clients -= 1

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _index(request):
    auth = _check_auth(request)
    if auth is not None:
        return auth
    return HTMLResponse(
        (STATIC_DIR / "index.html").read_text(encoding="utf-8"),
        headers={"Content-Security-Policy": "default-src 'self'"},
    )


def _root(request):
    """Redirect the bare root to the dashboard so /obs is reachable at /."""
    return RedirectResponse("/obs", status_code=302)


def _raw(request):
    auth = _check_auth(request)
    if auth is not None:
        return auth
    try:
        n = int(request.query_params.get("n", 100))
    except ValueError:
        n = 100
    n = max(0, min(n, 1000))
    return JSONResponse(store.read_events(n))


def _summary_route(request):
    auth = _check_auth(request)
    if auth is not None:
        return auth
    return JSONResponse(_summary())


def _health(request):
    return JSONResponse({"status": "ok", "service": "obs"})


async def _mark_used(request):
    """POST /obs/used — mark matching events as used.

    Body (all optional): {"id", "session_id", "turn_id", "query", "all"}.
    Returns {"marked": n}.
    """
    auth = _check_auth(request)
    if auth is not None:
        return auth
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json body"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    n = store.mark_used(
        event_id=body.get("id"),
        session_id=body.get("session_id"),
        turn_id=body.get("turn_id"),
        query=body.get("query"),
        all_matching=bool(body.get("all")),
    )
    return JSONResponse({"marked": n})


routes = [
    Route("/", _root),
    Route("/obs", _index),
    Route("/obs/events", _events_sse),
    Route("/obs/summary", _summary_route),
    Route("/obs/raw", _raw),
    Route("/obs/used", _mark_used, methods=["POST"]),
    Route("/obs/health", _health),
]


@asynccontextmanager
async def lifespan(app):
    # The sampler runs in its own sidecar container (obs-sampler) so this web
    # process never holds the Docker socket. Nothing to start here.
    yield


app = Starlette(routes=routes, lifespan=lifespan)
