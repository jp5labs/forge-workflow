"""Settings generator — builds and merges Claude Code safety hooks.

Produces .claude/settings.local.json with forge safety hooks merged
into any existing settings without clobbering.
"""

from __future__ import annotations

from typing import Any


def _hook_cmd(module_name: str, timeout: int | None = None) -> dict:
    """Build a hook entry for a forge_workflow.hooks module."""
    cmd = f"python -m forge_workflow.hooks.{module_name}"
    entry: dict[str, Any] = {"type": "command", "command": cmd}
    if timeout:
        entry["timeout"] = timeout
    return entry


def build_forge_hooks() -> dict[str, list[dict]]:
    """Build the default forge safety hook set for autonomous mode.

    Returns a dict keyed by Claude Code hook event name, with values
    being lists of hook group dicts (each with optional matcher and hooks list).
    Only includes portable forge_workflow.hooks.* modules — no repo-specific
    bash scripts.
    """
    return {
        "SessionStart": [
            {
                "hooks": [
                    _hook_cmd("circuit_breaker_init"),
                ]
            }
        ],
        "UserPromptSubmit": [
            {
                "matcher": ".*",
                "hooks": [
                    _hook_cmd("secret_detection", timeout=10),
                ],
            }
        ],
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    _hook_cmd("block_commit_to_main"),
                    _hook_cmd("shell_expansion_guard"),
                    _hook_cmd("destructive_git_halt"),
                    _hook_cmd("dangerous_command_halt"),
                    _hook_cmd("compound_command_interceptor", timeout=5),
                ],
            },
            {
                "matcher": "Edit|Write",
                "hooks": [
                    _hook_cmd("secret_file_scanner", timeout=10),
                ],
            },
            {
                "matcher": "ExitPlanMode",
                "hooks": [
                    _hook_cmd("post_plan_to_issue"),
                ],
            },
        ],
        "PostToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    _hook_cmd("sequential_failure_breaker"),
                ],
            },
            {
                "matcher": "Edit|Write",
                "hooks": [
                    _hook_cmd("ruff_fix"),
                    _hook_cmd("post_assessment_to_issue"),
                ],
            },
        ],
        "SessionEnd": [
            {
                "hooks": [
                    _hook_cmd("session_telemetry"),
                ]
            }
        ],
    }
