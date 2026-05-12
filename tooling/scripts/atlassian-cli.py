#!/usr/bin/env python3
"""
Atlassian CLI wrapper for Jira and Confluence.
Stores credentials in ~/.secrets/mcp-atlassian.json (chmod 600).
Prompts on first use, reads from file afterwards.

Usage:
  ./atlassian.py configure                    # Set up credentials
  ./atlassian.py jira search  "project=PROJ"  # JQL search
  ./atlassian.py jira get     PROJ-123        # Get issue
  ./atlassian.py jira create  PROJ "Summary" "Description"
  ./atlassian.py confluence search "space=DEV"  # CQL search
  ./atlassian.py confluence get <page-id>       # Get page
"""

import json
import os
import sys
from pathlib import Path

SECRETS_DIR = Path.home() / ".secrets"
SECRETS_FILE = SECRETS_DIR / "mcp-atlassian.json"


def load_credentials() -> dict:
    if not SECRETS_FILE.exists():
        print("No Atlassian credentials found. Run: atlassian configure", file=sys.stderr)
        sys.exit(1)
    data = json.loads(SECRETS_FILE.read_text())
    # Basic validation
    required = []
    for svc in ("jira", "confluence"):
        if data.get(f"{svc}_url"):
            required.extend([f"{svc}_url", f"{svc}_username", f"{svc}_api_token"])
    if not required:
        print("Credentials file is empty or invalid. Run: atlassian configure", file=sys.stderr)
        sys.exit(1)
    return data


def save_credentials(creds: dict):
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS_FILE.write_text(json.dumps(creds, indent=2))
    SECRETS_FILE.chmod(0o600)
    print(f"Credentials saved to {SECRETS_FILE} (chmod 600)")


def cmd_configure():
    """Prompt user for credentials and save them."""
    print("=== Atlassian Credential Setup ===\n")
    print("Leave fields blank for services you don't use.\n")

    creds = {}

    for svc in ["jira", "confluence"]:
        label = "Jira" if svc == "jira" else "Confluence"
        url = input(f"{label} URL (e.g. https://your-company.atlassian.net) [{label}]: ").strip()
        if not url:
            continue
        creds[f"{svc}_url"] = url
        creds[f"{svc}_username"] = input(f"{label} email: ").strip()
        creds[f"{svc}_api_token"] = input(f"{label} API token (from id.atlassian.com/manage-profile/security/api-tokens): ").strip()
        print()

    if not creds:
        print("No services configured. Nothing saved.")
        return

    save_credentials(creds)
    print("\nDone! You can now use atlassian jira/confluence commands.")


def get_jira(creds: dict):
    from atlassian import Jira
    return Jira(
        url=creds.get("jira_url", ""),
        username=creds.get("jira_username"),
        password=creds.get("jira_api_token"),
        cloud=True,
    )


def get_confluence(creds: dict):
    from atlassian import Confluence
    return Confluence(
        url=creds.get("confluence_url", ""),
        username=creds.get("confluence_username"),
        password=creds.get("confluence_api_token"),
        cloud=True,
    )


def cmd_jira_search(args):
    creds = load_credentials()
    jira = get_jira(creds)
    jql = " ".join(args)
    results = jira.jql(jql)
    issues = results.get("issues", [])
    print(f"Found {len(issues)} issues:\n")
    for issue in issues[:20]:
        key = issue["key"]
        summary = issue["fields"].get("summary", "No summary")
        status = issue["fields"].get("status", {}).get("name", "?")
        assignee = issue["fields"].get("assignee")
        assignee_name = assignee.get("displayName", "Unassigned") if assignee else "Unassigned"
        print(f"  [{status:15s}] {key:12s} {summary}")
        print(f"  {'':18s} Assignee: {assignee_name}")
        print()


