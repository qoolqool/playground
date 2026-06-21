#!/usr/bin/env python3
"""
OKF Migration Script — Convert existing knowledgebase entries to OKF format.

Scans the knowledgebase/ directory for legacy YAML entries and converts
them to OKF-compliant markdown files with YAML frontmatter.

Usage:
    python3 migrate-to-okf.py [--input-dir /project/knowledgebase] [--output-dir /project/knowledgebase]
    python3 migrate-to-okf.py --dry-run   # Preview without writing
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


# Reserved filenames in OKF
RESERVED_FILENAMES = {"index.md", "log.md"}

# Namespace mapping for OKF types
TYPE_TO_NAMESPACE = {
    "Decision": "decisions",
    "Pattern": "patterns",
    "Session": "sessions",
    "Metric": "metrics",
    "Table": "tables",
    "Runbook": "runbooks",
    "Playbook": "playbooks",
    "Concept": "concepts",
    "Reference": "references",
}


def parse_legacy_yaml(content: str) -> tuple[dict | None, str]:
    """Parse a legacy YAML knowledgebase entry.

    Handles two formats:
    1. Standard frontmatter: ---\\n...\\n---\\nbody
    2. YAML document: ---\\n... (no closing ---, entire file is YAML)

    Returns (frontmatter_dict, body_text) or (None, content) if no frontmatter.
    """
    # Try standard frontmatter format: ---\\n...\\n---\\nbody
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if fm_match:
        fm_raw = fm_match.group(1)
        body = fm_match.group(2).strip()
        try:
            fm = yaml.safe_load(fm_raw)
            if isinstance(fm, dict):
                return fm, body
        except yaml.YAMLError:
            pass

    # Try YAML document format: ---\\n... (no closing ---, entire file is YAML)
    yaml_match = re.match(r"^---\s*\n(.*)", content, re.DOTALL)
    if yaml_match:
        fm_raw = yaml_match.group(1).strip()
        try:
            fm = yaml.safe_load(fm_raw)
            if isinstance(fm, dict):
                return fm, ""
        except yaml.YAMLError:
            pass

    return None, content.strip()


def map_to_okf_type(fm: dict) -> str:
    """Map legacy fields to an OKF type."""
    # Direct type field
    type_val = fm.get("type", "")
    if isinstance(type_val, str) and type_val.strip():
        return type_val.strip().capitalize()

    # Map from category
    category = str(fm.get("category", "")).lower()
    type_map = {
        "decision": "Decision",
        "architecture": "Decision",
        "pattern": "Pattern",
        "session": "Session",
        "metric": "Metric",
        "runbook": "Runbook",
        "playbook": "Playbook",
        "table": "Table",
        "dataset": "Dataset",
        "reference": "Reference",
        "concept": "Concept",
    }
    for key, val in type_map.items():
        if key in category:
            return val

    # Map from namespace (folder name)
    return "Concept"


def convert_date_to_iso8601(date_str: str) -> str:
    """Convert various date formats to ISO 8601."""
    if not date_str:
        return ""

    date_str = str(date_str).strip()

    # Already ISO 8601
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", date_str):
        if not re.search(r"[Z+-]", date_str):
            date_str += "Z"
        return date_str

    # YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", date_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00Z"

    # MM/DD/YYYY
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", date_str)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}T00:00:00Z"

    # DD Mon YYYY
    m = re.match(r"^(\d{1,2})\s+(\w+)\s+(\d{4})", date_str)
    if m:
        months = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "may": "05", "jun": "06", "jul": "07", "aug": "08",
            "sep": "09", "oct": "10", "nov": "11", "dec": "12",
        }
        month = months.get(m.group(2).lower()[:3], "01")
        day = m.group(1).zfill(2)
        return f"{m.group(3)}-{month}-{day}T00:00:00Z"

    return date_str


def build_okf_document(fm: dict, body: str, source_path: str) -> str:
    """Build an OKF markdown document from parsed legacy fields."""
    okf_type = map_to_okf_type(fm)
    title = str(fm.get("title", fm.get("name", fm.get("id", Path(source_path).stem))))
    description = str(fm.get("description", fm.get("summary", "")))
    resource = str(fm.get("resource", fm.get("source", "")))
    tags = fm.get("topics", fm.get("tags", []))
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    if not isinstance(tags, list):
        tags = []

    timestamp = convert_date_to_iso8601(
        str(fm.get("timestamp", fm.get("date", fm.get("created_at", ""))))
    )

    # Build body sections from known fields
    body_parts = []
    if body:
        body_parts.append(body)

    # Add conventional sections for known fields
    section_fields = {
        "Context": "context",
        "Decision": "decision",
        "Consequences": "consequences",
        "Implementation": "implementation",
        "Rationale": "rationale",
        "Alternatives": "alternatives",
        "Schema": "schema",
        "Examples": "examples",
    }
    for section_title, field_name in section_fields.items():
        val = fm.get(field_name)
        if val and str(val).strip():
            body_parts.append(f"\n# {section_title}\n\n{str(val).strip()}")

    body_text = "\n".join(body_parts).strip()

    # Build OKF frontmatter dict
    okf_fm = {
        "type": okf_type,
        "title": title,
    }
    if description:
        okf_fm["description"] = description
    if resource:
        okf_fm["resource"] = resource
    if tags:
        okf_fm["tags"] = tags
    if timestamp:
        okf_fm["timestamp"] = timestamp

    # Preserve extra fields (not in standard set or already handled)
    standard_keys = {
        "type", "title", "description", "resource", "tags", "timestamp",
        "topics", "date", "name", "id", "summary", "decision", "source",
        "context", "consequences", "implementation", "rationale", "alternatives",
        "schema", "examples", "created_at", "status", "category",
    }
    for k, v in fm.items():
        if k not in standard_keys and v is not None and not k.startswith("_"):
            okf_fm[k] = v

    # Serialize frontmatter with proper YAML
    fm_yaml = yaml.dump(okf_fm, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()

    result = ["---", fm_yaml, "---"]
    if body_text:
        result.append("")
        result.append(body_text)

    return "\n".join(result)


def generate_index_file(directory: Path) -> str:
    """Generate an index.md for a directory of OKF concepts."""
    md_files = sorted(directory.glob("*.md"))
    concept_files = [f for f in md_files if f.name not in RESERVED_FILENAMES]

    if not concept_files:
        return ""

    dir_name = directory.name.capitalize()
    lines = [f"# {dir_name}", ""]

    for cf in concept_files:
        try:
            content = cf.read_text()
            fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                fm = yaml.safe_load(fm_match.group(1)) or {}
                title = fm.get("title", cf.stem)
                desc = fm.get("description", "")
                lines.append(f"* [{title}]({cf.name}) - {desc}" if desc else f"* [{title}]({cf.name})")
            else:
                lines.append(f"* [{cf.stem}]({cf.name})")
        except Exception:
            lines.append(f"* [{cf.stem}]({cf.name})")

    return "\n".join(lines) + "\n"


def migrate_knowledgebase(input_dir: Path, output_dir: Path, dry_run: bool = False):
    """Migrate all legacy YAML entries to OKF markdown."""
    if not input_dir.is_dir():
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        return False

    converted = 0
    errors = 0
    skipped = 0

    # Walk through input directory
    for yaml_file in sorted(input_dir.rglob("*.yaml")):
        rel_path = yaml_file.relative_to(input_dir)
        try:
            content = yaml_file.read_text()
            fm, body = parse_legacy_yaml(content)

            if fm is None:
                print(f"  ⚠  [{rel_path}] Could not parse YAML frontmatter")
                skipped += 1
                continue

            # Determine output path
            okf_type = map_to_okf_type(fm)
            namespace = TYPE_TO_NAMESPACE.get(okf_type, "concepts")
            title = str(fm.get("title", fm.get("name", yaml_file.stem)))
            key = _make_key(title)

            out_subdir = output_dir / namespace
            out_path = out_subdir / f"{key}.md"

            if dry_run:
                print(f"  🔍 [{rel_path}] → {out_path.relative_to(output_dir)} (type: {okf_type})")
                converted += 1
                continue

            # Build and write OKF document
            okf_content = build_okf_document(fm, body, str(yaml_file))
            out_subdir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(okf_content)

            print(f"  ✓ [{rel_path}] → {out_path.relative_to(output_dir)}")
            converted += 1

        except Exception as e:
            print(f"  ✗ [{rel_path}] Error: {e}", file=sys.stderr)
            errors += 1

    # Generate index.md files
    if not dry_run and converted > 0:
        for subdir in sorted(output_dir.iterdir()):
            if subdir.is_dir():
                index_content = generate_index_file(subdir)
                if index_content:
                    index_path = subdir / "index.md"
                    index_path.write_text(index_content)
                    print(f"  📋 Generated {index_path.relative_to(output_dir)}")

        # Generate root index.md
        root_index = _generate_root_index(output_dir)
        if root_index:
            (output_dir / "index.md").write_text(root_index)
            print(f"  📋 Generated root index.md")

    print(f"\n{'Dry run' if dry_run else 'Migration'} complete:")
    print(f"  Converted: {converted}")
    print(f"  Errors:    {errors}")
    print(f"  Skipped:   {skipped}")

    return errors == 0


def _make_key(title: str) -> str:
    """Convert a title to a URL-safe key."""
    key = title.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "-", key)
    key = key.strip("-")
    return key[:100] or "untitled"


def _generate_root_index(output_dir: Path) -> str:
    """Generate root index.md for the bundle."""
    lines = [
        "---",
        "okf_version: \"0.1\"",
        "---",
        "",
        "# Knowledge Base",
        "",
        "This is an Open Knowledge Format (OKF) v0.1 bundle.",
        "",
    ]

    for subdir in sorted(output_dir.iterdir()):
        if not subdir.is_dir():
            continue
        md_files = list(subdir.glob("*.md"))
        concept_files = [f for f in md_files if f.name not in RESERVED_FILENAMES]
        if not concept_files:
            continue

        dir_name = subdir.name.capitalize()
        lines.append(f"## {dir_name}")
        lines.append("")

        for cf in concept_files:
            try:
                content = cf.read_text()
                fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                if fm_match:
                    fm = yaml.safe_load(fm_match.group(1)) or {}
                    title = fm.get("title", cf.stem)
                    desc = fm.get("description", "")
                    lines.append(f"* [{title}]({subdir.name}/{cf.name}) - {desc}" if desc else f"* [{title}]({subdir.name}/{cf.name})")
                else:
                    lines.append(f"* [{cf.stem}]({subdir.name}/{cf.name})")
            except Exception:
                lines.append(f"* [{cf.stem}]({subdir.name}/{cf.name})")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Migrate legacy knowledgebase entries to OKF format"
    )
    parser.add_argument("--input-dir", "-i",
                        default="/project/knowledgebase",
                        help="Input directory with legacy YAML files")
    parser.add_argument("--output-dir", "-o",
                        default="/project/knowledgebase",
                        help="Output directory for OKF markdown files")
    parser.add_argument("--dry-run", "-n",
                        action="store_true",
                        help="Preview migration without writing files")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.is_dir():
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(f"Dry run: scanning {input_dir}...\n")

    success = migrate_knowledgebase(input_dir, output_dir, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
