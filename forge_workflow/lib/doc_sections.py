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


def render_agents_autonomous_detail(bots: list[BotEntry]) -> str:
    """Render the Autonomous Mode Detail section for AGENTS.md."""
    lines = [
        "### Autonomous Mode Detail",
        "",
        "In autonomous mode, `--dangerously-skip-permissions` bypasses Claude Code's "
        "built-in allow/deny permission lists entirely. **Hooks become the sole safety "
        "layer.** The settings generator (`forge_workflow.lib.settings_generator`) wires "
        "all safety hooks into `settings.local.json` at container startup.",
        "",
        "#### What hooks enforce",
        "",
        "**Circuit breakers** — halt the session on dangerous patterns:",
        "",
        "| Hook | Trigger |",
        "|------|---------|",
        "| `destructive_git_halt` | Destructive git commands (force push, reset --hard) |",
        "| `dangerous_command_halt` | Dangerous shell commands (rm -rf, etc.) |",
        "| `sequential_failure_breaker` | 5 consecutive Bash failures (configurable) |",
        "| `secret_detection` | Secrets in user prompts |",
        "| `secret_file_scanner` | Secrets in file writes/edits |",
        "",
        "**Guidance hooks** — block policy violations without halting:",
        "",
        "| Hook | Enforcement |",
        "|------|------------|",
        "| `block_commit_to_main` | Prevents direct commits to main branch |",
        "| `compound_command_interceptor` | Validates compound shell commands |",
        "| `shell_expansion_guard` | Blocks `${}` variable expansion in Bash |",
        "",
        "**Workflow hooks** — automation, not safety:",
        "",
        "| Hook | Purpose |",
        "|------|---------|",
        "| `circuit_breaker_init` | Initialize breaker state at session start |",
        "| `post_plan_to_issue` | Post plan to GitHub issue on ExitPlanMode |",
        "| `post_assessment_to_issue` | Post assessment to GitHub issue |",
        "| `ruff_fix` | Auto-format Python after edits |",
        "| `session_telemetry` | Record session metrics at end |",
        "",
        "#### Per-bot environment overrides",
        "",
        "Each bot's `.env` file supports these overrides:",
        "",
        "| Variable | Default | Effect |",
        "|----------|---------|--------|",
        "| `CLAUDE_MODE` | `autonomous` | `supervised` switches to `acceptEdits` "
        "permission model and disables hook wiring |",
        "| `CB_FAILURE_LIMIT` | `5` | Number of consecutive Bash failures before "
        "the sequential failure breaker halts the session |",
        "",
    ]
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


def render_agents_gate_policy(bots: list[BotEntry]) -> str:
    """Render the Autonomous Gate Policy section for AGENTS.md."""
    lines = [
        "### Autonomous Gate Policy",
        "",
        "Each forge skill has a gate — a point where it pauses for human approval. "
        "In autonomous mode, some gates auto-proceed; others always halt.",
        "",
        "| Skill | Gate | Autonomous behavior | Halt conditions |",
        "|-------|------|--------------------|--------------------|",
        "| forge-discover | Routing confirmation | Auto-proceed | (none) |",
        (
            "| forge-assess | Assessment approval | Auto-proceed if clean "
            "| UNCLEAR fit-check, HIGH risk, REVISE/DEFER, ADR boundary, DRIFT |"
        ),
        "| forge-plan | Plan approval | Mode-aware | Phase 4 execution handoff |",
        (
            "| forge-shape | Decomposition approval | Auto-proceed if `--from-spec` "
            "| Interactive mode (no spec) |"
        ),
        "| forge-deliver | Implementation review | Skip — PR is the review | (none) |",
        "| forge-spec | All gates | Never bypass | (always human) |",
        "| forge-start | (no gate) | N/A | N/A |",
        "| forge-cleanup | (no gate) | N/A | N/A |",
        "",
        "#### Override mechanisms",
        "",
        "- **`needs-human-gate` label:** Adding this label to a GitHub issue forces "
        "supervised behavior for all skills working on that issue, regardless of "
        "`CLAUDE_MODE`.",
        "- **Fail-safe defaults:** API errors → halt. unset mode → halt. "
        "Ambiguous evaluation → halt. When in doubt, the system stops and waits "
        "for human input.",
        "",
    ]
    return "\n".join(lines) + "\n"
