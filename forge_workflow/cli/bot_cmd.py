"""forge bot subcommands — add, list, remove, status, launch, stop, restart, attach."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import typer

from forge_workflow import config as forge_config
from forge_workflow.lib.bot_config import BotEntry, add_bot, list_bots, remove_bot
from forge_workflow.lib.bot_runtime import (
    DockerError,
    container_status,
    launch_bot,
    stop_container,
)

app = typer.Typer(no_args_is_help=True)


def _find_root() -> Path:
    """Find the repo root containing .forge/config.yaml."""
    root = forge_config._find_repo_root()
    if root is None:
        typer.echo("Error: No .forge/config.yaml found.", err=True)
        raise typer.Exit(code=1)
    return root


def _get_bot(root: Path, name: str) -> BotEntry:
    """Look up a bot by name from config. Exits with error if not found."""
    bots = list_bots(root)
    for bot in bots:
        if bot.name == name:
            return bot
    typer.echo(f"Error: Bot '{name}' not found in config.", err=True)
    raise typer.Exit(code=1)


def _read_bot_env_value(bots_dir: Path, bot_name: str, key: str) -> Optional[str]:
    """Read a single value from a bot's .env file."""
    env_file = bots_dir / f"{bot_name}.env"
    if not env_file.is_file():
        return None
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"')
    return None


# ---------------------------------------------------------------------------
# CRUD commands
# ---------------------------------------------------------------------------


@app.command("list")
def bot_list() -> None:
    """Show configured bots from .forge/config.yaml."""
    root = _find_root()
    bots = list_bots(root)
    if not bots:
        typer.echo("No bots configured. Run 'forge bot add <name>' to add one.")
        return

    typer.echo(f"{'Name':<15} {'Role':<25} {'GitHub':<20} {'Email'}")
    typer.echo("-" * 80)
    for bot in bots:
        typer.echo(f"{bot.name:<15} {bot.role:<25} {bot.github_account:<20} {bot.email}")


@app.command("add")
def bot_add(
    name: str = typer.Argument(help="Bot name slug (e.g. 'marcus')"),
    role: str = typer.Option(..., "--role", "-r", help="Human-readable role"),
    github_account: str = typer.Option(
        ..., "--github-account", "-g", help="GitHub username"
    ),
    email: str = typer.Option(..., "--email", "-e", help="Git commit email"),
    bots_dir: Optional[Path] = typer.Option(
        None, "--bots-dir", help="Directory for identity/env files"
    ),
) -> None:
    """Add a new bot — scaffolds identity file, adds to config, creates env template."""
    root = _find_root()
    target_dir = bots_dir or (root / "bots")
    try:
        bot = add_bot(
            root,
            name=name,
            role=role,
            github_account=github_account,
            email=email,
            bots_dir=target_dir,
        )
        typer.echo(f"Bot '{bot.name}' configured.")
        typer.echo(f"  Identity: {target_dir / f'{name}-identity.md'}")
        typer.echo(f"  Env:      {target_dir / f'{name}.env'}")
        typer.echo(f"\nEdit the identity file, then run: forge bot launch {name}")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command("remove")
def bot_remove(
    name: str = typer.Argument(help="Bot name to remove"),
) -> None:
    """Remove a bot from config. Does not delete identity/env files."""
    root = _find_root()
    try:
        remove_bot(root, name)
        typer.echo(f"Bot '{name}' removed from config.")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Runtime commands
# ---------------------------------------------------------------------------


@app.command("status")
def bot_status() -> None:
    """Show runtime state of configured bots: running/stopped, uptime."""
    root = _find_root()
    bots = list_bots(root)
    if not bots:
        typer.echo("No bots configured.")
        return

    typer.echo(f"{'Name':<15} {'State':<12} {'Status'}")
    typer.echo("-" * 60)
    for bot in bots:
        status = container_status(bot.name)
        typer.echo(f"{bot.name:<15} {status['state']:<12} {status['status']}")


