---
name: deploy-app
description: Deploy a git repository by analyzing documentation (README, INSTALL, howto) and generating a containerized environment in /project/app.
command: deploy-app
---

## Purpose
Automate the containerization and deployment of a git repository by discovering environment requirements and generating deployment artifacts.

## Execution Logic
1. **Discovery Phase**:
   - Fetch `README.md`, `INSTALL.md`, and `howto.md` sequentially.
   - Identify runtime versions (e.g., Python, Node.js), dependency files, and required external services (DBs, Caches).
2. **Environment Preparation**:
   - Create a target directory at `/project/app`.
3. **Artifact Generation**:
   - Generate a `Dockerfile` with the correct base image and `WORKDIR /project/app`.
   - Generate a `docker-compose.yml` including the application and any discovered external components with minimal resource limits.
   - Generate a detailed `DEPLOY.md` guide covering prerequisites, environment variables, volume mounts, and verification steps.

## Output
- `/project/app/Dockerfile`
- `/project/app/docker-compose.yml`
- `/project/app/DEPLOY.md`
