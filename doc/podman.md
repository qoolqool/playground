# Podman Setup

The playground supports both Docker and Podman. Podman is auto-detected by
`setenv.sh`. On Linux, Podman works out of the box with a rootful socket.
On macOS, a Podman VM with TCP API is required.

## macOS Setup

### 1. Install Podman

```bash
brew install podman
```

### 2. Create and start a rootful VM

```bash
podman machine init --rootful
podman machine start
```

### 3. Find your VM IP

```bash
podman system connection list
```

Look for the `IdentityFile` path and SSH URI — the VM IP is in the URI
(e.g., `ssh://core@192.168.127.2:...` → IP is `192.168.127.2`).

### 4. Set the environment variable

```bash
export PODMAN_VM_IP=192.168.127.2
./start.sh
```

Add the export to your shell profile (`~/.zshrc`, `~/.bashrc`) so it persists.

## Linux Setup

```bash
# Install podman-docker for docker CLI compatibility
sudo apt install podman-docker   # Debian/Ubuntu
sudo dnf install podman-docker   # Fedora

# Or use podman directly (auto-detected)
./start.sh
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ping: cannot resolve PODMAN_VM_IP` | Variable not set → `export PODMAN_VM_IP=<ip>` |
| `Cannot connect to Podman` | VM not started → `podman machine start` |
| `Error: rootless connection` | VM not rootful → `podman machine set --rootful` then restart |
| Port forwarding not working | Use the 3-layer port-forwarding script (not direct `-p` flags) |

## Quickstart Check

Use `./start.sh -q` to validate your Podman setup before building:
- Checks `PODMAN_VM_IP` is set (macOS)
- Pings the VM IP to verify reachability
- Verifies `podman info` returns successfully
