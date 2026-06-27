#!/usr/bin/env python3
"""
Forget Sweep — Apply decay to knowledgebase entries, archiving stale ones.

Decay formula (inspired by ai-memory / agentmemory):
    retention = salience × exp(-λ × weeks_since_access)
               + σ × log(1 + access_count) × exp(-μ × days_since_access)

Defaults: λ=0.02, σ=0.6, μ=0.04, cold_threshold=0.20

Entries below threshold get archived to knowledgebase/_archive/.
Pinned entries (pinned: true) are exempt. is_latest: false entries skip calculation.
"""
import argparse
import math
import os
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path


KB = Path("/project/knowledgebase")
ARCHIVE = KB / "_archive"
INDEX = KB / "index.yaml"

# Tunable parameters
LAMBDA = 0.02   # base decay rate (lower = slower forget)
SIGMA = 0.6     # reinforcement strength from access count
MU = 0.04       # recency weight for access-based reinforcement
COLD_THRESHOLD = 0.20  # below this → archive


def parse_yaml_simple(text: str) -> dict:
    result = {}
    lines = text.split("\n")
    key = None
    buf = []
    in_block = False

    for line in lines:
        if in_block:
            if line and (line[0:2] == "  " or line.strip() == "" or line.startswith("    ")):
                buf.append(line[2:] if line.startswith("  ") and not line.startswith("    ") else line)
                continue
            else:
                result[key] = "\n".join(buf).strip()
                buf = []
                in_block = False
        m = None
        for sep in [": ", ":"]:
            idx = line.find(sep)
            if idx > 0 and not line.startswith(" "):
                m = (line[:idx], line[idx + len(sep):])
                break
        if m:
            key = m[0]
            val = m[1].strip()
            if val in (">", "|"):
                in_block = True
                buf = []
            elif val:
                result[key] = val
            else:
                result[key] = ""
    if in_block and key:
        result[key] = "\n".join(buf).strip()
    return result


def compute_retention(salience: float, access_count: int, last_accessed_str: str,
                      created_str: str) -> float:
    """Compute decay score. Returns a float 0-1."""
    now = datetime.now(timezone.utc)

    # Time since last access
    if last_accessed_str:
        try:
            last_access = datetime.fromisoformat(last_accessed_str)
            if last_access.tzinfo is None:
                last_access = last_access.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            last_access = None
    else:
        last_access = None

    # Time since creation (fallback if no access record)
    try:
        created = datetime.fromisoformat(created_str)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        created = now

    reference_time = last_access if last_access else created
    days_since = max(0, (now - reference_time).total_seconds() / 86400)
    weeks_since = days_since / 7

    # Base temporal decay
    base = salience * math.exp(-LAMBDA * weeks_since)

    # Reinforcement from access count
    reinforcement = SIGMA * math.log(1 + access_count) * math.exp(-MU * days_since)

    return base + reinforcement


def run_sweep(dry_run: bool = False, verbose: bool = False):
    """Run the forget sweep across all knowledgebase directories."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    dirs = {
        "decisions": KB / "decisions",
        "patterns": KB / "patterns",
        "sessions": KB / "sessions",
        "gotchas": KB / "gotchas",
        "rules": KB / "rules",
    }

    archived = 0
    checked = 0
    exempt = 0

    print("Forget Sweep Report")
    print(f"  Parameters: λ={LAMBDA}, σ={SIGMA}, μ={MU}, threshold={COLD_THRESHOLD}")
    print(f"  Archive: {ARCHIVE}\n")

    for folder_name, dir_path in dirs.items():
        if not dir_path.exists():
            continue
        files = sorted(dir_path.glob("*.yaml"))
        for fpath in files:
            checked += 1
            try:
                text = fpath.read_text()
                parsed = parse_yaml_simple(text)

                # Skip non-latest entries (already handled by supersession)
                is_latest = parsed.get("is_latest", "true")
                if is_latest and is_latest.lower() in ("false", "no", "0"):
                    exempt += 1
                    continue

                # Skip pinned entries
                if parsed.get("pinned", "").lower() in ("true", "yes", "1"):
                    exempt += 1
                    if verbose:
                        print(f"  ⊙ PINNED: {fpath.name}")
                    continue

                # Parse fields
                salience = float(parsed.get("salience", 5))
                access_count = int(parsed.get("access_count", 0))
                last_accessed = parsed.get("last_accessed_at", "")
                date_str = parsed.get("date", "") or parsed.get("created_at", "") or now

                retention = compute_retention(salience, access_count, last_accessed, date_str)

                status = "✓ KEEP" if retention >= COLD_THRESHOLD else "✗ ARCHIVE"
                if verbose or retention < COLD_THRESHOLD:
                    print(f"  {status} {folder_name}/{fpath.name} "
                          f"(salience={salience}, accesses={access_count}, "
                          f"retention={retention:.4f})")

                if retention < COLD_THRESHOLD:
                    if not dry_run:
                        archive_path = ARCHIVE / folder_name / fpath.name
                        archive_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(fpath), str(archive_path))
                        print(f"    → moved to _archive/{folder_name}/{fpath.name}")
                    archived += 1

            except Exception as e:
                print(f"  ERROR {fpath.name}: {e}")

    print(f"\n  Summary: {checked} checked, {archived} archived, {exempt} exempt")

    if dry_run:
        print(f"  ⚠  DRY RUN — no files were moved. Remove --dry-run to archive.")

    return 0


def main():
    global COLD_THRESHOLD

    parser = argparse.ArgumentParser(
        description="Forget Sweep — decay stale knowledgebase entries"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be archived without moving files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show every entry, not just archived ones")
    parser.add_argument("--threshold", type=float, default=COLD_THRESHOLD,
                        help=f"Cold threshold (default: {COLD_THRESHOLD})")
    args = parser.parse_args()

    COLD_THRESHOLD = args.threshold

    return run_sweep(dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
