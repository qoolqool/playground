# Knowledge Base

This is an Open Knowledge Format (OKF) v0.1 bundle for the playground project.

## Decisions

Architecture decisions with rationale and alternatives.

* [FastAPI as Primary Web Framework](decisions/fastapi-stack.md) - All microservices will use FastAPI with Pydantic v2 for request validation and API documentation.

## Patterns

Implementation patterns and operational procedures.

* [Health Check Pattern](patterns/health-check.md) - Standard health check endpoint pattern for all microservices using curl against /health.
* [Docker Compose Setup](patterns/docker-compose.md) - Standard Docker Compose configuration for running microservices with shared networking and volume mounts.
