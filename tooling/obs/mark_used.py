#!/usr/bin/env python3
"""Mark obs retrieval events as used.

After the agent actually uses retrieved context, call this to record the
decision. By default marks the most recent event.

Usage:
  obs-mark-used                     # mark most recent event used
  obs-mark-used --id <event-id>     # mark a specific event
  obs-mark-used --query "..."       # mark most recent event for a query
  obs-mark-used --session S --turn T
  obs-mark-used --all               # mark all matching (with any filter)

POSTs to the obs API (default http://localhost:8080/obs/used).
"""
import argparse
import json
import sys
import urllib.request

API = "http://localhost:8080/obs/used"


def main() -> int:
    p = argparse.ArgumentParser(description="Mark obs retrieval events as used")
    p.add_argument("--id", dest="event_id", help="mark a specific event by id")
    p.add_argument("--query", help="mark most recent event matching this query")
    p.add_argument("--session", help="mark events for this session id")
    p.add_argument("--turn", help="mark events for this turn id")
    p.add_argument("--all", action="store_true",
                   help="mark all matching events (not just the most recent)")
    p.add_argument("--api", default=API, help="obs API base (default: %(default)s)")
    args = p.parse_args()

    payload: dict = {}
    if args.event_id:
        payload["id"] = args.event_id
    if args.query:
        payload["query"] = args.query
    if args.session:
        payload["session_id"] = args.session
    if args.turn:
        payload["turn_id"] = args.turn
    if args.all:
        payload["all"] = True

    req = urllib.request.Request(
        args.api,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"marked {resp.get('marked', 0)} event(s) as used")
    return 0


if __name__ == "__main__":
    sys.exit(main())
