#!/bin/bash

if command -v podman >/dev/null 2>&1; then
    # Podman setup
    export D_HOST="tcp://${PODMAN_VM_IP:-192.168.127.2}:2375"
    # Podman usually doesn't need the socket mount if you're using TCP
    export DOCKER_SOCKET_PATH="/dev/null" 
else
    # Docker setup
    export D_HOST="unix:///var/run/docker.sock"
    export DOCKER_SOCKET_PATH="/var/run/docker.sock"
fi
