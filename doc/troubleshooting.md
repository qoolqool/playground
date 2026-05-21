# Troubleshooting

## Container Won't Start

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `docker: command not found` | Docker/Podman not installed | Install Docker or Podman |
| `Cannot connect to the Docker daemon` | Daemon not running | Start Docker Desktop or `systemctl start docker` |
| `Error response from daemon: ...` | Permission denied | Add user to `docker` group: `sudo usermod -aG docker $USER` |
| Container exits immediately | Entrypoint error | Check logs: `docker compose logs` |

## Podman Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ping: cannot resolve PODMAN_VM_IP` | Variable not set | `export PODMAN_VM_IP=<ip>` from `podman system connection list` |
| `Cannot connect to Podman` | VM not started | `podman machine start` |
| `Error: rootless connection` | VM not rootful | `podman machine set --rootful` then restart |
| Port forwarding not working | Podman doesn't propagate `-p` | Use the 3-layer port-forwarding script |

## Shell Quoting in Docker Exec

When running commands inside a DinD environment:

```bash
# ✅ CORRECT: single-quote the Python block
docker exec dind docker exec test-runner python3 -c '
import urllib.request
print(urllib.request.urlopen("http://service:8000/health").read())
'

# ❌ WRONG: double quotes cause host shell expansion of $ and .get()
docker exec dind docker exec test-runner python3 -c "
print(requests.get('http://service:8000/health').json())
"
```

**Rule:** Single-quote the Python block. Pass env vars with `-e`. Avoid
double quotes that trigger host shell expansion.

## Network Isolation

Settlement-net services are **unreachable** from internet-net services by design.
This is correct network isolation, not a bug.
- Cross-segment traffic must go through a multi-homed gateway/ACL service
- The test-runner container spans all networks for integration testing

## Knowledge Pipeline

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `OperationalError: unable to open database file` | `.agent/` dir doesn't exist | Run any KB script once (auto-creates the dir) |
| `database is locked` errors | Concurrent SQLite connections | Use separate DB files for independent concerns |
| No results from search-kb | Embeddings not indexed | Run `distill-and-index` first |

## Still Stuck?

Check the [AGENT.md](../AGENT.md) roadmap, or
[open an issue](https://github.com/qoolqool/playground/issues) on GitHub.
