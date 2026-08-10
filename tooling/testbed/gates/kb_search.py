"""
KB-aware validation — cross-references a TestbedSpec against the local
knowledgebase to surface relevant gotchas, patterns, and decisions.

The knowledgebase is the accumulated wisdom of what actually works:
gotchas (things that broke), patterns (things that worked), decisions
(architectural constraints). The feedback loop MUST consider these when
validating a spec, otherwise the agent repeats past mistakes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..contracts.spec import TestbedSpec
from ..contracts.feedback import Diagnostic, Severity, KBRef


# ---------------------------------------------------------------------------
# KB entry parsing
# ---------------------------------------------------------------------------

def _parse_kb_entry(filepath: Path) -> Optional[dict]:
    """Parse a single KB markdown file, extracting frontmatter and body.

    Supports both OKF format (YAML frontmatter between --- delimiters)
    and simple markdown (first # heading as title).
    """
    try:
        text = filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return None

    entry = {
        "path": str(filepath.relative_to(*filepath.parts[:1])),
        "title": filepath.stem,
        "body": text,
        "tags": [],
        "type": "unknown",
    }

    # Try OKF frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            entry["body"] = parts[2].strip()
            # Extract title
            m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', frontmatter, re.MULTILINE)
            if m:
                entry["title"] = m.group(1)
            # Extract tags
            m = re.search(r'^tags:\s*\[(.+?)\]', frontmatter, re.MULTILINE)
            if m:
                entry["tags"] = [t.strip().strip('"\'') for t in m.group(1).split(",")]
            # Extract type
            m = re.search(r'^type:\s*(\S+)', frontmatter, re.MULTILINE)
            if m:
                entry["type"] = m.group(1).lower()
    else:
        # Simple markdown: first # heading is the title
        m = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
        if m:
            entry["title"] = m.group(1).strip()

    # Infer category from directory name
    parent_dir = filepath.parent.name
    if parent_dir in ("gotchas", "gotcha"):
        entry["category"] = "gotcha"
    elif parent_dir in ("patterns", "pattern"):
        entry["category"] = "pattern"
    elif parent_dir in ("decisions", "decision"):
        entry["category"] = "decision"
    elif parent_dir in ("facts", "fact"):
        entry["category"] = "fact"
    elif parent_dir in ("concepts", "concept"):
        entry["category"] = "concept"
    else:
        entry["category"] = parent_dir

    return entry


def _keyword_match(entry: dict, keywords: set[str]) -> float:
    """Score how well a KB entry matches a set of keywords.

    Returns a score 0.0-1.0 based on:
    - Title match (weight 3)
    - Tag match (weight 2)
    - Body match (weight 1)
    """
    title_lower = entry["title"].lower()
    body_lower = entry["body"].lower()
    tag_lower = {t.lower() for t in entry["tags"]}

    title_hits = sum(1 for kw in keywords if kw in title_lower)
    tag_hits = sum(1 for kw in keywords if kw in tag_lower)
    body_hits = sum(1 for kw in keywords if kw in body_lower)

    n = len(keywords)
    if n == 0:
        return 0.0

    score = (title_hits / n * 3 + tag_hits / n * 2 + body_hits / n * 1) / 6.0
    return min(score, 1.0)


def _extract_snippet(body: str, keywords: set[str], max_chars: int = 200) -> str:
    """Extract a relevant snippet from the body around keyword matches."""
    body_lower = body.lower()
    best_pos = -1

    for kw in keywords:
        pos = body_lower.find(kw)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        # No keyword found — return first N chars
        return body[:max_chars].strip()

    start = max(0, best_pos - 60)
    end = min(len(body), best_pos + 140)
    snippet = body[start:end].strip()

    if start > 0:
        snippet = "..." + snippet
    if end < len(body):
        snippet = snippet + "..."

    return snippet[:max_chars]


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------

def search_kb(
    spec: TestbedSpec,
    kb_dirs: list[Path],
    min_score: float = 0.15,
    max_results: int = 10,
) -> list[Diagnostic]:
    """Search the knowledgebase for entries relevant to this spec.

    Extracts keywords from the spec (service names, images, tags, etc.)
    and matches them against KB entries. Returns diagnostics with KB refs.

    Args:
        spec: The validated TestbedSpec to cross-reference.
        kb_dirs: List of KB root directories to search.
        min_score: Minimum match score (0.0-1.0) to include a result.
        max_results: Maximum number of KB diagnostics to return.

    Returns:
        List of Diagnostic objects, each with kb_refs linking to relevant entries.
    """
    # Build keyword set from the spec
    keywords: set[str] = set()
    for svc in spec.services:
        for part in re.split(r"[-_:/. ]", svc.name):
            if len(part) > 2:
                keywords.add(part.lower())
        for part in re.split(r"[-_:/. ]", svc.image):
            if len(part) > 2:
                keywords.add(part.lower())
        for net in svc.networks:
            for part in re.split(r"[-_:/. ]", net):
                if len(part) > 2:
                    keywords.add(part.lower())
    for tag in spec.tags:
        keywords.add(tag.lower())
    for ts in spec.test_suites:
        for tag in ts.tags:
            keywords.add(tag.lower())

    # Also add common infrastructure keywords
    infrastructure_keywords = {
        "postgres", "redis", "nginx", "besu", "fabric", "solana",
        "headscale", "prometheus", "grafana", "docker", "compose",
        "memory", "limit", "healthcheck", "network", "volume",
        "container", "service", "deploy",
    }
    keywords.update(infrastructure_keywords)

    # Scan KB directories
    all_entries: list[dict] = []
    for kb_dir in kb_dirs:
        if not kb_dir.exists():
            continue
        for ext in ("*.md",):
            for fpath in kb_dir.rglob(ext):
                # Skip index files
                if fpath.name == "index.md":
                    continue
                entry = _parse_kb_entry(fpath)
                if entry:
                    all_entries.append(entry)

    # Score and rank
    scored = []
    for entry in all_entries:
        score = _keyword_match(entry, keywords)
        if score >= min_score:
            scored.append((score, entry))

    scored.sort(key=lambda x: -x[0])

    # Build diagnostics from top matches
    diagnostics: list[Diagnostic] = []
    category_icons = {
        "gotcha": "⚠️ Known gotcha",
        "pattern": "📐 Relevant pattern",
        "decision": "📋 Architectural decision",
        "fact": "ℹ️ Fact",
        "concept": "📖 Concept",
    }

    for score, entry in scored[:max_results]:
        snippet = _extract_snippet(entry["body"], keywords)
        category_label = category_icons.get(entry.get("category", ""), entry.get("category", "reference"))

        diagnostic = Diagnostic(
            code=f"KB_{entry['category'].upper()}_{entry.get('type', 'REF').upper()}",
            severity=Severity.info,
            message=f"{category_label}: {entry['title']} (relevance: {score:.0%})",
            detail=snippet,
            kb_refs=[
                KBRef(
                    path=entry["path"],
                    title=entry["title"],
                    snippet=snippet,
                    category=entry.get("category", "reference"),
                ),
            ],
        )
        diagnostics.append(diagnostic)

    return diagnostics
