#!/usr/bin/env bash
set -e

# --- install-skill.sh ---
# Install pi skills from GitHub repos or local directories.
#
# Usage:
#   ./tooling/scripts/install-skill.sh https://github.com/user/my-skill
#   ./tooling/scripts/install-skill.sh ./path/to/skill-dir
#
# A skill is any directory containing a SKILL.md file.
# Installed to: tooling/skills/<skill-name>/
# Post-install: runs install.sh if present in the skill directory.
# Survives image rebuild: tooling/ is volume-mounted from host.

SKILLS_DIR="/project/tooling/skills"
PI_SKILLS_DIR="/project/.pi/skills"

print_usage() {
    echo "Usage: $0 <github-url>|<local-path>"
    echo ""
    echo "Install a pi skill from a GitHub repo or local directory."
    echo ""
    echo "Examples:"
    echo "  $0 https://github.com/user/my-awesome-skill"
    echo "  $0 ./path/to/skill-dir"
    echo ""
    echo "A valid skill must contain a SKILL.md file."
    exit 1
}

die() {
    echo "Error: $1" >&2
    exit 1
}

# --- Parse arguments ---
SKILL_SOURCE="${1:-}"
if [ -z "$SKILL_SOURCE" ]; then
    print_usage
fi

# --- Create temp directory ---
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Installing skill from: $SKILL_SOURCE"

# --- Download or copy skill ---
SKILL_NAME=""
if [[ "$SKILL_SOURCE" =~ ^https?:// ]]; then
    # GitHub URL — clone with depth 1
    echo "  Cloning repository..."
    if git clone --depth 1 "$SKILL_SOURCE" "$TMP_DIR/repo" 2>/dev/null; then
        SKILL_NAME=$(basename "$SKILL_SOURCE" .git)
        SKILL_DIR="$TMP_DIR/repo"
    else
        die "Failed to clone $SKILL_SOURCE"
    fi
else
    # Local path — copy
    if [ ! -d "$SKILL_SOURCE" ]; then
        die "Directory not found: $SKILL_SOURCE"
    fi
    SKILL_NAME=$(basename "$SKILL_SOURCE")
    cp -r "$SKILL_SOURCE" "$TMP_DIR/repo"
    SKILL_DIR="$TMP_DIR/repo"
fi

# --- Validate: must contain SKILL.md ---
if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
    die "Not a valid skill: no SKILL.md found in $SKILL_SOURCE"
fi

# --- Check for conflicts ---
TARGET_DIR="$SKILLS_DIR/$SKILL_NAME"
if [ -d "$TARGET_DIR" ]; then
    echo "  ⚠  Skill '$SKILL_NAME' is already installed at $TARGET_DIR"
    echo "     Remove it first: rm -rf $TARGET_DIR"
    echo "     Skipping installation."
    exit 0
fi

# --- Copy skill to tooling/skills/ ---
echo "  Installing to: $TARGET_DIR"
mkdir -p "$SKILLS_DIR"
cp -r "$SKILL_DIR" "$TARGET_DIR"

# --- Run post-install hook if present ---
if [ -f "$TARGET_DIR/install.sh" ]; then
    echo "  Running post-install script..."
    chmod +x "$TARGET_DIR/install.sh"
    (cd "$TARGET_DIR" && bash install.sh) || \
        echo "  ⚠  install.sh exited with code $? (continuing)"
fi

# --- Symlink into .pi/skills/ for immediate availability ---
mkdir -p "$PI_SKILLS_DIR"
ln -sf "$TARGET_DIR" "$PI_SKILLS_DIR/$SKILL_NAME"
echo "  Symlinked: .pi/skills/$SKILL_NAME → $TARGET_DIR"

# --- Done ---
echo ""
echo "  ✓ Skill '$SKILL_NAME' installed successfully."
echo "    Location: tooling/skills/$SKILL_NAME/"
echo "    Available at: /$SKILL_NAME in the next agent session."
