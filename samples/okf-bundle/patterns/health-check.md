---
type: Pattern
title: Health Check Pattern
description: Standard health check endpoint pattern for all microservices using curl against /health.
tags: [monitoring, operations, pattern]
timestamp: 2026-02-20T14:00:00Z
---

# Description

Every microservice exposes a `/health` endpoint that returns service status. This is used by the container orchestrator and monitoring systems.

# Implementation

```python
from fastapi import FastAPI
from datetime import datetime

app = FastAPI()

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "my-service",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }
```

# Verification

```bash
curl -sf http://localhost:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'"
```

# Related

- See [FastAPI Stack](/decisions/fastapi-stack.md) for the framework decision
- See [Docker Compose Setup](/patterns/docker-compose.md) for container orchestration
