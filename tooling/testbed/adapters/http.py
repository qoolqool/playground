"""HTTP callflow adapter.

Makes a single HTTP request to a target service's published port and
compares the result against the edge's expected outcome.

Uses only the Python standard library (urllib) so it runs anywhere pytest
runs, with no extra dependencies.

Request spec (edge.request):
    method:   HTTP method, default GET
    path:     URL path + optional query string, default "/"

Expected result (edge.expect):
    mode:       exact | contains | success
    status:     expected status code (when set)
    body:       expected response body (exact/contains modes)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from testbed.contracts.spec import ExpectMode


def _target_port(target_service) -> int:
    """Resolve the published (host) port of the target service."""
    if target_service is not None and target_service.ports:
        # Prefer the first tcp mapping's host port.
        for mapping in target_service.ports:
            if mapping.protocol == "tcp":
                return mapping.host
        return target_service.ports[0].host
    raise ValueError(
        "HTTP callflow edge has no target service with a published port"
    )


def _response_equals(actual: dict, expected: dict) -> bool:
    """Deep equality for exact mode."""
    return actual == expected


def _is_subset(expected, actual) -> bool:
    """Recursive subset check: is expected a subset of actual?"""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(
            key in actual and _is_subset(val, actual[key])
            for key, val in expected.items()
        )
    elif isinstance(expected, dict) or isinstance(actual, dict):
        return False
    # Compare lists element-wise (order-sensitive) if both are lists
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) > len(actual):
            return False
        return all(_is_subset(e, a) for e, a in zip(expected, actual))
    return expected == actual


def _matches(edge, status: int, body) -> bool:
    """Check the actual (status, body) against edge.expect."""
    expect = edge.expect
    mode = expect.mode

    if expect.status is not None and status != expect.status:
        return False

    if mode in (ExpectMode.exact, ExpectMode.contains):
        if expect.body is None:
            # No body to compare; status match is enough
            return expect.status is not None or status < 400
        if mode == ExpectMode.exact:
            return _response_equals(body, expect.body)
        return _is_subset(expect.body, body)
    # success mode
    return status < 400


def run(edge, target_service, base_host, workspace_root, timeout=15):
    """Execute the edge as a single HTTP request. Never raises."""
    from testbed.adapters import AdapterResult

    request = edge.request or {}
    method = (request.get("method", "GET") or "GET").upper()
    path = request.get("path", "/")

    try:
        port = _target_port(target_service)
    except ValueError as exc:
        return AdapterResult(passed=False, error=str(exc))

    url = f"http://{base_host}:{port}{path}"
    req = urllib.request.Request(url, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read() if exc.fp else b""
    except Exception as exc:
        return AdapterResult(
            passed=False,
            actual=None,
            error=f"request to {url} failed: {exc}",
        )

    try:
        body = json.loads(raw)
    except Exception:
        body = raw.decode("utf-8", errors="replace")

    actual = {"status": status, "body": body}
    try:
        ok = _matches(edge, status, body)
    except Exception as exc:
        return AdapterResult(
            passed=False,
            actual=actual,
            error=f"comparison failed: {exc}",
        )

    if not ok:
        return AdapterResult(
            passed=False,
            actual=actual,
            error=(
                f"expected result did not match for edge '{edge.id}' "
                f"(GET {path}); expected {edge.expect.model_dump(mode='json')}, "
                f"got {json.dumps(actual) if not isinstance(body, str) else actual}"
            ),
        )

    return AdapterResult(passed=True, actual=actual, error=None)
