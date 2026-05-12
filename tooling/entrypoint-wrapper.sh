#!/bin/bash
set -e

# --- Ownership Fix ---
echo "Fixing /project permissions..."
sudo chown -R tool:tool /project 2>/dev/null || true

# Ensure nvim plugins & tools are installed (first run only)
if [ ! -d "${XDG_DATA_HOME:-$HOME/.local/share}/nvim/lazy" ]; then
  echo "Installing nvim plugins (first run)..."
  nvim --headless "+Lazy! sync" +qa || true
  echo "Installing Treesitter parsers..."
  nvim --headless "+TSInstallSync python lua bash sql java xml json yaml markdown markdown_inline" +qa 2>/dev/null || true
  echo "Installing Mason LSP servers..."
  nvim --headless "+MasonInstall pyright lua-language-server" +qa 2>/dev/null || true
fi

ollama serve &

# Wait for Ollama to be ready
for i in $(seq 1 30); do
  if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama ready"
    break
  fi
  sleep 1
done

# Pull embedding model for knowledgebase vector search (small ~33MB)
if ! curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if any('bge-large' in m['name'] for m in d.get('models',[])) else 1)" 2>/dev/null; then
  echo "Pulling bge-large embedding model (~670MB)..."
  ollama pull bge-large:latest &
fi


echo "╔========================================================╗"
echo "|    Tooling Container                                   |"
echo "|    Ollama is now running in paperclip container        |"
echo "|    Ollama URL: http://127.0.0.1:11434                  |"

# Detect host IP for local model access (UX: OLLAMA_HOST)
if getent hosts host.docker.internal >/dev/null 2>&1; then
  export HOST_IP=$(getent hosts host.docker.internal | awk '{print $1}')
elif command -v ip >/dev/null 2>&1; then
  export HOST_IP=$(ip route | awk '/default/ {print $3}')
fi
export HOST_IP=${HOST_IP:-localhost}
echo "|    Host IP (local models): $HOST_IP                     "
echo "╚════════════════════════════════════════════════════════╝"

alias vi=nvim
# Execute the main command
exec "$@"
