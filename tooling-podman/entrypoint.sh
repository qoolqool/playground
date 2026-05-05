#!/bin/bash
set -e

# --- Ownership Fix ---
# Since we are user 'tool', we use sudo to ensure we own the mounted project.
# This allows Claude Code and your scripts to write to the host-mounted folder.
echo "Fixing /project permissions..."
sudo chown -R tool:tool /project 2>/dev/null || true

# --- Banner ---
echo "╔========================================================╗"
echo "|    Hole Punching POC - Tooling Container               |"
echo "|    Claude Code Bridge → POC Infrastructure             |"
echo "╠========================================================╣"
echo "|  Infrastructure (2026-02-24 topology):                 |"
echo "|    Headscale:  http://10.10.1.5:8080                   |"
echo "|    DERP Relay: https://10.10.1.11:443                  |"
echo "|    STUN:       10.10.1.11:3478/udp                     |"
echo "╚========================================================╝"

# --- Inject Aliases ---
# We inject these into the current user's .bashrc if they aren't there.
if ! grep -q "POC shortcuts" ~/.bashrc; then
cat << 'ALIASES' >> ~/.bashrc

# POC shortcuts
alias hs-setup='/project/scripts/headscale-wg/setup.sh'
alias hs-test='/project/scripts/headscale-wg/test.sh'
alias hs-status='/project/scripts/headscale-wg/observe.sh status'
alias hs-traffic='/project/scripts/headscale-wg/observe.sh traffic'
alias hs-nat='/project/scripts/headscale-wg/observe.sh nat'
alias hs-derp='/project/scripts/headscale-wg/observe.sh derp'

# Peer shortcuts (routing through Podman/Docker socket)
alias peer-a='docker exec -it peer-a'
alias peer-b='docker exec -it peer-b'
alias peer-a-status='docker exec peer-a tailscale status'
alias peer-b-status='docker exec peer-b tailscale status'
alias peer-a-netcheck='docker exec peer-a tailscale netcheck'
alias peer-b-netcheck='docker exec peer-b tailscale netcheck'

# Headscale shortcuts (routes via exec to avoid gRPC auth issues)
alias hs='docker exec headscale headscale'
alias hs-nodes='docker exec headscale headscale nodes list'
alias hs-routes='docker exec headscale headscale routes list'

# Navigation
alias docs='cd /project/docs'
alias scripts='cd /project/scripts'
alias glow='glow --width 0'
ALIASES
fi

exec "$@"
