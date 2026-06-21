---
type: Pattern
title: Docker Compose Setup
description: Standard Docker Compose configuration for running microservices with shared networking and volume mounts.
tags: [docker, infrastructure, devops]
timestamp: 2026-03-01T09:00:00Z
---

# Description

All microservices use Docker Compose for local development and testing. The setup includes shared networking, volume mounts for hot-reload, and environment variable management.

# Configuration

```yaml
version: "3.8"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - .:/app
    environment:
      - DATABASE_URL=postgresql://db:5432/myapp
    depends_on:
      - db

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: myapp
      POSTGRES_PASSWORD: devpassword
```

# Related

- See [Health Check](/patterns/health-check.md) for service health monitoring
