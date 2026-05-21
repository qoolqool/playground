#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Source dynamic env config (auto-detects Docker vs Podman)
if [ -f ./setenv.sh ]; then
  source ./setenv.sh
fi

# Container runtime command (set by setenv.sh, defaults to docker)
DOCKER="${CONTAINER_CMD:-docker}"

# Parse arguments
FORCE_REBUILD=false
PULL_IMAGE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--force)
            FORCE_REBUILD=true
            shift
            ;;
        -k|--setup-central-kb)
            SETUP_CENTRAL_KB=true
            shift
            ;;
        -q|--quickstart)
            QUICKSTART=true
            shift
            ;;
        -p|--pull)
            PULL_IMAGE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./start.sh [-f|--force] [-p|--pull] [-k|--setup-central-kb] [-q|--quickstart]"
            echo "  -f, --force              Force rebuild and recreate container"
            echo "  -k, --setup-central-kb   Start central-kb services before playground"
            echo "  -p, --pull              Pull prebuilt image from GHCR instead of building locally"
            echo "  -q, --quickstart           Check prerequisites before building"
            exit 1
            ;;
    esac
done

# --- Quickstart Check ---
# Run prerequisite validation before anything else.
# If checks pass, proceed. If they fail, print fix instructions and exit.
if [ "$QUICKSTART" = true ]; then
    # Re-source setenv.sh to ensure quickstart_check is available
    if [ -f ./setenv.sh ]; then
        source ./setenv.sh
    fi

    CENTRAL_KB_ARG=""
    [ "$SETUP_CENTRAL_KB" = true ] && CENTRAL_KB_ARG="--check-central-kb"

    if quickstart_check $CENTRAL_KB_ARG; then
        echo ""
        echo "Quickstart check passed. Proceeding..."
    else
        echo ""
        echo "Quickstart check failed. Fix issues above and re-run."
        exit 1
    fi
fi

# --- Central KB Setup ---
# If -k/--setup-central-kb flag is set, detect or start central-kb services
# before proceeding to playground container lifecycle.
if [ "$SETUP_CENTRAL_KB" = true ]; then
    echo "=== Central KB Setup ==="
    echo "Checking if central-kb is already running..."

    CENTRAL_KB_RUNNING=false
    if command -v curl >/dev/null 2>&1; then
        if curl -sf http://localhost:9000/health >/dev/null 2>&1 && \
           curl -sf http://localhost:9001/health >/dev/null 2>&1; then
            CENTRAL_KB_RUNNING=true
        fi
    fi

    if [ "$CENTRAL_KB_RUNNING" = true ]; then
        echo "central-kb is already running (API: :9000, embed: :9001)"
        touch .central-kb-ready
        echo "Created .central-kb-ready marker"
    else
        # Ensure the central-kb submodule is initialized if it exists as a submodule
        if [ -f .gitmodules ]; then
            git submodule update --init tooling/central-kb 2>/dev/null || true
        fi

        # Find central-kb source directory
        CENTRAL_KB_DIR=""
        if [ -f "tooling/central-kb/docker-compose.yml" ]; then
            CENTRAL_KB_DIR="tooling/central-kb"
            echo "Found central-kb at $CENTRAL_KB_DIR/ (submodule)"
        elif [ -f "../central-kb/docker-compose.yml" ]; then
            CENTRAL_KB_DIR="../central-kb"
            echo "Found central-kb at $CENTRAL_KB_DIR/ (sibling)"
        else
            echo "Error: central-kb not found."
            echo "  Clone to ../central-kb/:  git clone https://github.com/qoolqool/central-kb ../central-kb"
            echo "  Or init submodule:        git submodule update --init tooling/central-kb"
            exit 1
        fi

        # Start central-kb services (explicit service names only)
        echo "Starting central-kb services (embed-server, tooling-central)..."
        (cd "$CENTRAL_KB_DIR" && $DOCKER compose up -d embed-server tooling-central)

        # Wait for embed-server health (longer due to PyTorch model download)
        echo "Waiting for embed-server (port 9001)..."
        EMBED_READY=false
        for i in $(seq 1 20); do
            if curl -sf http://localhost:9001/health >/dev/null 2>&1; then
                EMBED_READY=true
                break
            fi
            echo "  (attempt $i/20 — embed-server still starting, model may be downloading...)"
            sleep 3
        done

        if [ "$EMBED_READY" != true ]; then
            echo "Error: embed-server did not become healthy within 60s"
            echo "Check logs: $DOCKER compose -f $CENTRAL_KB_DIR/docker-compose.yml logs embed-server"
            exit 1
        fi
        echo "embed-server is healthy"

        # Wait for central-kb API (depends on embed-server being healthy)
        echo "Waiting for central-kb API (port 9000)..."
        KB_READY=false
        for i in $(seq 1 10); do
            if curl -sf http://localhost:9000/health >/dev/null 2>&1; then
                KB_READY=true
                break
            fi
            echo "  (attempt $i/10 — central-kb still starting...)"
            sleep 3
        done

        if [ "$KB_READY" != true ]; then
            echo "Error: central-kb API did not become healthy within 30s"
            echo "Check logs: $DOCKER compose -f $CENTRAL_KB_DIR/docker-compose.yml logs tooling-central"
            exit 1
        fi
        echo "central-kb API is healthy"

        # Create readiness marker
        touch .central-kb-ready
        echo "Created .central-kb-ready marker"
        echo "central-kb is ready (API: :9000, embed: :9001)"
    fi

    echo "=== Central KB setup complete, proceeding to playground ==="
