#!/bin/bash
set -e

# --- Git Submodule Initialization ---
# Always run from /project (playground root) regardless of -w flag
cd /project
echo "Initializing git submodules..."
git submodule update --init --recursive || echo "⚠ git submodule update skipped (non-fatal)"

# --- Ownership Fix ---
echo "Fixing /project permissions..."
sudo chown -R tool:tool /project 2>/dev/null || true

# --- Knowledge Pipeline Symlinks ---
# Create symlinks from tooling/scripts/ and tooling/skills/ into the
# skill-marketplace submodule. These are NOT tracked in git to avoid
# dangling symlinks on fresh clones. They're created at container start
# after submodule init ensures targets exist.

# Cleanup: Remove global skill-marketplace plugins that conflict with project submodule
# This prevents "skill collision" warnings when the same plugin exists in both locations
GLOBAL_MARKETPLACE="$HOME/.local/share/skill-marketplace/plugins"
PROJECT_MARKETPLACE="/project/tooling/skill-marketplace/plugins"

if [ -d "$PROJECT_MARKETPLACE" ] && [ -d "$GLOBAL_MARKETPLACE" ]; then
  for plugin_dir in "$PROJECT_MARKETPLACE"/*/; do
    if [ -d "$plugin_dir" ]; then
      plugin_name=$(basename "$plugin_dir")
      global_plugin="$GLOBAL_MARKETPLACE/$plugin_name"
      if [ -d "$global_plugin" ]; then
        rm -rf "$global_plugin"
        echo "Removed conflicting global plugin: $global_plugin"
      fi
    fi
  done
fi

# Cleanup: Remove old symlinks in skill-marketplace (created by pi install)
MARKETPLACE_SKILLS="/project/tooling/skill-marketplace/plugins/distill-rag-bridge/skills"
if [ -d "$MARKETPLACE_SKILLS" ]; then
  for skill_dir in "$MARKETPLACE_SKILLS"/*/; do
    if [ -d "$skill_dir" ]; then
      skill_name=$(basename "$skill_dir")
      # Remove symlinks inside skill directories (circular or pointing elsewhere)
      for link in "$skill_dir$skill_name" "$skill_dir"*.py; do
        if [ -L "$link" ]; then
          rm -f "$link"
          echo "Removed symlink from skill-marketplace: $link"
        fi
      done
    fi
  done
fi

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

# Cleanup: Remove ALL symlinks inside skill directories (circular or otherwise)
# These are created by pi install and cause "skill collision" warnings
# Run cleanup TWICE: before and after bootstrap to catch runtime-created symlinks
cleanup_circular_symlinks() {
  local src_dir="$1"
  if [ -d "$src_dir" ]; then
    for skill_dir in "$src_dir"/*/; do
      if [ -d "$skill_dir" ]; then
        skill_name=$(basename "$skill_dir")
        # Remove circular symlink (skill_name -> parent dir)
        circular_link="$skill_dir$skill_name"
        if [ -L "$circular_link" ]; then
          rm -f "$circular_link"
          echo "Removed circular symlink: $circular_link"
        fi
        # Remove any other symlinks in skill directory root (including hidden)
        for link in "$skill_dir"* "$skill_dir".*; do
          if [ -L "$link" ] && [ "$(basename "$link")" != "." ] && [ "$(basename "$link")" != ".." ]; then
            rm -f "$link"
            echo "Removed symlink from skill directory: $link"
          fi
        done
      fi
    done
  fi
}

# Pre-cleanup: remove any existing circular symlinks from previous runs
cleanup_circular_symlinks "$SKILLS_SRC"
rm -rf "$SKILLS_DST"

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

# Post-cleanup: remove any circular symlinks that pi may have created at runtime
cleanup_circular_symlinks "$SKILLS_SRC"

# --- Cross-Project Skills Bridge ---
# When --project is used, /workspace points to a different directory than /project.
# Pi discovers skills from .pi/skills/ in cwd (/workspace), so we bridge them
# so Pi always finds the skills from /project regardless of which project is mounted.
# When no --project is used, /workspace and /project are the same directory,
# so the symlink would be circular — skip in that case.
if [ "$(readlink -f /workspace 2>/dev/null || echo /workspace)" != "$(readlink -f /project 2>/dev/null || echo /project)" ]; then
  mkdir -p /workspace/.pi 2>/dev/null || {
    echo "Warning: Cannot write to /workspace/.pi (project directory may not exist on host)"
    echo "  Create the directory on your host: mkdir -p $(readlink -f /workspace 2>/dev/null)"
  }
  if [ -w /workspace/.pi ]; then
    # Remove existing dir/symlink at target to avoid conflicts
    if [ -e /workspace/.pi/skills ] && [ ! -L /workspace/.pi/skills ]; then
      rm -rf /workspace/.pi/skills
      echo "Removed existing /workspace/.pi/skills/ directory (replacing with symlink)"
    fi
    ln -sfn /project/.pi/skills /workspace/.pi/skills
    echo "Bridged skills: /workspace/.pi/skills → /project/.pi/skills"
  fi
fi

# --- Pi Extensions & Settings Bootstrap ---
# .pi/ is gitignored — seed all config from tooling/ at container start.
# Source files live under /project/tooling/ (volume-mounted, survive rebuild).
PI_CONFIG_SRC="/project/tooling/config/pi"
PI_DST="/project/.pi"
mkdir -p "$PI_DST/extensions"

# Deploy extension source
if [ -f "/project/tooling/extensions/resume-handoff.ts" ]; then
  cp "/project/tooling/extensions/resume-handoff.ts" "$PI_DST/extensions/resume-handoff.ts"
  echo "Bootstrapped resume-handoff extension"
fi

# Deploy pi config files (settings.json, package.json)
if [ -d "$PI_CONFIG_SRC" ]; then
  for f in "$PI_CONFIG_SRC"/*; do
    if [ -f "$f" ]; then
      cp "$f" "$PI_DST/"
      echo "Bootstrapped .pi/$(basename $f)"
    fi
  done
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
echo "╔========================================================╗"
echo "|    Tooling Container                                    |"
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

# Execute the main command. If no command is given, default to running ollama
if [ $# -gt 0 ]; then
    exec "$@"
else
    exec ollama serve
fi
