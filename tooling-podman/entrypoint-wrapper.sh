#!/bin/bash
set -e

# --- Ownership Fix ---
echo "Fixing /project permissions..."
sudo chown -R tool:tool /project 2>/dev/null || true

# Ensure nvim plugins are installed (in case Docker layer cache was invalidated)
if [ ! -d "${XDG_DATA_HOME:-$HOME/.local/share}/nvim/lazy" ]; then
  echo "Installing nvim plugins (first run)..."
  nvim --headless "+Lazy! sync" +qa || true
fi

ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama to be ready..."
for i in $(seq 1 30); do
  if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Pull embedding model if not already present
if ! ollama list 2>/dev/null | grep -q bge-small; then
  echo "Pulling embedding model bge-small:latest (34 MB)..."
  ollama pull bge-small:latest 2>&1 | tail -5
  echo "Model pulled successfully"
fi

# Start embed daemon (fast local embeddings, ~40ms vs 330ms via Ollama)
if [ -f /project/scripts/embed-server.py ]; then
  echo "Starting embed daemon..."
  python3 /project/scripts/embed-server.py &
  # Give it a moment to load the model
  sleep 1
fi

# Initial knowledgebase index (idempotent — uses embed daemon if available)
if [ -f /project/scripts/load-kb-to-memory.py ]; then
  echo "Building knowledgebase vector index..."
  python3 /project/scripts/load-kb-to-memory.py 2>&1 || echo "Index build deferred (will retry on next start)"
fi

# Port forwarder: makes developer portal accessible on Mac host
python3 /home/tool/port-forward.py &
disown

echo "╔========================================================╗"
echo "|    Tooling Container                                   |"
echo "|    Ollama is now running in tooling container          |"
echo "|    Ollama URL: http://tooling:11434                    |"
echo "╚════════════════════════════════════════════════════════╝"

# Execute the main command
exec "$@"