fi

# Container name is stored in .container_name file (deterministic per playground)
CONTAINER_FILE=".container_name"

# Function to find available container name
find_available_name() {
    local base="tooling"
    local name="$base"
    local counter=2
    while $DOCKER ps -a --format '{{.Names}}' | grep -q "^${name}$"; do
        name="${base}-${counter}"
        counter=$((counter + 1))
    done
    echo "$name"
}

# --- Pull prebuilt image or build locally ---
pull_or_build() {
    if [ "$PULL_IMAGE" = true ]; then
        echo "Pulling prebuilt image from GHCR..."
        if $DOCKER pull ghcr.io/qoolqool/playground-tooling:latest; then
            # Tag as local build name so docker-compose finds it
            $DOCKER tag ghcr.io/qoolqool/playground-tooling:latest playground-tooling:latest
            echo "Using prebuilt image (skipped local build)."
        else
            echo ""
            echo "Error: Failed to pull prebuilt image from ghcr.io."
            echo "  This could mean:"
            echo "    1. No image has been built yet for this branch"
            echo "    2. Network cannot reach ghcr.io"
            echo "    3. Rate limit exceeded (anonymous pulls: 100/6h per IP)"
            echo ""
            echo "  To build locally instead, run without --pull:  ./start.sh"
            echo "  To authenticate for higher rate limits: docker login ghcr.io"
            exit 1
        fi
    else
        echo "Building tooling container..."
        $DOCKER compose build
    fi
}

# Force rebuild - remove existing container
if [ "$FORCE_REBUILD" = true ]; then
    if [ -f "$CONTAINER_FILE" ]; then
        CONTAINER_NAME=$(cat "$CONTAINER_FILE")
        echo "Force rebuild - removing container '$CONTAINER_NAME'..."
        $DOCKER rm -f "$CONTAINER_NAME" 2>/dev/null || true
    fi
    rm -f "$CONTAINER_FILE"

    # Ensure submodules are initialized before building
    if [ -f .gitmodules ]; then
      echo "Initializing git submodules..."
      git submodule update --init --recursive
    fi

    echo "Force rebuild - rebuilding image..."
    pull_or_build

    # Find available name
    CONTAINER_NAME=$(find_available_name)
    echo "Using container name: $CONTAINER_NAME"

    cat > docker-compose.override.yml << OVERRIDE_EOF
services:
  tooling:
    container_name: $CONTAINER_NAME
OVERRIDE_EOF

    echo ""
    echo "Creating container..."
    $DOCKER compose up -d
    echo "$CONTAINER_NAME" > "$CONTAINER_FILE"
    rm -f docker-compose.override.yml
    echo ""
    echo "Entering container (type 'exit' to leave)..."
    echo ""
    $DOCKER exec -it "$CONTAINER_NAME" bash
    exit 0
fi

if [ -f "$CONTAINER_FILE" ]; then
    # This playground has an assigned container
    CONTAINER_NAME=$(cat "$CONTAINER_FILE")

    if $DOCKER ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Container '$CONTAINER_NAME' is running."
    elif $DOCKER ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Container '$CONTAINER_NAME' exists but is stopped. Starting..."
        $DOCKER start "$CONTAINER_NAME"
    else
        echo "Container '$CONTAINER_NAME' was removed. Creating new one..."
        rm -f "$CONTAINER_FILE"
        # Fall through to first-run logic
    fi

    if [ -f "$CONTAINER_FILE" ]; then
        echo "Entering container (type 'exit' to leave)..."
        echo ""
        $DOCKER exec -it "$CONTAINER_NAME" bash
        exit 0
    fi
fi

# First run - ensure submodules are initialized before building
if [ -f .gitmodules ]; then
  echo "Initializing git submodules..."
  git submodule update --init --recursive
fi

# Then build and create container
pull_or_build

# Find available container name (check before creating)
CONTAINER_NAME=$(find_available_name)
echo "Using container name: $CONTAINER_NAME"

# Use override to set container name
cat > docker-compose.override.yml << OVERRIDE_EOF
services:
  tooling:
    container_name: $CONTAINER_NAME
OVERRIDE_EOF

echo ""
echo "Starting container..."
$DOCKER compose up -d

# Store container name for future runs
echo "$CONTAINER_NAME" > "$CONTAINER_FILE"
rm -f docker-compose.override.yml

echo ""
echo "Entering container (type 'exit' to leave)..."
echo ""
$DOCKER exec -it "$CONTAINER_NAME" bash
