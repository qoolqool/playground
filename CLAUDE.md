# Docker Playground

Autonomous Docker development.

## Rules
- Fix errors autonomously
- Retry: 2s, 5s, 10s, 15s (max 5)
- Document in DEBUG_STATE.md

## Workflow
1. docker compose build
2. docker compose up -d
3. Validate: docker ps, logs, curl
4. Stabilize
