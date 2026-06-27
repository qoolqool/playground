#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"

# ---------- host‑only guard ----------
# bootstrap.sh must run from the host, not inside a container.
if [ -z "${PLAYGROUND_ALLOW_INSIDE:-}" ]; then
    if [ -f /.dockerenv ] || grep -qE 'docker|kubepods|containerd|lxc' /proc/1/cgroup 2>/dev/null; then
        echo "Error: bootstrap.sh must be run from the host, not inside a container." >&2
        exit 1
    fi
fi

# ---------- Source dynamic env config (auto-detects Docker vs Podman) ----------
if [ -f ./setenv.sh ]; then
    source ./setenv.sh
fi
DOCKER="${CONTAINER_CMD:-docker}"

# ---------- configuration ----------
CONTAINER_NAME="playground-tooling"
PROJECTS_FILE="$SCRIPT_DIR/projects.yml"

# ---------- yq / awk YAML reader ----------
resolve_project_path() {
    local name="$1" file="$2" raw=""
    [ ! -f "$file" ] && return 1
    if command -v yq >/dev/null 2>&1; then
        raw=$(yq -r ".projects.\"${name}\" // \"\"" "$file" 2>/dev/null || true)
    else
        raw=$(awk -v key="^[[:space:]]*[\"']?${name}[\"']?[[:space:]]*:" '
            $0 ~ key {
                sub(/^[^:]*:[[:space:]]*/, "")
                sub(/[[:space:]]*#.*$/, "")
                gsub(/^["'\''"]|["'\''"]$/, "")
                print
                exit
            }' "$file")
    fi
    [ -z "$raw" ] || [ "$raw" = "null" ] && return 1
    raw="${raw/#\~/$HOME}"
    [ -d "$raw" ] && echo "$raw" && return 0
    return 1
}

# ---------- flag parsing ----------
FORCE_REBUILD=false
PULL_IMAGE=false
SETUP_CENTRAL_KB=false
QUICKSTART=false
STOP_REQUESTED=false
PROJECT_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--force) FORCE_REBUILD=true; shift ;;
        -k|--setup-central-kb) SETUP_CENTRAL_KB=true; shift ;;
        -p|--pull) PULL_IMAGE=true; shift ;;
        -q|--quickstart) QUICKSTART=true; shift ;;
        --stop) STOP_REQUESTED=true; shift ;;
        --project)
            [ -z "${2:-}" ] && { echo "Error: --project requires a name"; exit 1; }
            PROJECT_NAME="$2"; shift 2 ;;
        --project=*) PROJECT_NAME="${1#--project=}"; shift ;;
        *)
            echo "Usage: $0 [ -f | -p | -k | -q ] [ --project <name> ] [ --stop ]"
            echo ""
            echo "  -f, --force              Force rebuild and recreate container"
            echo "  -k, --setup-central-kb   Start central-kb services before playground"
            echo "  -p, --pull               Pull prebuilt image from GHCR instead of building locally"
            echo "  -q, --quickstart         Check prerequisites before building"
            echo "  --project <name>         Mount a project directory (from projects.yml) as /workspace"
            echo "  --stop                   Stop the container and optionally central-kb"
            exit 1
            ;;
    esac
done

# ---------- stop logic (exits after stopping) ----------
if [ "$STOP_REQUESTED" = true ]; then
    echo "Stopping playground container '$CONTAINER_NAME'..."
    if $DOCKER ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        $DOCKER stop "$CONTAINER_NAME"
        echo "Container stopped."
    else
        echo "Container is not running."
    fi

    if [ "$SETUP_CENTRAL_KB" = true ]; then
        echo ""
        echo "Stopping central-kb services..."
        CENTRAL_KB_DIR=""
        if [ -f "tooling/central-kb/docker-compose.yml" ]; then
            CENTRAL_KB_DIR="tooling/central-kb"
        elif [ -f "../central-kb/docker-compose.yml" ]; then
            CENTRAL_KB_DIR="../central-kb"
        else
            echo "Warning: central-kb not found. Nothing to stop."
        fi
        if [ -n "$CENTRAL_KB_DIR" ]; then
            (cd "$CENTRAL_KB_DIR" && $DOCKER compose stop embed-server tooling-central)
            echo "central-kb services stopped."
        fi
    fi
    exit 0
fi

# ---------- quickstart ----------
if [ "$QUICKSTART" = true ]; then
    if [ -f ./setenv.sh ]; then source ./setenv.sh; fi
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

# ---------- central‑kb setup ----------
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
        if [ -f .gitmodules ]; then
            git submodule update --init tooling/central-kb 2>/dev/null || true
        fi

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

        echo "Starting central-kb services (embed-server, tooling-central)..."
        (cd "$CENTRAL_KB_DIR" && $DOCKER compose up -d embed-server tooling-central)

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

        touch .central-kb-ready
        echo "Created .central-kb-ready marker"
    fi
    echo "=== Central KB setup complete, proceeding to playground ==="
fi

