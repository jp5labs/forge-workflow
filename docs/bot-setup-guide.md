# Bot Fleet Setup Guide

This guide walks through setting up a bot fleet from scratch using Forge. By the end, you'll have one or more Claude Code bots running in Docker containers with Discord integration, Tailscale SSH access, and autonomous or supervised delivery workflows.

## Prerequisites

- Docker installed and running
- GitHub CLI (`gh`) authenticated
- A GitHub repo initialized with `forge init`
- (Optional) Discord bot tokens — one per bot
- (Optional) Tailscale account for remote SSH access

## 1. Initialize Forge in Your Repo

If you haven't already:

```bash
pip install "forge-workflow @ git+https://github.com/jp5labs/forge-workflow.git"
cd your-repo
forge init
```

This creates `.forge/config.yaml` and scaffolds the hooks, skills, and Docker infrastructure.

## 2. Add Bots

Use `forge bot add` to register each bot:

```bash
forge bot add alex \
  --role "Lead Engineer" \
  --github-account alexnova-dev \
  --email alex@example.com

forge bot add marcus \
  --role "Systems Architect" \
  --github-account marcuswei-dev \
  --email marcus@example.com
```

Each call:
- Adds the bot to `.forge/config.yaml` under `bots:`
- Creates a skeleton identity file at `bots/<name>-identity.md`
- Creates an env template at `bots/<name>.env`

Verify with:

```bash
forge bot list
```

## 3. Configure Bot Identity

Edit `bots/<name>-identity.md` to define the bot's persona, perspective, and voice. This file is mounted into the container and appended to Claude's system prompt at launch. A bot's identity describes its default lens — it doesn't limit what it can do.

## 4. Configure Bot Environment

Edit `bots/<name>.env` for each bot. Key variables:

| Variable | Purpose | Required |
|----------|---------|----------|
| `BOT_NAME` | Bot identifier (matches config name) | Yes |
| `GIT_USER_NAME` | Git commit author name | Yes |
| `GIT_USER_EMAIL` | Git commit author email | Yes |
| `TAILSCALE_HOSTNAME` | Tailscale node name (default: `claude-<name>`) | No |
| `DISCORD_BOT_TOKEN` | Discord bot token for the Channels plugin | No |
| `DISCORD_WEBHOOK_URL` | Webhook for lifecycle notifications | No |
| `CLAUDE_MODE` | `autonomous` or `supervised` (default: `autonomous`) | No |
| `CB_FAILURE_LIMIT` | Circuit breaker: max consecutive failures (default: 5) | No |

The `.env` files are gitignored — secrets stay local.

## 5. Launch

Launch a single bot:

```bash
forge bot launch alex
```

Launch the entire fleet:

```bash
forge bot launch --all
```

Options:
- `--mode autonomous` / `--mode supervised` — override the mode from `.env`
- `--bare` — launch without the Discord Channels plugin

## 6. First-Time Authentication

On the first launch, each bot container needs GitHub and Claude authentication:

```bash
# Open a shell in the container
docker exec -it --user claude claude-alex bash

# Authenticate
gh auth login        # GitHub CLI
claude /login        # Claude Code

# Exit and re-launch
exit
forge bot launch alex
```

You can also run `forge bot setup-guide <name>` for a step-by-step checklist.

## 7. Discord Integration (Optional)

### Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new Application for each bot
3. Under **Bot**, copy the bot token
4. Enable **Message Content Intent** under Privileged Gateway Intents
5. Invite the bot to your server with appropriate permissions

### Configure in Container

```bash
# Attach to the bot's Claude session
forge bot attach alex

# In Claude, configure Discord
/discord:configure
# Paste the bot token when prompted

# Exit and re-launch so the plugin loads
/exit
forge bot restart alex
```

### Enable Channel Access

```bash
forge bot attach alex

# Send the bot a DM in Discord — it shows a pairing code
# In the Claude session:
/discord:access
# Approve the pending pairing
# Enable access for group channels by chat ID
# Disable pairing mode when done

# Detach (keep bot running)
# Press: Ctrl+B then D
```

## 8. Day-to-Day Operations

| Command | Purpose |
|---------|---------|
| `forge bot status` | Check running state of all bots |
| `forge bot attach <name>` | Attach to a bot's tmux session |
| `forge bot stop <name>` | Graceful shutdown |
| `forge bot stop --all` | Stop the entire fleet |
| `forge bot restart <name>` | Stop + relaunch |
| `forge bot launch <name> --bare` | Launch without Discord |

**Detaching from a session:** Press `Ctrl+B` then `D`. This leaves the bot running.

## 9. Operating Modes

### Autonomous Mode

Bots run with `--dangerously-skip-permissions` and rely on circuit breakers for safety:

- **Sequential failure breaker** — halts after N consecutive Bash failures (default: 5)
- **Destructive git breaker** — blocks force-push, reset --hard, etc.
- **Secret escalation breaker** — halts after 3 secret detections in one session

Set `CLAUDE_MODE=autonomous` in the bot's `.env` file or pass `--mode autonomous` to launch.

### Supervised Mode

Bots run with `--accept-edits` and require manual approval for tool calls. Use this when you want to watch and approve each action.

Set `CLAUDE_MODE=supervised` or pass `--mode supervised` to launch.

## 10. Tailscale SSH Access

Each bot container runs Tailscale for remote SSH access. On first launch:

```bash
docker exec -it claude-alex tailscale up --ssh
```

Follow the authentication URL. Once connected, SSH from any device on your tailnet:

```bash
ssh claude@claude-alex
```

## 11. Troubleshooting

### Bot won't start

```bash
forge doctor              # Check environment health
docker logs claude-alex   # Check container logs
```

### Bot is unresponsive

```bash
forge bot status          # Check if container is running
forge bot restart alex    # Stop and relaunch
```

### Circuit breaker tripped

The bot halts and reports which breaker tripped (via Discord or console). Read `tmp/circuit-breaker-halt.json` in the workspace for details. Fix the underlying issue, then relaunch.

### Discord not responding

1. Verify the token is set in `bots/<name>.env`
2. Ensure the bot was launched without `--bare`
3. Check that channel access was approved via `/discord:access`
4. Restart: `forge bot restart <name>`

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│  Host Machine                               │
│                                             │
│  forge bot launch --all                     │
│    ├── claude-alex   (Docker container)     │
│    │   ├── Claude Code (tmux session)       │
│    │   ├── Tailscale SSH                    │
│    │   ├── Discord Channels plugin          │
│    │   └── forge-workflow (pip)             │
│    ├── claude-marcus (Docker container)     │
│    │   └── ...                              │
│    └── claude-steph  (Docker container)     │
│        └── ...                              │
│                                             │
│  .forge/config.yaml  ← fleet configuration  │
│  bots/*.env          ← secrets (gitignored) │
│  bots/*-identity.md  ← persona definitions  │
└─────────────────────────────────────────────┘
```

Each container mounts the workspace volume, so all bots operate on the same repo. Coordination happens through GitHub (issues, PRs, branches) — bots do not communicate directly.
