#!/usr/bin/env bash
# install-kb-cli.sh — Install the `kb` CLI for Central Knowledge Base
#
# Strategy (in order):
#   1. If tooling-central package is available → install the official kb CLI via pip
#   2. Otherwise → install the standalone kb-cli.py wrapper that talks HTTP directly
#
# The standalone wrapper auto-generates embeddings via Ollama — no extra deps needed.
#
# Usage:
#   bash install-kb-cli.sh
#   bash install-kb-cli.sh --central-kb-path /path/to/tooling-central

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"

# --- Parse args ---
CENTRAL_KB_PATH=""
for arg in "$@"; do
    case "$arg" in
        --central-kb-path=*) CENTRAL_KB_PATH="${arg#--central-kb-path=}" ;;
        --central-kb-path)   shift; CENTRAL_KB_PATH="$1" ;;
    esac
done

# --- Ensure install dir exists ---
mkdir -p "$INSTALL_DIR"

# --- Strategy 1: Try official kb CLI from tooling-central ---
INSTALLED=false
if [ -z "$CENTRAL_KB_PATH" ]; then
    # Search common locations
    for candidate in \
        "$SCRIPT_DIR/../../../tooling-central" \
        "$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)/../tooling-central" \
        "/project/../tooling-central" \
        "/project/tooling-central"; do
        if [ -d "$candidate" ] && [ -f "$candidate/pyproject.toml" ]; then
            CENTRAL_KB_PATH="$(cd "$candidate" && pwd)"
            break
        fi
    done
fi

if [ -n "$CENTRAL_KB_PATH" ] && [ -f "$CENTRAL_KB_PATH/pyproject.toml" ]; then
    echo "🔧 Installing official kb CLI from: $CENTRAL_KB_PATH"
    if pip install --break-system-packages --no-deps -e "$CENTRAL_KB_PATH" 2>&1 | grep -v "^WARNING:"; then
        if command -v kb &>/dev/null; then
            INSTALLED=true
            echo "✅ Official kb CLI installed: $(command -v kb)"
        fi
    fi
fi

# --- Strategy 2: Standalone wrapper ---
if [ "$INSTALLED" = "false" ]; then
    echo "📦 tooling-central not found — installing standalone kb CLI wrapper"
    cp "$SCRIPT_DIR/kb-cli.py" "$INSTALL_DIR/kb"
    chmod +x "$INSTALL_DIR/kb"
    # Verify Python works
    if python3 "$INSTALL_DIR/kb" --help > /dev/null 2>&1; then
        INSTALLED=true
        echo "✅ Standalone kb CLI installed: $INSTALL_DIR/kb"
    else
        echo "❌ Standalone kb CLI failed validation"
        exit 1
    fi
fi

# --- Ensure PATH ---
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "⚠️  Adding ~/.local/bin to PATH"
    export PATH="$HOME/.local/bin:$PATH"
    grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc" 2>/dev/null || \
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi

# --- Verify Ollama + embedding model ---
EMBED_MODEL="${KB_EMBED_MODEL:-bge-large:latest}"
if command -v ollama &>/dev/null; then
    # Check if server is running
    if curl -s --max-time 3 http://localhost:11434/ > /dev/null 2>&1; then
        # Check if embedding model exists
        MODEL_NAME="${EMBED_MODEL%%:*}"
        if ! ollama list 2>/dev/null | grep -q "$MODEL_NAME"; then
            echo "📥 Pulling embedding model: $EMBED_MODEL"
            ollama pull "$EMBED_MODEL" 2>&1 | tail -1
        fi
        echo "✅ Ollama ready with $EMBED_MODEL"
    else
        echo "⚠️  Ollama server not running — start with: ollama serve"
    fi
else
    echo "⚠️  Ollama not found — embeddings will not work without it"
    echo "   Install: curl -fsSL https://ollama.com/install.sh | sh"
fi

# --- Determine server URL ---
KB_URL="${CENTRAL_KB_URL:-}"
if [ -z "$KB_URL" ]; then
    # Auto-detect: try host.containers.internal, then host.docker.internal, then gateway
    for host_candidate in host.containers.internal host.docker.internal; do
        if curl -s --max-time 3 "http://${host_candidate}:9000/health" > /dev/null 2>&1; then
            KB_URL="http://${host_candidate}:9000"
            break
        fi
    done
    if [ -z "$KB_URL" ]; then
        # Try default gateway
        GW=$(ip route show default 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="via") print $(i+1)}' | head -1)
        if [ -n "$GW" ] && curl -s --max-time 3 "http://${GW}:9000/health" > /dev/null 2>&1; then
            KB_URL="http://${GW}:9000"
        else
            KB_URL="http://localhost:9000"
        fi
    fi
fi
export CENTRAL_KB_URL="$KB_URL"
if curl -s --max-time 3 "$KB_URL/health" > /dev/null 2>&1; then
    HEALTH=$(curl -s "$KB_URL/health")
    echo "✅ Central KB server reachable: $HEALTH"
else
    echo "⚠️  Central KB server not reachable at $KB_URL"
    echo "   Set CENTRAL_KB_URL to the correct server URL"
fi

# --- Summary ---
echo ""
echo "═══════════════════════════════════════════════════"
echo "  kb CLI installed! Next steps:"
echo ""
echo "  1. Set environment variables (or let kb auto-detect the server):"
echo "     export CENTRAL_KB_URL=$KB_URL          # auto-detected, override if needed"
echo "     export CENTRAL_KB_PROJECT=<your-project-name>"
echo ""
echo "  2. Use the CLI:"
echo "     kb health                            # Check server"
echo "     kb submit --project my-project        # Push entries"
echo "     kb search \"some query\" --scope my-project"
echo "     kb pull --project my-project"
echo "     kb drift --project my-project"
echo "     kb candidates"
echo "═══════════════════════════════════════════════════"