#!/usr/bin/env python3
"""Index the docs/prompts/ directory and generate a summary index.

Usage:
    python scripts/index_prompts.py              # print index to stdout
    python scripts/index_prompts.py --write       # write index to docs/prompts/INDEX.md
    python scripts/index_prompts.py --json        # output as JSON
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "prompts"


@dataclass
class PromptEntry:
    filename: str
    title: str
    subtitle: str = ""
    topics: list[str] = field(default_factory=list)
    swim_lanes: int = 0
    stages: int = 0
    aspect_ratio: str = ""


def extract_title(content: str) -> str:
    """Extract the infographic title from quoted text after 'titled:'."""
    # Strip zero-width spaces that some prompts use
    cleaned = content.replace('​', '')
    # Pattern 1: "titled:" then title in quotes on the next line
    m = re.search(r'titled:\s*\n\s*"(.+?)"', cleaned)
    if m:
        return m.group(1).strip()
    # Pattern 2: "titled:" on same line as quotes
    m = re.search(r'titled:\s*"(.+?)"', cleaned)
    if m:
        return m.group(1).strip()
    # Pattern 3: first standalone quoted line (10-120 chars)
    m = re.search(r'^"(.{10,120}?)"\s*$', cleaned, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # Pattern 4: first markdown heading
    m = re.search(r'^#\s+(.+)$', cleaned, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def extract_subtitle(content: str) -> str:
    """Extract the subtitle line (starts with 'From' or 'Subtitle:')."""
    m = re.search(r'Subtitle:\s*\n\s*"(.+?)"', content, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r'Subtitle:\s*\n(.+)', content)
    if m:
        return m.group(1).strip()
    m = re.search(r'\n\s*\n\s*"([^"]+)"\s*\n', content)
    if m:
        line = m.group(1).strip()
        if len(line) > 20:
            return line
    return ""


def extract_topics(content: str) -> list[str]:
    """Extract key topics from section headers."""
    topics = []
    headers = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
    skip = {"layout structure", "style guidelines", "color system", "output",
            "visual story", "core message", "real-world implementation",
            "required", "deliverables", "style", "layout"}
    for h in headers:
        clean = h.strip().lower()
        if not any(s in clean for s in skip) and len(h.strip()) < 60:
            topics.append(h.strip())
    return topics[:8]


def count_swim_lanes(content: str) -> int:
    """Count vertical swim lanes."""
    m = re.search(r'(\d+)\s+Vertical\s+Swim\s+Lanes?', content, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def count_stages(content: str) -> int:
    """Count horizontal stages."""
    m = re.search(r'(\d+)\s+Horizontal\s+Stages?', content, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def extract_aspect_ratio(content: str) -> str:
    """Extract aspect ratio or resolution."""
    m = re.search(r'(\d{3,4})\s*x\s*(\d{3,4})', content)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        from math import gcd
        d = gcd(w, h)
        return f"{w // d}:{h // d} ({w}x{h})"
    return ""


def index_prompt(filepath: Path) -> PromptEntry:
    """Parse a single prompt file and return a PromptEntry."""
    content = filepath.read_text(encoding="utf-8")

    title = extract_title(content)
    if not title:
        title = filepath.stem.replace("-", " ").replace("gemini ", "").title()

    subtitle = extract_subtitle(content)
    topics = extract_topics(content)
    swim_lanes = count_swim_lanes(content)
    stages = count_stages(content)
    aspect_ratio = extract_aspect_ratio(content)

    return PromptEntry(
        filename=filepath.name,
        title=title,
        subtitle=subtitle,
        topics=topics,
        swim_lanes=swim_lanes,
        stages=stages,
        aspect_ratio=aspect_ratio,
    )


def format_markdown(entries: list[PromptEntry]) -> str:
    """Format entries as a Markdown index."""
    lines = [
        "# Prompts Index",
        "",
        f"Auto-generated from `docs/prompts/` — {len(entries)} prompts",
        "",
    ]

    for i, e in enumerate(entries, 1):
        lines.append(f"## {i}. [{e.filename}]({e.filename})")
        lines.append("")
        if e.title:
            lines.append(f"**Title:** {e.title}")
        if e.subtitle:
            lines.append(f"**Subtitle:** {e.subtitle}")
        if e.aspect_ratio:
            lines.append(f"**Aspect ratio:** {e.aspect_ratio}")
        if e.swim_lanes:
            lines.append(f"**Swim lanes:** {e.swim_lanes}")
        if e.stages:
            lines.append(f"**Stages:** {e.stages}")
        if e.topics:
            lines.append(f"**Sections:** {' → '.join(e.topics)}")
        lines.append("")

    return "\n".join(lines)


def format_json(entries: list[PromptEntry]) -> str:
    """Format entries as JSON."""
    data = [
        {
            "filename": e.filename,
            "title": e.title,
            "subtitle": e.subtitle,
            "topics": e.topics,
            "swim_lanes": e.swim_lanes,
            "stages": e.stages,
            "aspect_ratio": e.aspect_ratio,
        }
        for e in entries
    ]
    return json.dumps(data, indent=2, ensure_ascii=False)


def main():
    if not PROMPTS_DIR.exists():
        print(f"Error: {PROMPTS_DIR} does not exist", file=sys.stderr)
        sys.exit(1)

    md_files = sorted(f for f in PROMPTS_DIR.glob("*.md") if f.name != "INDEX.md")
    if not md_files:
        print(f"No .md files found in {PROMPTS_DIR}", file=sys.stderr)
        sys.exit(1)

    entries = [index_prompt(f) for f in md_files]

    if "--json" in sys.argv:
        print(format_json(entries))
    elif "--write" in sys.argv:
        output_path = PROMPTS_DIR / "INDEX.md"
        output_path.write_text(format_markdown(entries), encoding="utf-8")
        print(f"Written to {output_path}")
    else:
        print(format_markdown(entries))


if __name__ == "__main__":
    main()