#!/bin/bash
# Claude Code container entrypoint
# Starts infrastructure services and keeps container alive.
# Repo clone and Claude launch are handled by forge bot launch (or start-claude-remote.sh).

WORKSPACE="/workspace"

# Mark repo as safe (if it exists)
git config --global --add safe.directory "$WORKSPACE"
su -c 'git config --global --add safe.directory /workspace' claude

# Mirror host path so project settings.json paths resolve identically.
# Uses WORKSPACE_OWNER_HOME env var (set by forge bot launch) if available.
OWNER_HOME="${WORKSPACE_OWNER_HOME:-}"
if [[ -n "$OWNER_HOME" ]]; then
    mkdir -p "$(dirname "$OWNER_HOME")"
    ln -sfn "$WORKSPACE" "$OWNER_HOME"
fi

# Mirror workspace path for claude user
mkdir -p /home/claude/projects
ln -sfn "$WORKSPACE" /home/claude/projects/workspace

# Ensure claude user owns workspace (fast-path: skip if already owned)
if [ "$(stat -c '%U' /workspace 2>/dev/null)" != "claude" ]; then
    chown -R claude:claude /workspace
fi

# Ensure claude user owns mounted volumes (Docker creates them as root)
chown -R claude:claude /home/claude/.claude 2>/dev/null || true
chown -R claude:claude /home/claude/.config 2>/dev/null || true

# --- Start Tailscale ---
mkdir -p /var/run/tailscale /var/lib/tailscale
tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscale/tailscaled.sock &
sleep 2

TS_HOSTNAME="${TAILSCALE_HOSTNAME:-claude-dev}"
CONTAINER="${BOT_NAME:+claude-$BOT_NAME}"
CONTAINER="${CONTAINER:-claude-dev}"

tailscale up --hostname="$TS_HOSTNAME" --ssh --timeout=10s 2>&1 || {
    echo "WARNING: Tailscale auth not complete. Run 'docker exec -it $CONTAINER tailscale up --ssh' to authenticate."
}

# --- Install JP5 CLI (editable, from workspace volume) ---
if [[ -f "$WORKSPACE/pyproject.toml" ]]; then
    pip install --break-system-packages --ignore-installed cryptography -e "$WORKSPACE" -q 2>/dev/null || true
fi

# --- Generate settings.local.json (autonomous/supervised mode) ---
if [[ -f "$WORKSPACE/scripts/generate-settings-local.py" ]]; then
    su -c "CLAUDE_MODE=${CLAUDE_MODE:-autonomous} python3 $WORKSPACE/scripts/generate-settings-local.py" claude || true
else
    su -c "CLAUDE_MODE=${CLAUDE_MODE:-autonomous} REPO_ROOT=$WORKSPACE python3 -m forge_workflow.lib.settings_generator" claude || true
fi

# --- Start SSH server ---
/usr/sbin/sshd

# --- Lifecycle notifications ---

notify_lifecycle() {
    local event="$1"
    local script="$WORKSPACE/scripts/hooks/notify.sh"
    if [[ -f "$script" ]]; then
        bash "$script" "$event" &
    fi
}

cleanup() {
    notify_lifecycle container-stop
    wait
    exit 0
}
trap cleanup SIGTERM SIGINT

# --- Ready ---
echo "$CONTAINER ready."
echo "  First-time setup:"
echo "    forge bot attach ${BOT_NAME:-dev}  (then run: gh auth login && claude /login)"
echo "  Launch:"
echo "    forge bot launch ${BOT_NAME:-dev}"

notify_lifecycle container-start

# Keep container alive (not exec — trap must remain active)
sleep infinity &
wait $!
