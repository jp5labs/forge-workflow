FROM ubuntu:24.04

# Prevent interactive prompts during install
ENV DEBIAN_FRONTEND=noninteractive

# Core dependencies
RUN apt-get update && apt-get install -y \
    curl git python3 python3-pip python3-venv \
    tmux fzf jq unzip wget ca-certificates \
    openssh-server openssh-client iptables \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

# Install Node.js 22 LTS (required for Claude Code and MCP servers)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for Claude Code (--dangerously-skip-permissions requires non-root)
RUN useradd -m -s /bin/bash -u 1001 claude

# Install Tailscale (SSH access from phone/anywhere on tailnet)
RUN curl -fsSL https://tailscale.com/install.sh | sh

# Install Bun (required for Channels plugins) — as claude user
USER claude
RUN curl -fsSL https://bun.sh/install | bash
USER root
ENV PATH="/home/claude/.bun/bin:${PATH}"

# Install Claude Code — npm bootstrap as root, native binary as claude user.
# Clean /home/claude/.claude after build so it doesn't overwrite the named volume on mount.
RUN npm install -g @anthropic-ai/claude-code
USER claude
RUN claude install --force && rm -rf /home/claude/.claude
USER root
RUN npm uninstall -g @anthropic-ai/claude-code
ENV PATH="/home/claude/.local/bin:${PATH}"

# Install Python tooling (ruff for formatting hook)
RUN pip3 install ruff --break-system-packages

# Pre-seed GitHub SSH known_hosts for both root and claude users
RUN mkdir -p /root/.ssh /home/claude/.ssh \
    && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null \
    && cp /root/.ssh/known_hosts /home/claude/.ssh/known_hosts \
    && chown -R claude:claude /home/claude/.ssh

# SSH configuration (Tailscale SSH is primary access — disable password auth)
RUN mkdir -p /var/run/sshd \
    && echo "PermitRootLogin no" >> /etc/ssh/sshd_config \
    && echo "PasswordAuthentication no" >> /etc/ssh/sshd_config

# Git defaults
RUN git config --global init.defaultBranch main
USER claude
RUN git config --global init.defaultBranch main
USER root

# Working directory
WORKDIR /workspace

# Startup script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
