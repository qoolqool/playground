"""Tests for the obs package (emitter, store, api)."""
import json
import os
import tempfile
from pathlib import Path

import pytest

# Point obs at a temp dir before importing the modules.
_TMP = tempfile.mkdtemp(prefix="obs-test-")
os.environ["OBS_DIR"] = _TMP

from obs import emitter, store  # noqa: E402
from obs.api import app  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    for f in ("events.jsonl", "samples.jsonl"):
        p = Path(_TMP) / f
        if p.exists():
            p.unlink()
    yield


def test_emit_appends_json_line():
    emitter.emit({"query_used": "hello", "backend": "local-vector", "latency_ms": 5})
    lines = (Path(_TMP) / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    ev = json.loads(lines[0])
    assert ev["query_used"] == "hello"
    assert "ts" in ev


def test_emit_search_schema():
    emitter.emit_search(
        query_original="user question",
        query_used="user question",
        backend="central-kb",
        latency_ms=87.4,
        top_k=5,
        results=[{"id": "x", "score": 0.82, "title": "t", "snippet": "s"}],
    )
    ev = store.read_events(1)[0]
    assert ev["backend"] == "central-kb"
    assert ev["latency_ms"] == 87.4
    assert ev["top_k"] == 5
    assert ev["results"][0]["score"] == 0.82
    assert ev["used"] is None


def test_read_events_returns_last_n():
    for i in range(5):
        emitter.emit({"i": i})
    events = store.read_events(2)
    assert [e["i"] for e in events] == [3, 4]


def test_event_count():
    assert store.event_count() == 0
    emitter.emit({"a": 1})
    emitter.emit({"a": 2})
    assert store.event_count() == 2


def test_api_health():
    from starlette.testclient import TestClient
    with TestClient(app) as c:
        r = c.get("/obs/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_api_raw():
    from starlette.testclient import TestClient
    emitter.emit({"query_used": "q1", "backend": "local-vector"})
    with TestClient(app) as c:
        r = c.get("/obs/raw")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["query_used"] == "q1"


def test_api_summary():
    from starlette.testclient import TestClient
    emitter.emit_search(query_original="q", query_used="q", backend="local-vector",
                        latency_ms=10, top_k=5, results=[])
    with TestClient(app) as c:
        r = c.get("/obs/summary")
        assert r.status_code == 200
        s = r.json()
        assert s["search_count"] >= 1
        assert s["avg_latency_ms"] == 10.0


def test_api_index_serves_html():
    from starlette.testclient import TestClient
    with TestClient(app) as c:
        r = c.get("/obs")
        assert r.status_code == 200
        assert "KB Obs" in r.text


def test_emit_adds_id():
    emitter.emit({"query_used": "q"})
    ev = store.read_events(1)[0]
    assert ev["id"]


def test_mark_used_by_id():
    emitter.emit_search(query_original="q", query_used="q", backend="local-vector",
                        latency_ms=5, top_k=3, results=[])
    ev = store.read_events(1)[0]
    assert ev["used"] is None
    n = store.mark_used(event_id=ev["id"])
    assert n == 1
    assert store.read_events(1)[0]["used"] is True
    # idempotent
    assert store.mark_used(event_id=ev["id"]) == 0


def test_mark_used_by_query_marks_latest_only():
    for _ in range(3):
        emitter.emit_search(query_original="dup", query_used="dup", backend="central-kb",
                            latency_ms=5, top_k=1, results=[])
    n = store.mark_used(query="dup")
    assert n == 1
    events = store.read_events(10)
    assert [e["used"] for e in events] == [None, None, True]
    # all_matching marks the rest
    assert store.mark_used(query="dup", all_matching=True) == 2


def test_api_mark_used():
    from starlette.testclient import TestClient
    emitter.emit_search(query_original="q", query_used="q", backend="local-vector",
                        latency_ms=5, top_k=3, results=[])
    ev = store.read_events(1)[0]
    with TestClient(app) as c:
        r = c.post("/obs/used", json={"id": ev["id"]})
        assert r.status_code == 200
        assert r.json()["marked"] == 1
    assert store.read_events(1)[0]["used"] is True


def test_api_mark_used_bad_body():
    from starlette.testclient import TestClient
    with TestClient(app) as c:
        r = c.post("/obs/used", content="not json", headers={"Content-Type": "application/json"})
        assert r.status_code == 400
