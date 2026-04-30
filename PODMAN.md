# Podman Setup and Networking Configuration

This guide covers setting up Podman on macOS to work with this Docker Playground. Podman runs containers inside a Linux VM, so you need to configure networking and the REST API for the container to communicate with the host and the Docker socket.

## 1. Install Podman

```bash
brew install podman
```

Verify the installation:

```bash
podman version
```

## 2. Create and Configure the VM

Create the Podman VM and set it to **rootful** mode — required for Docker socket forwarding and host networking to work correctly.

```bash
# Create the VM
podman machine init

# Set rootful mode (required)
podman machine set --rootful

# Verify rootful is enabled
podman machine inspect --format '{{.Rootful}}'
# Should print: true
```

## 3. Start the VM

```bash
podman machine start
```

Check the VM status:

```bash
podman machine list
```

The VM must show **Running** before proceeding.

## 4. Expose the Podman REST API

You need a systemd service inside the VM to expose the Podman REST API on TCP port `2375`.

**Setup:**

```bash
podman machine ssh -- "sudo tee /etc/systemd/system/podman-tcp.service > /dev/null << 'EOF'
[Unit]
Description=Podman REST API (TCP 2375)
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/podman system service --time=0 tcp:0.0.0.0:2375
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now podman-tcp.service"
```

**Verification:**

```bash
podman machine ssh "ss -tlnp | grep 2375"
```

You should see output showing the service listening on port `2375`.

> **Note:** This service must be re-setup if you recreate the VM (`podman machine init` again).

## 5. Find the Podman VM IP

The `docker-compose.yml` uses `${PODMAN_VM_IP:-192.168.127.2}`. Find the actual IP:

```bash
export PODMAN_VM_IP=$(podman machine ssh "ip addr show eth0 | grep 'inet ' | awk '{print \$2}' | cut -d '/' -f1")
```

Verify:

```bash
echo $PODMAN_VM_IP
```

If the auto-detected IP differs from the default `192.168.127.2`, the env var will override it. You can also set it manually:

```bash
export PODMAN_VM_IP=192.168.127.2
```

## 6. Set `DOCKER_HOST` (Host Shell)

Set this environment variable so `docker compose` commands on your host route through the Podman VM:

```bash
export DOCKER_HOST=tcp://${PODMAN_VM_IP}:2375
```

Add this to your shell profile (`~/.zshrc` or `~/.bashrc`) to persist it:

```bash
echo 'export DOCKER_HOST=tcp://${PODMAN_VM_IP:-192.168.127.2}:2375' >> ~/.zshrc
```

## 7. Environment Configuration (docker-compose.yml)

With `PODMAN_VM_IP` set, the `docker-compose.yml` in this repo can forward the Docker socket through the Podman VM:

```yaml
tooling:
  build:
    context: ./tooling
    dockerfile: Dockerfile
  container_name: poc-tooling
  hostname: tooling
  environment:
    - DOCKER_HOST=tcp://${PODMAN_VM_IP:-192.168.127.2}:2375
```

The default fallback IP (`192.168.127.2`) works for most default Podman VM configurations on macOS.

## 8. Podman Machine Lifecycle

```bash
# Stop the VM
podman machine stop

# List all VMs and their status
podman machine list

# Remove the VM (irreversible — recreates from scratch)
podman machine rm
```

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker compose` commands hang or timeout | VM not started or `DOCKER_HOST` not set | Run `podman machine start` and verify `DOCKER_HOST` |
| `Error: rootless networking is not supported` | VM not in rootful mode | `podman machine set --rootful`, then restart |
| Connection refused on port 2375 | REST API service not running | Re-run the systemd setup in step 4 |
| Wrong IP detected after VM restart | VM IP can change on restart | Re-run the IP detection command in step 5 |
| `docker ps` shows no containers when there should be some | Docker contexts or wrong socket | Check `DOCKER_HOST` is set to the Podman VM IP, not a local Docker socket |
