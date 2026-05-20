FROM debian:trixie-slim

USER root

ENV TZ=Asia/Kuala_Lumpur \
    PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/tool/.local/bin" \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt


# --- CA bootstrap -----------------------------------------------------
RUN apt update && apt install --no-install-recommends -y ca-certificates && \
    update-ca-certificates && \
    mkdir -p /usr/local/sbin /usr/local/bin && \
    rm -rf /var/lib/apt/lists/*

# --- Core packages ----------------------------------------------------
RUN apt update && apt install --no-install-recommends -y \
    curl wget jq gnupg bash iputils-ping dnsutils iproute2 \
    netcat-openbsd procps htop tree git sudo \
    python3 python3-pip python3-venv xdg-utils \
    build-essential libncurses-dev unzip zstd less \
    libstdc++6 libgcc-s1 && \
    rm -rf /var/lib/apt/lists/*

# --- Docker CLI (standalone binary, no daemon) -------------------------
RUN set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64)  DOCKER_ARCH="x86_64" ;; \
      aarch64|arm64) DOCKER_ARCH="aarch64" ;; \
      *) echo "Unsupported arch: $ARCH"; exit 1 ;; \
    esac; \
    DOCKER_VERSION="29.4.3"; \
    curl -fsSL "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${DOCKER_VERSION}.tgz" \
      -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /tmp; \
    mv /tmp/docker/docker /usr/local/bin/docker; \
    chmod +x /usr/local/bin/docker; \
    rm -rf /tmp/docker.tgz /tmp/docker; \
    docker --version

# Install Node.js 22 (required by pi-coding-agent >=22.19.0)
RUN set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64)  NODE_ARCH="x64" ;; \
      aarch64|arm64) NODE_ARCH="arm64" ;; \
      *) echo "Unsupported arch: $ARCH"; exit 1 ;; \
    esac; \
    NODE_VERSION="22.19.0"; \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" \
      -o /tmp/node.tar.xz; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1; \
    rm -rf /tmp/node.tar.xz; \
    node --version; \
    npm --version

# Global npm tools
RUN npm install -g typescript pnpm && npm cache clean --force


# --- OLLAMA (standalone binary, no models) ----------------------------
RUN set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64)  GOARCH="amd64" ;; \
      aarch64|arm64) GOARCH="arm64" ;; \
      *) echo "Unsupported arch: $ARCH"; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-${GOARCH}.tar.zst" \
      -o /tmp/ollama.tar.zst; \
    zstd -d < /tmp/ollama.tar.zst | tar -xf - -C /tmp; \
    mv /tmp/bin/ollama /usr/local/bin/ollama; \
    chmod +x /usr/local/bin/ollama; \
    rm -rf /tmp/ollama.tar.zst /tmp/bin /tmp/lib; \
    ollama --version

# --- NEOVIM + STARSHIP ------------------------------------------------
RUN set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64) \
        NVIM_TAR="nvim-linux-x86_64.tar.gz" ;; \
      aarch64|arm64) \
        NVIM_TAR="nvim-linux-arm64.tar.gz" ;; \
      *) \
        echo "Unsupported architecture: $ARCH"; \
        exit 1 ;; \
    esac; \
    curl -LO "https://github.com/neovim/neovim/releases/latest/download/${NVIM_TAR}"; \
    mkdir -p /tmp/nvim; \
    tar -xzf "${NVIM_TAR}" -C /tmp/nvim; \
    cp -r /tmp/nvim/nvim-linux-*/bin /usr/local/; \
    cp -r /tmp/nvim/nvim-linux-*/lib /usr/local/; \
    cp -r /tmp/nvim/nvim-linux-*/share /usr/local/; \
    rm -rf "${NVIM_TAR}" /tmp/nvim; \
    curl -sS https://starship.rs/install.sh -o /tmp/starship-install.sh; \
    sh /tmp/starship-install.sh -y --bin-dir /usr/local/bin; \
    rm -f /tmp/starship-install.sh; \
    nvim --version | head -n 1; \
    starship --version


# --- PYTHON -----------------------------------------------------------
RUN pip3 install --break-system-packages --no-cache-dir requests rich click mcp-atlassian pipx sentence-transformers && \
    pipx ensurepath

# --- USER -------------------------------------------------------------
RUN useradd -u 502 -m -s /bin/bash tool && \
    echo 'tool ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers && \
    mkdir -p /project && chown tool:tool /project

USER tool
WORKDIR /home/tool

