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

# --- Quickstart Prerequisite Check -----------------------------------------
# Called by start.sh with -q/--quickstart flag.
# Uses `type` (not `command -v`) to detect aliases like `alias docker=podman`.
# Usage: quickstart_check [--check-central-kb]
quickstart_check() {
    local CHECK_CENTRAL_KB=false
    [[ "$1" == "--check-central-kb" ]] && CHECK_CENTRAL_KB=true

    local ALL_PASSED=true
    local RUNTIME_CMD=""
    local RUNTIME_LABEL=""

    echo ""
    echo "═══════════════════════════════════════════════"
    echo "  Prerequisite Check"
    echo "═══════════════════════════════════════════════"

    # --- 1. Container runtime ---
    # Use `type` instead of `command -v` — `type` reports shell aliases.
    if type docker >/dev/null 2>&1; then
        local DOCKER_TYPE
        DOCKER_TYPE=$(type docker 2>&1)
        if [[ "$DOCKER_TYPE" == *"aliased"* ]]; then
            # e.g., "docker is aliased to podman"
            local ALIAS_TARGET
            ALIAS_TARGET=$(echo "$DOCKER_TYPE" | sed -n "s/.*\`\(.*\)'.*/\1/p")
            RUNTIME_CMD="podman"
            RUNTIME_LABEL="podman"
            echo "  ⚠  docker is aliased to ${ALIAS_TARGET:-podman}"
            echo "     → Using podman as container runtime"
        elif docker --version 2>/dev/null | grep -qi podman; then
            RUNTIME_CMD="podman"
            RUNTIME_LABEL="podman (podman-docker)"
        else
            RUNTIME_CMD="docker"
            RUNTIME_LABEL="docker"
        fi
    elif type podman >/dev/null 2>&1; then
        RUNTIME_CMD="podman"
        RUNTIME_LABEL="podman"
    else
        echo "  ✗  Neither docker nor podman found in PATH"
        echo "     → Install Docker: https://docs.docker.com/engine/install/"
        echo "     → Or Podman: https://podman.io/docs/installation"
        ALL_PASSED=false
    fi

    # --- 2. Validate runtime is alive ---
    if [ -n "$RUNTIME_CMD" ]; then
        echo "  ✓  Container runtime: $RUNTIME_LABEL"
        if $RUNTIME_CMD info >/dev/null 2>&1; then
            echo "  ✓  $RUNTIME_CMD daemon is running"
        else
            echo "  ✗  $RUNTIME_CMD daemon is NOT running or not accessible"
            if [ "$RUNTIME_CMD" = "podman" ]; then
                echo "     → Start Podman machine: podman machine start"
                echo "     → Or check Podman socket: podman system service --time=0"
            else
                echo "     → Start Docker daemon: systemctl start docker (Linux)"
                echo "     → Or open Docker Desktop (macOS/Windows)"
            fi
            ALL_PASSED=false
        fi
    fi

    # --- 3. Podman on macOS: check PODMAN_VM_IP ---
    if [ "$RUNTIME_CMD" = "podman" ] && [ "$(uname)" = "Darwin" ]; then
        if [ -n "$PODMAN_VM_IP" ]; then
            echo "  ✓  PODMAN_VM_IP is set: $PODMAN_VM_IP"
            if ping -c1 -W2 "$PODMAN_VM_IP" >/dev/null 2>&1; then
                echo "  ✓  Podman VM is reachable at $PODMAN_VM_IP"
            else
                echo "  ✗  Cannot reach Podman VM at $PODMAN_VM_IP"
                echo "     → Verify VM is running: podman machine list"
                echo "     → Check PODMAN_VM_IP is correct (from: podman system connection list)"
                ALL_PASSED=false
            fi
        else
            echo "  ✗  PODMAN_VM_IP is not set"
            echo "     → Find your Podman VM IP: podman system connection list"
            echo "     → Set it: export PODMAN_VM_IP=<your-vm-ip>"
            echo "     → Or add to ~/.zshrc / ~/.bashrc for persistence"
            ALL_PASSED=false
        fi
    fi

    # --- 4. Git ---
    if command -v git >/dev/null 2>&1; then
        echo "  ✓  Git is installed"
    else
        echo "  ✗  Git is not installed"
        echo "     → Install Git: https://git-scm.com/downloads"
        ALL_PASSED=false
    fi

    # --- 5. Submodules (warning only) ---
    if [ -f .gitmodules ]; then
        if git submodule status 2>/dev/null | grep -q '^-'; then
            echo "  ⚠  Some git submodules are not initialized"
            echo "     → They will be initialized automatically during build"
        else
            echo "  ✓  Git submodules are initialized"
        fi
    fi

    # --- 6. Central KB (warning only, only when -k) ---
    if [ "$CHECK_CENTRAL_KB" = true ]; then
        if command -v curl >/dev/null 2>&1 && curl -sf http://localhost:9000/health >/dev/null 2>&1; then
            echo "  ✓  Central KB is reachable (port 9000)"
        else
            echo "  ⚠  Central KB is not reachable at localhost:9000"
            echo "     → It will be started by the --setup-central-kb flow"
        fi
    fi

    # --- Summary ---
    echo "───────────────────────────────────────────────"
    if [ "$ALL_PASSED" = true ]; then
        echo "  ✓ All prerequisite checks passed. Ready to proceed."
        echo "───────────────────────────────────────────────"
        echo ""
        return 0
    else
        echo "  ✗ Some checks failed. Fix the issues above, then re-run."
        echo "───────────────────────────────────────────────"
        echo ""
        return 1
    fi
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
