---
type: Decision
title: FastAPI as Primary Web Framework
description: All microservices will use FastAPI with Pydantic v2 for request validation and API documentation.
tags: [architecture, python, fastapi]
timestamp: 2026-01-15T10:30:00Z
status: accepted
---

# Context

The team needed a Python web framework for building microservices. The main candidates were FastAPI, Flask, and Django REST Framework.

# Decision

Use **FastAPI** with **Pydantic v2** for all new microservices. FastAPI provides:

- Automatic OpenAPI/Swagger documentation
- Pydantic-based request validation
- Async support out of the box
- Excellent performance (on par with Node.js/Go)

# Consequences

- All services use the same patterns, making cross-service work easier
- Pydantic models serve as both validation and documentation
- Need to keep FastAPI version in sync across services
- Team needs training on async Python patterns

# Alternatives Considered

- **Flask**: Too minimal, requires too many add-on libraries
- **Django REST Framework**: Too heavy for microservices, better for monolithic apps

# Citations

[1] [FastAPI documentation](https://fastapi.tiangolo.com/)
[2] [Pydantic v2 migration guide](https://docs.pydantic.dev/latest/migration/)