# ---------- project resolution ----------
if [ -n "$PROJECT_NAME" ]; then
    PROJ_PATH=$(resolve_project_path "$PROJECT_NAME" "$PROJECTS_FILE") || {
        echo "Error: project '$PROJECT_NAME' not found in $PROJECTS_FILE or path is invalid." >&2
        echo "  Add it to $PROJECTS_FILE, e.g.:"
        echo "    projects:"
        echo "      $PROJECT_NAME: ~/path/to/$PROJECT_NAME"
        exit 1
    }
    echo "Project '$PROJECT_NAME' → $PROJ_PATH"
fi

# ---------- build / pull (only when needed) ----------
NEEDS_BUILD=false
if [ "$FORCE_REBUILD" = true ]; then
    NEEDS_BUILD=true
elif ! $DOCKER image inspect playground-tooling:latest &>/dev/null; then
    NEEDS_BUILD=true
fi

if [ "$NEEDS_BUILD" = true ]; then
    # Ensure submodules are initialized before building
    if [ -f .gitmodules ]; then
      echo "Initializing git submodules..."
      git submodule update --init --recursive
    fi

    if [ "$PULL_IMAGE" = true ]; then
        echo "Pulling prebuilt image from GHCR..."
        if $DOCKER pull ghcr.io/qoolqool/playground-tooling:latest; then
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
            echo "  To build locally instead, run without --pull:  ./bootstrap.sh"
            echo "  To authenticate for higher rate limits: docker login ghcr.io"
            exit 1
        fi
    else
        echo "Building tooling container..."
        $DOCKER compose build
    fi
fi

# ---------- container lifecycle ----------
if [ "$FORCE_REBUILD" = true ] || [ -n "$PROJECT_NAME" ]; then
    if $DOCKER ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Removing existing container '${CONTAINER_NAME}'..."
        $DOCKER rm -f "$CONTAINER_NAME" 2>/dev/null || true
    fi
fi

if ! $DOCKER ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    # ---------- Determine mount paths and modes ----------
    if [ -n "$PROJ_PATH" ]; then
        # Project mode: mount the project dir as /workspace (rw)
        # and the playground root as /project (rw) — different directories
        MOUNT_TARGET="$PROJ_PATH"
        ENV_CKB="-e CENTRAL_KB_PROJECT=$PROJECT_NAME"
        PROJECT_MODE="rw"
        WORKSPACE_MODE="rw"
    else
        # Default mode: mount the playground root as both /workspace and /project
        # /workspace gets ro to avoid two writable mounts of the same directory
        MOUNT_TARGET="$SCRIPT_DIR"
        ENV_CKB=""
        PROJECT_MODE="rw"
        WORKSPACE_MODE="ro"
    fi

    SOCKET_MOUNT="${DOCKER_SOCKET_PATH:-/var/run/docker.sock}"
    DOCKER_HOST_ENV="${D_HOST:-unix:///var/run/docker.sock}"

    echo "Creating container '$CONTAINER_NAME'..."
    echo "  /project  ← $SCRIPT_DIR  (${PROJECT_MODE})"
    echo "  /workspace ← $MOUNT_TARGET (${WORKSPACE_MODE})"
    [ -n "$PROJECT_NAME" ] && echo "  CENTRAL_KB_PROJECT=$PROJECT_NAME"

    $DOCKER run -d --name "$CONTAINER_NAME" \
        --restart unless-stopped \
        -t -i \
        -v "${MOUNT_TARGET}:/workspace:${WORKSPACE_MODE}" \
        $ENV_CKB \
        -v "${SOCKET_MOUNT}:/var/run/docker.sock" \
        -v "$SCRIPT_DIR:/project:${PROJECT_MODE}" \
        -w /workspace \
        -e DOCKER_HOST="$DOCKER_HOST_ENV" \
        -e TZ=Asia/Kuala_Lumpur \
        --add-host host.docker.internal:host-gateway \
        --add-host host.containers.internal:host-gateway \
        playground-tooling:latest \
        bash -c '
            if [ -f /project/setenv.sh ]; then
                source /project/setenv.sh
            fi
            tail -f /dev/null
        '

    # Wait for container to be running
    for i in $(seq 1 10); do
        sleep 1
        STATUS=$($DOCKER inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo 'missing')
        [ "$STATUS" = "running" ] && break
        if [ "$STATUS" = "exited" ]; then
            echo "Container exited. Logs:"
            $DOCKER logs "$CONTAINER_NAME"
            $DOCKER rm -f "$CONTAINER_NAME" 2>/dev/null
            exit 1
        fi
        echo "  waiting... ($STATUS)"
    done
else
    if ! $DOCKER ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Starting existing container '$CONTAINER_NAME' ..."
        $DOCKER start "$CONTAINER_NAME" >/dev/null
    fi
fi

# Enter the container
echo ""
echo "Entering container (type 'exit' to leave)..."
echo ""
$DOCKER exec -it "$CONTAINER_NAME" bash
