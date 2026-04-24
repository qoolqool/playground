# Minimal Alpine-based Ollama image (~70MB base vs 5GB+)
# https://hub.docker.com/r/alpine/ollama
FROM alpine/ollama:latest

USER root

ENV TZ=Asia/Kuala_Lumpur \
    PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/tool/.local/bin"

# Install system dependencies
RUN apk add --no-cache \
    curl wget jq gnupg bash iputils bind-tools iproute2 \
    netcat-openbsd procps htop tree git sudo \
    python3 py3-pip py3-rich py3-click xdg-utils \
    build-base ncurses-dev unzip zstd nano less vim \
    docker-cli nodejs npm \
    # For Mermaid CLI (Puppeteer needs Chromium)
    chromium

# Docker Compose (standalone binary)
RUN curl -SL "https://github.com/docker/compose/releases/download/v2.30.3/docker-compose-linux-$(uname -m)" \
    -o /usr/local/bin/docker-compose && \
    chmod +x /usr/local/bin/docker-compose

# Neovim (latest)
RUN ARCH=$(uname -m) && \
    case "$ARCH" in \
      aarch64|arm64) NVIM_TAR="nvim-linux-arm64.tar.gz" ;; \
      *)             NVIM_TAR="nvim-linux-x86_64.tar.gz" ;; \
    esac && \
    curl -LO "https://github.com/neovim/neovim/releases/latest/download/${NVIM_TAR}" && \
    tar -C /usr/local --strip-components=1 -xzf "${NVIM_TAR}" && \
    rm "${NVIM_TAR}"

# Starship prompt
RUN curl -sS https://starship.rs/install.sh | sh -s -- -y --bin-dir /usr/local/bin

# Python tools (additional)
RUN pip3 install --break-system-packages --no-cache-dir requests rich click pynvim

# User setup
RUN adduser -D -u 502 -s /bin/bash tool && \
    echo 'tool ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers && \
    mkdir -p /project && chown tool:tool /project

USER tool
WORKDIR /home/tool

# Create modern nvim config structure
RUN mkdir -p ~/.config/nvim/lua/core ~/.config/nvim/lua/plugins ~/.config/nvim/data/undo

# Copy nvim config files
COPY --chown=tool:tool config/init.lua /home/tool/.config/nvim/init.lua
COPY --chown=tool:tool config/lua/core/options.lua /home/tool/.config/nvim/lua/core/options.lua
COPY --chown=tool:tool config/lua/core/keymaps.lua /home/tool/.config/nvim/lua/core/keymaps.lua
COPY --chown=tool:tool config/lua/core/autocmds.lua /home/tool/.config/nvim/lua/core/autocmds.lua
COPY --chown=tool:tool config/lua/plugins/init.lua /home/tool/.config/nvim/lua/plugins/init.lua
COPY --chown=tool:tool config/lua/plugins/lsp.lua /home/tool/.config/nvim/lua/plugins/lsp.lua
COPY --chown=tool:tool config/lua/plugins/treesitter.lua /home/tool/.config/nvim/lua/plugins/treesitter.lua
COPY --chown=tool:tool config/lua/plugins/telescope.lua /home/tool/.config/nvim/lua/plugins/telescope.lua
COPY --chown=tool:tool config/lua/plugins/nvim-tree.lua /home/tool/.config/nvim/lua/plugins/nvim-tree.lua
COPY --chown=tool:tool config/lua/plugins/markdown.lua /home/tool/.config/nvim/lua/plugins/markdown.lua
COPY --chown=tool:tool config/lua/plugins/cmp.lua /home/tool/.config/nvim/lua/plugins/cmp.lua

COPY --chown=tool:tool entrypoint.sh /entrypoint.sh
COPY --chown=tool:tool config/bashrc /home/tool/.bashrc
COPY --chown=tool:tool config/starship.toml /home/tool/.config/starship.toml
COPY --chown=tool:tool config/gitconfig /home/tool/.gitconfig

# Copy skills into image (context is ./tooling/, so skills/ not tooling/skills/)
COPY --chown=tool:tool skills/ /home/tool/.claude/skills/

# Skip nvim setup during build - plugins install on first run
RUN chmod +x /entrypoint.sh

# Claude Code
RUN curl -fsSL https://claude.ai/install.sh | bash

WORKDIR /project
ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
