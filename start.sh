#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Parse arguments
FORCE_REBUILD=false
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--force)
            FORCE_REBUILD=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./start.sh [-f|--force]"
            echo "  -f, --force    Force rebuild and recreate container"
            exit 1
            ;;
    esac
done

# Container name is stored in .container_name file (deterministic per playground)
CONTAINER_FILE=".container_name"

# Function to find available container name
find_available_name() {
    local base="tooling"
    local name="$base"
    local counter=2
    while docker ps -a --format '{{.Names}}' | grep -q "^${name}$"; do
        name="${base}-${counter}"
        counter=$((counter + 1))
    done
    echo "$name"
}

# Force rebuild - remove existing container
if [ "$FORCE_REBUILD" = true ]; then
    if [ -f "$CONTAINER_FILE" ]; then
        CONTAINER_NAME=$(cat "$CONTAINER_FILE")
        echo "Force rebuild - removing container '$CONTAINER_NAME'..."
        docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
    fi
    rm -f "$CONTAINER_FILE"
    echo "Force rebuild - rebuilding image..."
    docker compose build

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
    docker compose up -d
    echo "$CONTAINER_NAME" > "$CONTAINER_FILE"
    rm -f docker-compose.override.yml
    echo ""
    echo "Entering container (type 'exit' to leave)..."
    echo ""
    docker exec -it "$CONTAINER_NAME" bash
    exit 0
fi

if [ -f "$CONTAINER_FILE" ]; then
    # This playground has an assigned container
    CONTAINER_NAME=$(cat "$CONTAINER_FILE")

    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Container '$CONTAINER_NAME' is running."
    elif docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Container '$CONTAINER_NAME' exists but is stopped. Starting..."
        docker start "$CONTAINER_NAME"
    else
        echo "Container '$CONTAINER_NAME' was removed. Creating new one..."
        rm -f "$CONTAINER_FILE"
        # Fall through to first-run logic
    fi

    if [ -f "$CONTAINER_FILE" ]; then
        echo "Entering container (type 'exit' to leave)..."
        echo ""
        docker exec -it "$CONTAINER_NAME" bash
        exit 0
    fi
fi

# First run - build and create container
echo "First run - building tooling container..."
docker compose build

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
docker compose up -d

# Store container name for future runs
echo "$CONTAINER_NAME" > "$CONTAINER_FILE"
rm -f docker-compose.override.yml

echo ""
echo "Entering container (type 'exit' to leave)..."
echo ""
docker exec -it "$CONTAINER_NAME" bash
