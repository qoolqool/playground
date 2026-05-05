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
    docker.io nodejs npm libstdc++6 libgcc-s1 && \
    rm -rf /var/lib/apt/lists/*

# Global npm tools
RUN npm install -g typescript pnpm && npm cache clean --force

# --- JAVA / MAVEN -----------------------------------------------------
RUN apt update && apt install --no-install-recommends -y \
    openjdk-21-jdk-headless maven && \
    rm -rf /var/lib/apt/lists/*

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

# --- NEOVIM + STARSHIP + GLOW -----------------------------------------
RUN set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64) \
        NVIM_TAR="nvim-linux-x86_64.tar.gz"; \
        GLOW_ARCH="amd64" ;; \
      aarch64|arm64) \
        NVIM_TAR="nvim-linux-arm64.tar.gz"; \
        GLOW_ARCH="arm64" ;; \
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

# --- GO ---------------------------------------------------------------
RUN set -eux; \
    ARCH="$(uname -m)"; \
    case "$ARCH" in \
      x86_64) GO_ARCH="amd64" ;; \
      aarch64|arm64) GO_ARCH="arm64" ;; \
      *) echo "Unsupported architecture: $ARCH"; exit 1 ;; \
    esac; \
    curl -sL "https://go.dev/dl/go1.24.2.linux-${GO_ARCH}.tar.gz" -o /tmp/go.tar.gz; \
    tar -C /usr/local -xzf /tmp/go.tar.gz; \
    rm -f /tmp/go.tar.gz; \
    ln -s /usr/local/go/bin/go /usr/local/bin/go; \
    ln -s /usr/local/go/bin/gofmt /usr/local/bin/gofmt; \
    go version

# --- PYTHON -----------------------------------------------------------
RUN pip3 install --break-system-packages --no-cache-dir requests rich click
RUN pip3 install --break-system-packages --no-cache-dir \
    fastapi==0.115.12 \
    uvicorn[standard]==0.34.2 \
    sqlalchemy[asyncio]==2.0.41 \
    asyncpg==0.30.0 \
    psycopg2-binary==2.9.10 \
    pydantic==2.11.3 \
    pydantic-settings==2.9.1 \
    apscheduler==3.11.0 \
    httpx==0.28.1 \
    pytest==8.3.5 \
    pytest-asyncio==0.26.0 \
    aiosqlite==0.22.1 \
    pyiso8583>=4.0 \
    xrpl-py>=4.5 \
    scalar-fastapi>=1.8.0 \
    markdown-it-py>=3.0 \
    mdit-py-plugins>=0.4 \
    sentence-transformers>=4.0

# --- USER -------------------------------------------------------------
RUN useradd -u 502 -m -s /bin/bash tool && \
    echo 'tool ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers && \
    mkdir -p /project && chown tool:tool /project


USER tool
WORKDIR /home/tool

# --- NEOVIM CONFIG ----------------------------------------------------
COPY --chown=tool:tool config/nvim/ /home/tool/.config/nvim/

RUN nvim --headless "+Lazy! sync" +qa && \
    nvim --headless "+TSInstall python lua bash sql java xml json yaml markdown markdown_inline" +qa && \
    nvim --headless "+MasonInstall pyright lua-language-server" +qa

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

# --- CLAUDE CODE PLUGINS ------------------------------------------------
COPY --chown=tool:tool skill-marketplace/ /home/tool/.local/share/skill-marketplace/

ENV NPM_CONFIG_PREFIX=/home/tool/.npm-global
ENV PATH=$PATH:/home/tool/.npm-global/bin

# --- AI TOOLS ---------------------------------------------------------
# Install Pi coding agent globally
RUN npm install -g @mariozechner/pi-coding-agent

RUN curl -fsSL https://claude.ai/install.sh | bash

# Install Superpowers plugin
RUN claude plugin marketplace add obra/superpowers-marketplace 2>/dev/null || true && \
    claude plugin install superpowers@superpowers-marketplace 2>/dev/null || true

# Install distill-rag-bridge plugin from local marketplace
RUN claude plugin marketplace add /home/tool/.local/share/skill-marketplace 2>/dev/null || true && \
    claude plugin install distill-rag-bridge@distill-rag-bridge 2>/dev/null || true

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
