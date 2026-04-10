"""Doc sections — render managed Markdown sections from bot config data.

Each function returns a string of Markdown content (without markers)
to be used with doc_manager.upsert_section().
"""

from __future__ import annotations

from forge_workflow.lib.bot_config import BotEntry


def render_claude_remote_sessions(bots: list[BotEntry]) -> str:
    """Render the Remote Sessions table for CLAUDE.md."""
    lines = [
        "### Remote Sessions (Docker + Discord)",
        "",
        "| Bot | Launch | Attach |",
        "|-----|--------|--------|",
        (
            "| Generic | `forge bot launch` "
            "| `docker exec -it claude-dev tmux attach -t claude` |"
        ),
    ]
    for bot in bots:
        display = bot.name.capitalize()
        lines.append(
            f"| {display} | `forge bot launch {bot.name}` "
            f"| `docker exec -it claude-{bot.name} tmux attach -t {bot.name}` |"
        )
    lines.extend([
        "",
        "Launch all named bots: `forge bot launch --all`",
        "Stop a bot: `forge bot stop <name>`",
        "Detach: `Ctrl+B` then `D`",
        "",
    ])
    return "\n".join(lines) + "\n"


def render_claude_bot_identity(bots: list[BotEntry]) -> str:
    """Render the Bot Identity section for CLAUDE.md."""
    lines = [
        "### Bot Identity",
        "",
        "Named bots receive persona identity via Claude Code's "
        "`--append-system-prompt-file` flag, passed at container launch "
        "from `bots/{name}-identity.md`. The identity file is synced into "
        "the container at `/home/claude/.claude/bot-identity.md` and appended "
        "to the system prompt when Claude starts. Identity files define "
        "perspective and voice as soft defaults — any bot can do any work "
        "the operator assigns. The generic `claude-dev` instance receives "
        "no identity. See `AGENTS.md` for fleet coordination rules.",
        "",
    ]
    return "\n".join(lines) + "\n"


def render_agents_bot_fleet(bots: list[BotEntry]) -> str:
    """Render the bot fleet table for AGENTS.md."""
    lines = [
        "### Bot Fleet",
        "",
        "| Bot | Container | GitHub Account | Default Perspective |",
        "|-----|-----------|----------------|---------------------|",
        "| Generic | `claude-dev` | (shared) | Any work |",
    ]
    for bot in bots:
        display = bot.name.capitalize()
        lines.append(
            f"| {display} | `claude-{bot.name}` "
            f"| `{bot.github_account}` | {bot.role} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def render_agents_bot_identity(bots: list[BotEntry]) -> str:
    """Render the Bot Identity section for AGENTS.md."""
    lines = [
        "### Bot Identity",
        "",
        "Bot identity is injected at container launch via Claude Code's "
        "`--append-system-prompt-file` flag. Identity files live at "
        "`bots/{name}-identity.md`, are synced into the container at "
        "`/home/claude/.claude/bot-identity.md`, and appended to the system "
        "prompt when Claude starts. They define **soft lanes** — default "
        "perspective and tendencies, not rigid authority boundaries. Any bot "
        "can do any work when assigned by the operator.",
        "",
    ]
    return "\n".join(lines) + "\n"


def render_agents_mode_table(bots: list[BotEntry]) -> str:
    """Render the Autonomous vs Supervised Mode section for AGENTS.md."""
    lines = [
        "### Autonomous vs Supervised Mode",
        "",
        "| Mode | Permission | Safety Layer | Default |",
        "|------|-----------|-------------|---------|",
        (
            "| **autonomous** | `--dangerously-skip-permissions` "
            "| Hook-based denies + circuit breakers | Yes |"
        ),
        (
            "| **supervised** | `acceptEdits` "
            "| Full hook set + allow/deny lists | No |"
        ),
        "",
        "Launch flags:",
    ]
    if bots:
        first = bots[0].name
        lines.append(f"- `forge bot launch {first}` — autonomous (default)")
        lines.append(
            f"- `forge bot launch {first} --mode supervised` — supervised mode"
        )
    else:
        lines.append("- `forge bot launch <name>` — autonomous (default)")
        lines.append(
            "- `forge bot launch <name> --mode supervised` — supervised mode"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def render_workflow_choreography() -> str:
    """Render the forge delivery workflow choreography section."""
    lines = [
        "### Delivery Workflow",
        "",
        "All changes go through PRs. Never commit directly to main.",
        "",
        "#### Workflow Modes",
        "",
        "| Mode | Steps | Use when |",
        "|------|-------|----------|",
        (
            "| **full** | discover → shape → assess → plan → start → "
            "implement → deliver → cleanup | Architecture-touching, multi-file |"
        ),
        (
            "| **standard** | plan → start → implement → deliver → cleanup "
            "| Normal feature work |"
        ),
        "| **quick** | start → implement → deliver | Config, docs, single-file |",
        "| **ship** | commit → push → PR | Already on branch |",
        "",
        "#### Skills Reference",
        "",
        "| Skill | Purpose |",
        "|-------|---------|",
        "| `/forge-discover` | Idea triage and complexity gating |",
        "| `/forge-shape` | Scope issues with acceptance criteria |",
        "| `/forge-assess` | Pre-implementation evaluation gate |",
        "| `/forge-plan` | Full implementation planning session |",
        "| `/forge-start` | Sync main, create branch, scaffold templates |",
        "| `/forge-deliver` | Commit, push, PR, issue comment workflow |",
        "| `/forge-cleanup` | Branch cleanup and issue closure after merge |",
        "| `/forge-review` | Two-phase PR review (triage + submit) |",
        "| `/forge-respond` | Review response with triage and approval gate |",
        "| `/forge-resume` | Session context reconstruction from GitHub |",
        "",
        "#### Branch Naming",
        "",
        "`issue-<N>-<slug>` — e.g. `issue-42-add-auth-middleware`",
        "",
    ]
    return "\n".join(lines) + "\n"