# --- NEOVIM CONFIG ----------------------------------------------------
COPY --chown=tool:tool config/nvim/ /home/tool/.config/nvim/
# Plugins are installed at container start by entrypoint-wrapper.sh

# --- SHELL / GIT CONFIG -----------------------------------------------
COPY --chown=tool:tool config/bashrc /home/tool/.bashrc
COPY --chown=tool:tool config/starship.toml /home/tool/.config/starship.toml
COPY --chown=tool:tool config/gitconfig /home/tool/.gitconfig
COPY --chown=tool:tool entrypoint-wrapper.sh /entrypoint-wrapper.sh

RUN chmod +x /entrypoint-wrapper.sh

# --- DOCKER COMPOSE ---------------------------------------------------
ARG COMPOSE_VERSION=v5.1.3
RUN ARCH="$(uname -m)" && \
    case ${ARCH} in \
        x86_64)  BINARY_ARCH=x86_64 ;; \
        aarch64|arm64) BINARY_ARCH=aarch64 ;; \
        armv7*)  BINARY_ARCH=armv7 ;; \
        *) echo "Unsupported architecture: ${ARCH}"; exit 1 ;; \
    esac && \
    sudo mkdir -p /usr/local/lib/docker/cli-plugins && \
    sudo curl -fSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-${BINARY_ARCH}" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose && \
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose && \
    sudo ln -s /usr/local/lib/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose

# --- AI PLUGINS ------------------------------------------------
COPY --chown=tool:tool skill-marketplace/ /home/tool/.local/share/skill-marketplace/

# --- AI TOOLS ---------------------------------------------------------
# 1. Setup variables (must be separate lines to reference each other)
ENV NPM_CONFIG_PREFIX=/home/tool/.npm-global
ENV PATH=$PATH:/home/tool/.npm-global/bin:/home/tool/.local/bin

# 2. Ensure the directory exists and is owned by 'tool'
# Run this as root before switching users
RUN mkdir -p /home/tool/.npm-global && \
    chown -R tool:tool /home/tool/.npm-global

# 3. Now global installs will work without sudo/root
# Install Pi coding agent globally
# Use the updated namespace
RUN npm install -g @earendil-works/pi-coding-agent

# Install local distill-rag-bridge from your copied local directory
RUN pi install /home/tool/.local/share/skill-marketplace/plugins/distill-rag-bridge || true

# Install pi-hermes-memory (persistent memory + session search + secret scanning)
RUN pi install npm:pi-hermes-memory || true

# Install subagent extension and agent definitions
COPY --chown=tool:tool extensions/logging.ts /home/tool/.pi/agent/extensions/logging.ts
COPY --chown=tool:tool extensions/subagent/ /home/tool/.pi/agent/extensions/subagent/
COPY --chown=tool:tool extensions/agents/ /home/tool/.pi/agent/agents/

# --- ATLASSIAN CLI SCRIPT ------------------------------------------------
COPY --chown=tool:tool scripts/atlassian-cli.py scripts/atlassian-cli.py

# --- KNOWLEDGEBASE VECTOR SEARCH + CENTRAL KB CLI --------------------------------
# Vector DB scripts and embed-server for local indexing.
# Search and load scripts are now bundled inside skill-marketplace submodule
# (plugins/distill-rag-bridge/skills/*/) alongside their SKILL.md files.
# embed-server.py is a system daemon, kept here.
COPY --chown=tool:tool scripts/embed-server.py scripts/embed-server.py

# Install kb CLI (Central Knowledge Base)
COPY --chown=tool:tool skills/install-kb-cli/ /tmp/kb-skill/
RUN mkdir -p /home/tool/.local/bin && \
    cp /tmp/kb-skill/kb-cli.py /home/tool/.local/bin/kb && \
    chmod +x /home/tool/.local/bin/kb && \
    rm -rf /tmp/kb-skill

# Cleanup: remove npm/pnpm caches and tmp artifacts
RUN rm -rf /tmp/* /home/tool/.npm /home/tool/.cache/node 2>/dev/null; \
    npm cache clean --force 2>/dev/null || true

# Ollama (standalone binary — used for LLM inference, not embeddings)
# Embeddings are served by embed-server.py via Hugging Face sentence-transformers.
ENV OLLAMA_HOME=/home/tool/.ollama

WORKDIR /project

ENTRYPOINT ["/entrypoint-wrapper.sh"]
CMD ["bash"]
