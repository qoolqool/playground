#!/bin/bash

# Detect container runtime.
# Key cases:
#   - docker binary is real Docker   → use docker
#   - docker binary is podman wrapper → use podman  (podman-docker package)
#   - no docker, only podman         → use podman  (alias-only setups)
#   - neither found                  → default to docker (will error at runtime)
detect_container_cmd() {
    if command -v docker >/dev/null 2>&1; then
        # docker binary exists — is it real Docker or podman in disguise?
        if docker --version 2>/dev/null | grep -qi podman; then
            echo "podman"
        else
            echo "docker"
        fi
        return
    fi

    if command -v podman >/dev/null 2>&1; then
        echo "podman"
        return
    fi

    # Neither found — will fail later with a clear error
    echo "docker"
}

export CONTAINER_CMD="$(detect_container_cmd)"

# Set engine-specific env vars based on detected runtime
if [ "$CONTAINER_CMD" = "podman" ]; then
    export D_HOST="tcp://${PODMAN_VM_IP:-192.168.127.2}:2375"
    export DOCKER_SOCKET_PATH="/dev/null"
else
    export D_HOST="unix:///var/run/docker.sock"
    export DOCKER_SOCKET_PATH="/var/run/docker.sock"
fi