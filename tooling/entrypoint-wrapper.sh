#!/bin/bash
set -e

# --- Git Submodule Initialization ---
echo "Initializing git submodules..."
git submodule update --init --recursive

# --- Ownership Fix ---
echo "Fixing /project permissions..."
sudo chown -R tool:tool /project 2>/dev/null || true

# --- Knowledge Pipeline Symlinks ---
# Create symlinks from tooling/scripts/ and tooling/skills/ into the
# skill-marketplace submodule. These are NOT tracked in git to avoid
# dangling symlinks on fresh clones. They're created at container start
# after submodule init ensures targets exist.
SCRIPT_SYMLINKS=(
  "search-kb-memory.py:../skills/search-kb/search-kb-memory.py"
  "load-kb-to-memory.py:../skills/distill-and-index/load-kb-to-memory.py"
)
for entry in "${SCRIPT_SYMLINKS[@]}"; do
  name="${entry%%:*}"
  target="${entry#*:}"
  if [ ! -e "/project/tooling/scripts/$name" ]; then
    ln -sf "$target" "/project/tooling/scripts/$name"
    echo "Created symlink: tooling/scripts/$name -> $target"
  fi
done

SKILL_SYMLINKS=(
  "search-kb:../skill-marketplace/plugins/distill-rag-bridge/skills/search-kb"
  "distill-and-index:../skill-marketplace/plugins/distill-rag-bridge/skills/distill-and-index"
)
for entry in "${SKILL_SYMLINKS[@]}"; do
  name="${entry%%:*}"
  target="${entry#*:}"
  if [ ! -e "/project/tooling/skills/$name" ]; then
    ln -sf "$target" "/project/tooling/skills/$name"
    echo "Created symlink: tooling/skills/$name -> $target"
  fi
done

# --- Pi Skills Bootstrap ---
# Symlink tooling/skills/ into .pi/skills/ so agent skills survive fresh clones.
# .pi/ is gitignored, so these symlinks are recreated on every container start.
# New skills can be installed at runtime via:
#   ./tooling/scripts/install-skill.sh <github-url>|<local-path>
SKILLS_SRC="/project/tooling/skills"
SKILLS_DST="/project/.pi/skills"
if [ -d "$SKILLS_SRC" ]; then
  mkdir -p "$SKILLS_DST"
  for skill_dir in "$SKILLS_SRC"/*/; do
    if [ -d "$skill_dir" ]; then
      skill_name=$(basename "$skill_dir")
      ln -sf "$skill_dir" "$SKILLS_DST/$skill_name"
    fi
  done
  synced=$(ls -1d "$SKILLS_DST"/*/ 2>/dev/null | wc -l | tr -d ' ')
  echo "Bootstrapped $synced pi skills from tooling/skills/"
fi

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

# Embeddings are served by embed-server.py (Model2Vec distilled BGE-M3 via Hugging Face)
# No Ollama model needed — the 1024-dim model is loaded by the embed daemon.
# See: scripts/embed-server.py (default: tss-deposium/m2v-bge-m3-1024d, 1024-dim, ~500MB)


echo "╔========================================================╗"
echo "|    Tooling Container                                   |"
echo "|    Ollama is now running in paperclip container        |"
echo "|    Ollama URL: http://127.0.0.1:11434                  |"

# Detect host IP for local model access (UX: OLLAMA_HOST)
# Docker uses host.docker.internal; Podman uses host.containers.internal
if getent hosts host.docker.internal >/dev/null 2>&1; then
  export HOST_IP=$(getent hosts host.docker.internal | awk '{print $1}')
elif getent hosts host.containers.internal >/dev/null 2>&1; then
  export HOST_IP=$(getent hosts host.containers.internal | awk '{print $1}')
elif command -v ip >/dev/null 2>&1; then
  export HOST_IP=$(ip route | awk '/default/ {print $3}')
fi
export HOST_IP=${HOST_IP:-localhost}
echo "|    Host IP (local models): $HOST_IP                     "
echo "╚════════════════════════════════════════════════════════╝"

alias vi=nvim
# Execute the main command
exec "$@"