@app.command("launch")
def bot_launch(
    name: Optional[str] = typer.Argument(None, help="Bot name to launch"),
    all_bots: bool = typer.Option(False, "--all", help="Launch all configured bots"),
    mode: Optional[str] = typer.Option(
        None, "--mode", "-m", help="autonomous or supervised"
    ),
    bare: bool = typer.Option(
        False, "--bare", help="Launch without Discord Channels plugin"
    ),
) -> None:
    """Start bot container(s) — reads all config from .forge/config.yaml."""
    root = _find_root()
    repo_slug = forge_config.repo_slug()

    if not all_bots and name is None:
        typer.echo("Error: Specify a bot name or use --all.", err=True)
        raise typer.Exit(code=1)

    bots = list_bots(root) if all_bots else [_get_bot(root, name)]

    # Determine bots directory (where identity/env files live)
    bots_dir = root / "bots"
    if not bots_dir.is_dir():
        bots_dir = root / "docker" / "claude-dev" / "bots"

    for bot in bots:
        bot_mode = (
            mode
            or _read_bot_env_value(bots_dir, bot.name, "CLAUDE_MODE")
            or "autonomous"
        )
        typer.echo(f"Launching {bot.name} (mode={bot_mode})...")
        try:
            launch_bot(
                bot=bot,
                mode=bot_mode,
                use_channels=not bare,
                repo_slug=repo_slug,
                bots_dir=bots_dir,
            )
            cname = f"claude-{bot.name}"
            typer.echo(f"  {bot.name} started.")
            typer.echo(
                f"  Attach: docker exec -it --user claude {cname} tmux attach -t {bot.name}"
            )
        except DockerError as e:
            typer.echo(f"Error launching {bot.name}: {e}", err=True)
            if not all_bots:
                raise typer.Exit(code=1)


@app.command("stop")
def bot_stop(
    name: Optional[str] = typer.Argument(None, help="Bot name to stop"),
    all_bots: bool = typer.Option(False, "--all", help="Stop all configured bots"),
) -> None:
    """Stop bot container(s) with graceful shutdown."""
    root = _find_root()

    if not all_bots and name is None:
        typer.echo("Error: Specify a bot name or use --all.", err=True)
        raise typer.Exit(code=1)

    bots = list_bots(root) if all_bots else [_get_bot(root, name)]

    for bot in bots:
        typer.echo(f"Stopping {bot.name}...")
        stop_container(bot.name)
        typer.echo(f"  {bot.name} stopped.")


@app.command("restart")
def bot_restart(
    name: Optional[str] = typer.Argument(None, help="Bot name to restart"),
    all_bots: bool = typer.Option(False, "--all", help="Restart all configured bots"),
    mode: Optional[str] = typer.Option(
        None, "--mode", "-m", help="autonomous or supervised"
    ),
    bare: bool = typer.Option(
        False, "--bare", help="Launch without Discord Channels plugin"
    ),
) -> None:
    """Stop + relaunch bot(s) with fresh tmux session."""
    root = _find_root()

    if not all_bots and name is None:
        typer.echo("Error: Specify a bot name or use --all.", err=True)
        raise typer.Exit(code=1)

    bots = list_bots(root) if all_bots else [_get_bot(root, name)]

    for bot in bots:
        typer.echo(f"Stopping {bot.name}...")
        stop_container(bot.name)

    # Re-launch
    bot_launch(name=name, all_bots=all_bots, mode=mode, bare=bare)


@app.command("attach")
def bot_attach(
    name: str = typer.Argument(help="Bot name to attach to"),
) -> None:
    """Attach to a bot's tmux session (interactive)."""
    root = _find_root()
    _get_bot(root, name)  # Validate bot exists in config
    cname = f"claude-{name}"
    typer.echo(f"Attaching to {name}... (Ctrl+B then D to detach)")
    subprocess.run(
        ["docker", "exec", "-it", "--user", "claude", cname, "tmux", "attach", "-t", name],
    )
