"""Obs — lightweight observability for KB retrieval decisions.

A tiny, dependency-free event emitter + store + sampler + Starlette API that
surfaces every KB search decision (query, backend, latency, top results) and
embed-server memory. Served from the tooling container on port 8080.

Layout:
    emitter.py   emit(event) / emit_search(...)  -> append JSONL
    store.py     read_events(n) / tail()          -> read back
    sampler.py   embed-server RSS via docker socket
    api.py       Starlette app (/obs/*)
    static/      single-page dashboard
"""
from .emitter import emit, emit_search
from .store import read_events, read_samples

__all__ = ["emit", "emit_search", "read_events", "read_samples"]
