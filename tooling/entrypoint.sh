#!/usr/bin/env bash
set -e

echo "========================================"
echo "  Tooling Container"
echo "========================================"

# Install nvim plugins on first run
if [ ! -d "$HOME/.local/share/nvim/lazy/nvim-lspconfig" ]; then
    echo "Installing nvim plugins (first run, this takes a minute)..."
    nvim --headless -c "lazy sync" -c qa 2>&1 || true
    echo "Plugins installed."
fi

# Start Ollama in background (if not running)
if command -v ollama >/dev/null && ! pgrep -x ollama >/dev/null; then
    echo "Starting Ollama..."
    ollama serve >/tmp/ollama.log 2>&1 &
    sleep 2
fi

if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[OK] Ollama (container) available"
else
    echo "[INFO] Ollama starting..."
fi

# Check host Ollama (local models with GPU)
if curl -s --connect-timeout 2 http://host.docker.internal:11434/api/tags >/dev/null 2>&1; then
    echo "[OK] Ollama (host) available — use 'ollama-local' for local models"
else
    echo "[INFO] Host Ollama not reachable — local models unavailable"
fi

docker info >/dev/null 2>&1 && echo "[OK] Docker accessible" || echo "[WARN] Docker not accessible"
command -v claude >/dev/null && echo "[OK] Claude Code available" || echo "[WARN] Claude not found"
echo "========================================"
echo ""
exec "$@"