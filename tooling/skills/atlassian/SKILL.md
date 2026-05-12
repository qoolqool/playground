---
name: atlassian
description: >
  Search, read, and create Jira issues and Confluence pages via the Atlassian CLI
  wrapper. Requires Atlassian credentials configured once via `atlassian configure`.
  Use when the user asks about tickets, issues, sprints, or Confluence documentation.
---

# Atlassian (Jira + Confluence)

## First-time Setup

Credentials are prompted once and stored in `~/.secrets/mcp-atlassian.json` (chmod 600):

```bash
python3 /project/tooling/scripts/atlassian-cli.py configure
```

You only need to configure services you use. Leave a service blank to skip it.

## Usage

### Jira

```bash
# Search issues with JQL
python3 /project/tooling/scripts/atlassian-cli.py jira search "project=PROJ AND status!=Done"

# Get issue details
python3 /project/tooling/scripts/atlassian-cli.py jira get PROJ-123

# Create an issue
python3 /project/tooling/scripts/atlassian-cli.py jira create PROJ "Fix login bug" "Users cannot log in with SSO"
```

### Confluence

```bash
# Search pages with CQL
python3 /project/tooling/scripts/atlassian-cli.py confluence search "space=DEV AND type=page"

# Get page content
python3 /project/tooling/scripts/atlassian-cli.py confluence get 123456
```

## Credential Security

- Credentials are stored in `~/.secrets/mcp-atlassian.json` with permissions `600` (owner read/write only)
- The file is never in the project directory or git history
- On container rebuild, credentials are lost and must be re-configured
- API tokens can be revoked at any time from https://id.atlassian.com/manage-profile/security/api-tokens

## Agent Guidelines

- Always run `atlassian configure` first if no credentials file exists
- Prefer `jira search` with specific JQL over broad queries
- Use `jira get` to see full issue details (description, comments) before making changes
- For Confluence, prefer `confluence search` before `confluence get` to find the right page ID
- Results are limited to 20 items per query
