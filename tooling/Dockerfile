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
    nodejs npm libstdc++6 libgcc-s1 && \
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
RUN pip3 install --break-system-packages --no-cache-dir requests rich click mcp-atlassian

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
COPY --chown=tool:tool port-forward.py /home/tool/port-forward.py

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
ENV PATH=$PATH:/home/tool/.npm-global/bin

# 2. Ensure the directory exists and is owned by 'tool'
# Run this as root before switching users
RUN mkdir -p /home/tool/.npm-global && \
    chown -R tool:tool /home/tool/.npm-global

# 3. Now global installs will work without sudo/root
# Install Pi coding agent globally
# Use the updated namespace
RUN npm install -g @earendil-works/pi-coding-agent

# Install Superpowers (assuming it's an NPM or Git package)
# Install ONLY the plus bundle (it includes subagents internally)
RUN pi install npm:pi-superpowers-plus || true

# Install local distill-rag-bridge from your copied local directory
RUN pi install /home/tool/.local/share/skill-marketplace/plugins/distill-rag-bridge || true

# Install atlassian skill (Confluence/Jira CLI wrapper)
COPY --chown=tool:tool skills/atlassian/ /home/tool/.local/share/skill-marketplace/atlassian/

# Install pi-hermes-memory (persistent memory + session search + secret scanning)
RUN pi install npm:pi-hermes-memory || true


# --- ATLASSIAN CLI SCRIPT ------------------------------------------------
COPY --chown=tool:tool scripts/atlassian-cli.py scripts/atlassian-cli.py

# --- KNOWLEDGEBASE VECTOR SEARCH SCRIPTS --------------------------------
COPY --chown=tool:tool scripts/embed-server.py scripts/embed-server.py
COPY --chown=tool:tool scripts/load-kb-to-memory.py scripts/load-kb-to-memory.py
COPY --chown=tool:tool scripts/search-kb-memory.py scripts/search-kb-memory.py

# Cleanup: remove npm/pnpm caches and tmp artifacts
RUN rm -rf /tmp/* /home/tool/.npm /home/tool/.cache/node 2>/dev/null; \
    npm cache clean --force 2>/dev/null || true

# Ollama (standalone binary — embedding model pulled at container start)
ENV OLLAMA_HOME=/home/tool/.ollama

WORKDIR /project

ENTRYPOINT ["/entrypoint-wrapper.sh"]
CMD ["bash"]
