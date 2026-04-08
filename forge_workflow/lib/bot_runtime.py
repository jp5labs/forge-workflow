"""Bot runtime management — Docker container lifecycle, tmux sessions."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from forge_workflow.lib.bot_config import BotEntry


class DockerError(RuntimeError):
    """Raised when a Docker operation fails."""


IMAGE_NAME = "claude-workspace"
GRACEFUL_TIMEOUT = 30
SIGTERM_TIMEOUT = 10

# Default plugins to install in bot containers
DEFAULT_PLUGINS = [
    "discord@claude-plugins-official",
    "code-review@claude-plugins-official",
    "code-simplifier@claude-plugins-official",
    "superpowers@claude-plugins-official",
    "feature-dev@claude-plugins-official",
]


# ---------------------------------------------------------------------------
# Low-level Docker helpers
# ---------------------------------------------------------------------------


def _docker_run(args: list[str], *, timeout: int = 30) -> str:
    """Run a docker command and return stdout. Raises DockerError on failure."""
    try:
        result = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise DockerError("Docker is not installed or not in PATH.")
    except subprocess.TimeoutExpired:
        raise DockerError(f"Docker command timed out: docker {' '.join(args)}")

    if result.returncode != 0:
        raise DockerError(f"Docker command failed: {result.stderr.strip()}")
    return result.stdout


def _docker_run_ok(args: list[str], *, timeout: int = 30) -> tuple[bool, str]:
    """Run a docker command, return (success, stdout). Does not raise."""
    try:
        result = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, ""


# ---------------------------------------------------------------------------
# Naming and status
# ---------------------------------------------------------------------------


def container_name(bot_name: str) -> str:
    """Return the Docker container name for a bot."""
    return f"claude-{bot_name}"


def volume_names(bot_name: str) -> dict[str, str]:
    """Return the named volume mapping for a bot."""
    prefix = f"claude-{bot_name}"
    return {
        "workspace": f"{prefix}-workspace",
        "config": f"{prefix}-config",
        "gh": f"{prefix}-gh",
        "tailscale": f"{prefix}-tailscale",
    }


def is_container_exists(bot_name: str) -> bool:
    """Check if a container exists (running or stopped)."""
    cname = container_name(bot_name)
    ok, stdout = _docker_run_ok(["ps", "-a", "--format", "{{.Names}}"])
    return cname in stdout.splitlines() if ok else False


def is_container_running(bot_name: str) -> bool:
    """Check if a container is currently running."""
    cname = container_name(bot_name)
    ok, stdout = _docker_run_ok(["ps", "--format", "{{.Names}}"])
    return cname in stdout.splitlines() if ok else False


def container_status(bot_name: str) -> dict:
    """Get container status details: state, uptime, health."""
    cname = container_name(bot_name)
    ok, stdout = _docker_run_ok([
        "ps", "-a", "--filter", f"name=^{cname}$",
        "--format", "{{.Status}}|{{.State}}|{{.RunningFor}}",
    ])
    if not ok or not stdout.strip():
        return {"state": "not_created", "status": "", "uptime": ""}
    parts = stdout.strip().split("|")
    return {
        "state": parts[1] if len(parts) > 1 else "unknown",
        "status": parts[0] if len(parts) > 0 else "",
        "uptime": parts[2] if len(parts) > 2 else "",
    }


# ---------------------------------------------------------------------------
# Internal process checks
# ---------------------------------------------------------------------------


def _has_tmux_session(bot_name: str) -> bool:
    """Check if a tmux session exists in the container."""
    cname = container_name(bot_name)
    ok, _ = _docker_run_ok([
        "exec", "--user", "claude", cname,
        "tmux", "has-session", "-t", bot_name,
    ])
    return ok


def _is_claude_running(bot_name: str) -> bool:
    """Check if a claude process is running in the container."""
    cname = container_name(bot_name)
    ok, _ = _docker_run_ok([
        "exec", cname, "bash", "-c",
        "ps -eo comm | grep -qw claude",
    ])
    return ok


# ---------------------------------------------------------------------------
# Container lifecycle
# ---------------------------------------------------------------------------


def create_container(
    bot: BotEntry,
    *,
    mode: str = "autonomous",
    cb_failure_limit: int = 5,
    workspace_owner_home: Optional[str] = None,
) -> None:
    """Create a new Docker container for a bot.

    Does NOT start Claude — only creates the container with infrastructure.
    """
    if is_container_exists(bot.name):
        raise DockerError(f"Container {container_name(bot.name)} already exists.")

    vols = volume_names(bot.name)
    cname = container_name(bot.name)
    tailscale_hostname = f"claude-{bot.name}"

    env_args = [
        "-e", f"BOT_NAME={bot.name}",
        "-e", f"TAILSCALE_HOSTNAME={tailscale_hostname}",
        "-e", f"CLAUDE_MODE={mode}",
        "-e", f"CB_FAILURE_LIMIT={cb_failure_limit}",
    ]
    if workspace_owner_home:
        env_args.extend(["-e", f"WORKSPACE_OWNER_HOME={workspace_owner_home}"])

    _docker_run([
        "run", "-d",
        "--name", cname,
        "--cap-add=NET_ADMIN",
        "--cap-add=NET_RAW",
        "--device", "/dev/net/tun",
        "-v", f"{vols['workspace']}:/workspace",
        "-v", f"{vols['config']}:/home/claude/.claude",
        "-v", f"{vols['gh']}:/home/claude/.config/gh",
        "-v", f"{vols['tailscale']}:/var/lib/tailscale",
        *env_args,
        "--restart", "unless-stopped",
        IMAGE_NAME,
    ], timeout=60)


def start_container(bot_name: str) -> None:
    """Start a stopped container."""
    if not is_container_exists(bot_name):
        raise DockerError(f"Container {container_name(bot_name)} does not exist.")
    if is_container_running(bot_name):
        return
    _docker_run(["start", container_name(bot_name)])


def stop_container(bot_name: str, *, graceful: bool = True) -> None:
    """Stop a bot container with optional graceful shutdown.

    Graceful shutdown follows the 3-phase protocol:
    1. Send /exit via tmux (triggers SessionEnd hooks)
    2. SIGTERM after timeout
    3. SIGKILL as last resort
    """
    cname = container_name(bot_name)

    if not is_container_running(bot_name):
        return

    if not graceful:
        _docker_run(["stop", cname], timeout=30)
        return

    # No tmux session — nothing to gracefully exit, just docker stop
    if not _has_tmux_session(bot_name):
        _docker_run(["stop", cname], timeout=30)
        return

    # Tmux exists but claude is not running — kill tmux and docker stop
    if not _is_claude_running(bot_name):
        _docker_run_ok([
            "exec", "--user", "claude", cname,
            "tmux", "kill-session", "-t", bot_name,
        ])
        _docker_run(["stop", cname], timeout=30)
        return

    # Phase 1: Send /exit through tmux
    _docker_run_ok([
        "exec", "--user", "claude", cname,
        "tmux", "send-keys", "-t", bot_name, "/exit", "Enter",
    ])

    for _ in range(GRACEFUL_TIMEOUT):
        if not _is_claude_running(bot_name):
            _docker_run_ok([
                "exec", "--user", "claude", cname,
                "tmux", "kill-session", "-t", bot_name,
            ])
            return
        time.sleep(1)

    # Phase 2: SIGTERM
    _docker_run_ok(["exec", cname, "pkill", "-TERM", "-x", "claude"])

    for _ in range(SIGTERM_TIMEOUT):
        if not _is_claude_running(bot_name):
            _docker_run_ok([
                "exec", "--user", "claude", cname,
                "tmux", "kill-session", "-t", bot_name,
            ])
            return
        time.sleep(1)

    # Phase 3: SIGKILL
    _docker_run_ok(["exec", cname, "pkill", "-9", "-x", "claude"])
    _docker_run_ok([
        "exec", "--user", "claude", cname,
        "tmux", "kill-session", "-t", bot_name,
    ])


# ---------------------------------------------------------------------------
# Launch orchestration sub-steps
# ---------------------------------------------------------------------------


def _ensure_image() -> None:
    """Check the Docker image exists. Raise if not."""
    ok, _ = _docker_run_ok(["image", "inspect", IMAGE_NAME])
    if ok:
        return
    raise DockerError(
        f"Docker image '{IMAGE_NAME}' not found. "
        f"Build it with: docker build -t {IMAGE_NAME} docker/claude-dev/"
    )


def _ensure_container(
    bot: BotEntry,
    *,
    mode: str,
    cb_failure_limit: int = 5,
    workspace_owner_home: Optional[str] = None,
) -> None:
    """Create container if absent, start if stopped."""
    if not is_container_exists(bot.name):
        create_container(
            bot,
            mode=mode,
            cb_failure_limit=cb_failure_limit,
            workspace_owner_home=workspace_owner_home,
        )
        time.sleep(5)
    elif not is_container_running(bot.name):
        start_container(bot.name)
        time.sleep(3)


def _ensure_auth(bot_name: str) -> None:
    """Check GitHub auth is configured in the container."""
    cname = container_name(bot_name)
    ok, _ = _docker_run_ok([
        "exec", "--user", "claude", cname, "gh", "auth", "status",
    ])
    if not ok:
        raise DockerError(
            f"GitHub auth required for {cname}:\n"
            f"  1. docker exec -it --user claude {cname} gh auth login\n"
            f"  2. docker exec -it --user claude {cname} claude /login"
        )
    _docker_run_ok(["exec", "--user", "claude", cname, "gh", "auth", "setup-git"])


def _ensure_repo(bot_name: str, repo_slug: str) -> None:
    """Clone repo if absent, sync with remote."""
    cname = container_name(bot_name)

    ok, _ = _docker_run_ok(["exec", cname, "test", "-d", "/workspace/.git"])
    if not ok:
        _docker_run_ok([
            "exec", "--user", "claude", cname, "bash", "-c",
            "rm -rf /workspace/* /workspace/.[!.]* 2>/dev/null; true",
        ])
        _docker_run([
            "exec", "--user", "claude", cname,
            "gh", "repo", "clone", repo_slug, "/workspace", "--", "--depth=50",
        ], timeout=120)

    _docker_run_ok([
        "exec", "--user", "claude", cname, "bash", "-c",
        "cd /workspace && git fetch --all --prune -q && "
        "git checkout main -q 2>/dev/null && git pull origin main -q",
    ])


def _sync_bot_files(
    bot: BotEntry,
    *,
    bots_dir: Optional[Path] = None,
    secrets_env: Optional[Path] = None,
    memory_src: Optional[Path] = None,
) -> None:
    """Sync identity, secrets, memory, and settings into the container."""
    cname = container_name(bot.name)

    # Git identity — use discrete args to avoid shell injection
    git_name = f"{bot.name.capitalize()} (bot)"
    _docker_run_ok([
        "exec", "--user", "claude", "-w", "/workspace", cname,
        "git", "config", "user.name", git_name,
    ])
    _docker_run_ok([
        "exec", "--user", "claude", "-w", "/workspace", cname,
        "git", "config", "user.email", bot.email,
    ])

    # Identity file
    if bots_dir:
        identity_file = bots_dir / f"{bot.name}-identity.md"
        if identity_file.is_file():
            _docker_run_ok([
                "cp", str(identity_file),
                f"{cname}:/home/claude/.claude/bot-identity.md",
            ])

    # Secrets env
    if secrets_env and secrets_env.is_file():
        _docker_run_ok([
            "cp", str(secrets_env),
            f"{cname}:/workspace/scripts/hooks/.env",
        ])

    # Memory sync
    if memory_src and memory_src.is_dir():
        _docker_run_ok([
            "exec", "--user", "claude", cname,
            "rm", "-rf", "/home/claude/.claude/projects/-workspace/memory",
        ])
        _docker_run_ok([
            "exec", "--user", "claude", cname,
            "mkdir", "-p", "/home/claude/.claude/projects/-workspace/memory",
        ])
        _docker_run_ok([
            "cp", f"{memory_src}/.",
            f"{cname}:/home/claude/.claude/projects/-workspace/memory/",
        ])

    # Generate settings (path is configurable via forge config)
    from forge_workflow.config import get
    settings_script = get("hooks.settings_generator", "/workspace/scripts/generate-settings-local.py")
    _docker_run_ok([
        "exec", "--user", "claude", cname,
        "python3", settings_script,
    ])

    # Fix ownership
    _docker_run_ok([
        "exec", cname, "chown", "-R", "claude:claude", "/home/claude/.claude",
    ])


def _install_plugins(bot_name: str, plugins: Optional[list[str]] = None) -> None:
    """Install Claude Code plugins if not already present."""
    cname = container_name(bot_name)
    plugin_list = plugins or DEFAULT_PLUGINS

    ok, installed = _docker_run_ok([
        "exec", "--user", "claude", cname, "claude", "plugin", "list",
    ])
    installed_str = installed if ok else ""

    for plugin in plugin_list:
        plugin_name = plugin.split("@")[0]
        if f"{plugin_name}@" not in installed_str:
            _docker_run_ok([
                "exec", "--user", "claude", cname,
                "claude", "plugin", "install", plugin, "--scope", "user",
            ])


def _start_claude_session(
    bot: BotEntry,
    *,
    mode: str,
    use_channels: bool,
) -> None:
    """Start Claude in a tmux session inside the container."""
    cname = container_name(bot.name)

    # Stop existing session if present
    if _has_tmux_session(bot.name):
        stop_container(bot.name)
        time.sleep(2)

    # Build command
    cmd_parts = ["cd /workspace && export CLAUDE_REMOTE=1 && claude"]

    if mode == "autonomous":
        cmd_parts.append("--dangerously-skip-permissions")

    if not use_channels:
        cmd_parts.append("--bare")
    else:
        cmd_parts.append("--channels plugin:discord@claude-plugins-official")

    # Append identity file if present
    identity_ok, _ = _docker_run_ok([
        "exec", "--user", "claude", cname,
        "test", "-f", "/home/claude/.claude/bot-identity.md",
    ])
    if identity_ok:
        cmd_parts.append(
            "--append-system-prompt-file /home/claude/.claude/bot-identity.md"
        )

    claude_cmd = " ".join(cmd_parts)

    # Launch in tmux
    _docker_run([
        "exec", "--user", "claude", cname,
        "tmux", "new-session", "-d", "-s", bot.name, claude_cmd,
    ])

    # Auto-confirm consent prompt in autonomous mode
    if mode == "autonomous":
        time.sleep(3)
        _docker_run_ok([
            "exec", "--user", "claude", cname,
            "tmux", "send-keys", "-t", bot.name, "Enter",
        ])
        time.sleep(2)


def _verify_session(bot_name: str) -> None:
    """Verify the tmux session started successfully."""
    for _ in range(5):
        if _has_tmux_session(bot_name):
            return
        time.sleep(1)
    cname = container_name(bot_name)
    raise DockerError(
        f"{bot_name} tmux session failed to start.\n"
        f"  Debug: docker exec -it --user claude {cname} bash\n"
        f"  Auth:  docker exec -it --user claude {cname} claude /login"
    )


# ---------------------------------------------------------------------------
# Top-level launch orchestrator
# ---------------------------------------------------------------------------


def launch_bot(
    bot: BotEntry,
    *,
    mode: str = "autonomous",
    use_channels: bool = True,
    repo_slug: str,
    bots_dir: Optional[Path] = None,
    secrets_env: Optional[Path] = None,
    memory_src: Optional[Path] = None,
    plugins: Optional[list[str]] = None,
    cb_failure_limit: int = 5,
    workspace_owner_home: Optional[str] = None,
) -> None:
    """Full bot launch orchestration — replaces start-claude-remote.sh."""
    _ensure_image()
    _ensure_container(
        bot,
        mode=mode,
        cb_failure_limit=cb_failure_limit,
        workspace_owner_home=workspace_owner_home,
    )
    _ensure_auth(bot.name)
    _ensure_repo(bot.name, repo_slug)
    _sync_bot_files(
        bot, bots_dir=bots_dir, secrets_env=secrets_env, memory_src=memory_src,
    )
    _install_plugins(bot.name, plugins)
    _start_claude_session(bot, mode=mode, use_channels=use_channels)
    _verify_session(bot.name)
