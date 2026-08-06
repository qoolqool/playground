#!/usr/bin/env bash
# testbed — Wrapper script that sets PYTHONPATH automatically
# Usage: ./testbed <command> [args...]
#   or:  testbed <command> [args...]  (if on PATH)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export PYTHONPATH="$PROJECT_DIR:$PYTHONPATH"

exec python3 -m testbed.cli "$@"