def cmd_jira_get(args):
    creds = load_credentials()
    jira = get_jira(creds)
    issue_key = args[0]
    issue = jira.get_issue(issue_key)
    fields = issue["fields"]
    print(f"{'Key:':12s} {issue['key']}")
    print(f"{'Summary:':12s} {fields.get('summary', 'N/A')}")
    print(f"{'Status:':12s} {fields.get('status', {}).get('name', 'N/A')}")
    print(f"{'Type:':12s} {fields.get('issuetype', {}).get('name', 'N/A')}")
    print(f"{'Priority:':12s} {fields.get('priority', {}).get('name', 'N/A')}")
    print(f"{'Assignee:':12s} {fields.get('assignee', {}).get('displayName', 'Unassigned')}")
    print(f"{'Reporter:':12s} {fields.get('reporter', {}).get('displayName', 'N/A')}")
    print(f"{'Created:':12s} {fields.get('created', 'N/A')}")
    print(f"{'Updated:':12s} {fields.get('updated', 'N/A')}")
    desc = fields.get("description")
    if desc:
        # Simple text extraction from Atlassian document format
        if isinstance(desc, str):
            print(f"\nDescription:\n{desc[:2000]}")
        elif isinstance(desc, dict):
            text_parts = []
            def extract_text(node):
                if isinstance(node, dict):
                    if node.get("type") == "text" and "text" in node:
                        text_parts.append(node["text"])
                    for v in node.values():
                        if isinstance(v, (dict, list)):
                            extract_text(v)
                elif isinstance(node, list):
                    for item in node:
                        extract_text(item)
            extract_text(desc.get("content", []))
            print(f"\nDescription:\n{''.join(text_parts)[:2000]}")


def cmd_jira_create(args):
    creds = load_credentials()
    jira = get_jira(creds)
    project = args[0]
    summary = args[1]
    description = " ".join(args[2:]) if len(args) > 2 else ""
    issue = jira.create_issue(project=project, summary=summary, description=description)
    print(f"Created: {issue.get('key', '?')}")


def cmd_confluence_search(args):
    creds = load_credentials()
    confluence = get_confluence(creds)
    cql = " ".join(args)
    results = confluence.cql(cql, limit=20)
    pages = results.get("results", [])
    print(f"Found {len(pages)} pages:\n")
    for page in pages[:20]:
        content = page.get("content", {}) or {}
        title = page.get("title", content.get("title", "No title"))
        page_id = content.get("id", "?")
        # Extract space key from _expandable.space path (e.g. "/rest/api/space/OF")
        expandable = content.get("_expandable", {}) or {}
        space_path = expandable.get("space", "")
        space = space_path.split("/")[-1] if space_path else "?"
        print(f"  [{space:12s}] {title}")
        print(f"  {'':14s} ID: {page_id}")
        print()


def cmd_confluence_get(args):
    creds = load_credentials()
    confluence = get_confluence(creds)
    page_id = args[0]
    page = confluence.get_page_by_id(page_id, expand="body.storage,version")
    print(f"{'Title:':12s} {page.get('title', 'N/A')}")
    print(f"{'Space:':12s} {page.get('space', {}).get('key', 'N/A')}")
    print(f"{'Version:':12s} {page.get('version', {}).get('number', 'N/A')}")
    print(f"{'Created:':12s} {page.get('createdDate', 'N/A')}")
    body = page.get("body", {}).get("storage", {}).get("value", "")
    if body:
        # Strip HTML tags for readability
        import re
        text = re.sub(r"<[^>]+>", "", body)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        print(f"\nContent:\n{text[:3000]}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "configure": cmd_configure,
        "jira": {
            "search": cmd_jira_search,
            "get": cmd_jira_get,
            "create": cmd_jira_create,
        },
        "confluence": {
            "search": cmd_confluence_search,
            "get": cmd_confluence_get,
        },
    }

    if command == "configure":
        cmd_configure()
    elif command in ("jira", "confluence"):
        if not args:
            print(f"Usage: atlassian {command} <subcommand> [args]")
            print(f"Subcommands: {', '.join(commands[command].keys())}")
            sys.exit(1)
        sub = args[0]
        sub_args = args[1:]
        if sub in commands[command]:
            commands[command][sub](sub_args)
        else:
            print(f"Unknown subcommand: {sub}")
            print(f"Available: {', '.join(commands[command].keys())}")
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        print(f"Available: configure, jira, confluence")
        sys.exit(1)


if __name__ == "__main__":
    main()
