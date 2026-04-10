"""Bot configuration management — add, list, remove bots in .forge/config.yaml."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

# Docker container names must match [a-zA-Z0-9][a-zA-Z0-9_.-]
_BOT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


@dataclass
class BotEntry:
    """A bot definition from config."""

    name: str
    role: str
    github_account: str
    email: str


def _load_config(root: Path) -> dict:
    """Load .forge/config.yaml from repo root."""
    cfg_path = root / ".forge" / "config.yaml"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"No config found at {cfg_path}")
    with open(cfg_path) as f:
        return yaml.safe_load(f) or {}


def _save_config(root: Path, config: dict) -> None:
    """Write config back to .forge/config.yaml."""
    cfg_path = root / ".forge" / "config.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def list_bots(root: Path) -> list[BotEntry]:
    """Return all configured bots."""
    config = _load_config(root)
    bots = config.get("bots") or []
    return [
        BotEntry(
            name=b["name"],
            role=b.get("role", ""),
            github_account=b.get("github_account", ""),
            email=b.get("email", ""),
        )
        for b in bots
    ]


def add_bot(
    root: Path,
    *,
    name: str,
    role: str,
    github_account: str,
    email: str,
    bots_dir: Optional[Path] = None,
) -> BotEntry:
    """Add a bot to config and scaffold identity + env files."""
    if not _BOT_NAME_RE.match(name):
        raise ValueError(
            f"Invalid bot name '{name}'. "
            "Names must match [a-zA-Z0-9][a-zA-Z0-9_.-] (Docker container name rules)."
        )

    config = _load_config(root)
    bots = config.get("bots") or []

    if any(b["name"] == name for b in bots):
        raise ValueError(f"Bot '{name}' already exists in config.")

    entry = {
        "name": name,
        "role": role,
        "github_account": github_account,
        "email": email,
    }
    bots.append(entry)
    config["bots"] = bots
    _save_config(root, config)

    # Scaffold files
    target_dir = bots_dir or (root / "bots")
    target_dir.mkdir(parents=True, exist_ok=True)
    _scaffold_identity(target_dir, name=name, role=role, github_account=github_account, email=email)
    _scaffold_env(target_dir, name=name, email=email)

    # Update managed doc sections
    _update_docs(root)

    return BotEntry(name=name, role=role, github_account=github_account, email=email)


def remove_bot(root: Path, name: str) -> None:
    """Remove a bot from config. Does not delete identity/env files."""
    config = _load_config(root)
    bots = config.get("bots") or []
    original_len = len(bots)
    bots = [b for b in bots if b["name"] != name]
    if len(bots) == original_len:
        raise ValueError(f"Bot '{name}' not found in config.")
    config["bots"] = bots
    _save_config(root, config)

    # Update managed doc sections
    _update_docs(root)


def _update_docs(root: Path) -> None:
    """Update managed sections in CLAUDE.md and AGENTS.md."""
    try:
        from forge_workflow.lib.scaffold import scaffold_docs

        bots = list_bots(root)
        scaffold_docs(root, bots=bots)
    except Exception:
        pass  # Non-blocking — doc updates should not break bot operations


def _scaffold_identity(
    bots_dir: Path, *, name: str, role: str, github_account: str, email: str
) -> None:
    """Create a starter identity markdown file."""
    display_name = name.capitalize()
    content = f"""# {display_name} — {role}

## Identity

You are {display_name}. Your GitHub account is `{github_account}`, authenticated via
`gh auth login`. Git identity is pre-configured in your container — do
not override it.

Your commits are authored as "{display_name} (bot)" <{email}>.

## Core Principle

You are a fully capable software engineer. Your role describes your
default perspective — what you notice first and where you add the most
value. It does not limit what you can do.

## Perspective

Your default lens as {role}:

- (customize this section for your bot's perspective)

## Voice

- (customize this section for your bot's communication style)

## Fleet Rules

- Never merge your own PRs
- Never merge without explicit delegation
- Use `needs-decision` label to escalate
- Claim work via GitHub Assignee field
"""
    (bots_dir / f"{name}-identity.md").write_text(content)


def _scaffold_env(bots_dir: Path, *, name: str, email: str) -> None:
    """Create a starter .env file for the bot."""
    display_name = name.capitalize()
    content = f"""BOT_NAME={name}
GIT_USER_NAME="{display_name} (bot)"
GIT_USER_EMAIL="{email}"
TAILSCALE_HOSTNAME=claude-{name}
DISCORD_WEBHOOK_URL=
DISCORD_BOT_TOKEN=
CLAUDE_MODE=autonomous
CB_FAILURE_LIMIT=5
"""
    (bots_dir / f"{name}.env").write_text(content)
