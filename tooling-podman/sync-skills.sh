#!/bin/bash
# Sync custom skills from .claude/skills/ into tooling/skills/
# Run this before `docker compose build tooling` if skills have changed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SRC="$PROJECT_ROOT/.claude/skills"
DST="$SCRIPT_DIR/skills"

if [ ! -d "$SRC" ]; then
    echo "ERROR: Source directory $SRC does not exist."
    echo "Create skills in .claude/skills/ first."
    exit 1
fi

# Clean destination and copy fresh
rm -rf "$DST"
cp -r "$SRC" "$DST"

# Count synced skills
SKILL_COUNT=$(ls -1d "$DST"/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "Synced $SKILL_COUNT skills to tooling/skills/:"
ls -1d "$DST"/*/ | xargs -I{} basename {}

echo ""
echo "Now run: docker compose build tooling"