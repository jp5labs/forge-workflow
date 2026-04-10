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


def merge_hooks(
    existing_settings: dict,
    forge_hooks: dict[str, list[dict]],
) -> dict:
    """Merge forge hooks into existing settings without clobbering.

    - Preserves all non-hook settings (allowedTools, permissions, etc.)
    - For each hook event, appends forge hooks to matching matcher groups
    - Adds new matcher groups for matchers not already present
    - Skips hooks that are already present (idempotent)
    """
    import copy

    result = copy.deepcopy(existing_settings)
    existing_hooks = result.setdefault("hooks", {})

    for event, forge_groups in forge_hooks.items():
        if event not in existing_hooks:
            existing_hooks[event] = copy.deepcopy(forge_groups)
            continue

        existing_groups = existing_hooks[event]

        for forge_group in forge_groups:
            forge_matcher = forge_group.get("matcher")
            # Find existing group with same matcher
            matched_group = None
            for eg in existing_groups:
                if eg.get("matcher") == forge_matcher:
                    matched_group = eg
                    break

            if matched_group is not None:
                # Append forge hooks that aren't already present
                existing_cmds = {
                    h.get("command") for h in matched_group.get("hooks", [])
                }
                for hook in forge_group.get("hooks", []):
                    if hook.get("command") not in existing_cmds:
                        matched_group.setdefault("hooks", []).append(
                            copy.deepcopy(hook)
                        )
            else:
                # New matcher group — add it
                existing_groups.append(copy.deepcopy(forge_group))

    return result


def build_custom_hooks(custom_entries: list[dict]) -> dict[str, list[dict]]:
    """Build hook groups from hooks.custom config entries.

    Each entry is: {"event": "PreToolUse", "matcher": "Bash", "command": "..."}
    matcher is optional.
    """
    hooks: dict[str, list[dict]] = {}
    for entry in custom_entries:
        event = entry.get("event", "")
        if not event:
            continue
        command = entry.get("command", "")
        if not command:
            continue

        group: dict[str, Any] = {
            "hooks": [{"type": "command", "command": command}],
        }
        matcher = entry.get("matcher")
        if matcher:
            group["matcher"] = matcher

        hooks.setdefault(event, []).append(group)

    return hooks


def generate(
    output_path: Path | str,
    mode: str = "autonomous",
    custom_hooks: list[dict] | None = None,
) -> None:
    """Generate settings.local.json with forge hooks merged in.

    Args:
        output_path: Path to write settings.local.json
        mode: "autonomous" (wire safety hooks) or "supervised" (empty)
        custom_hooks: List of custom hook entries from hooks.custom config
    """
    import json
    from pathlib import Path as _Path

    output_path = _Path(output_path)

    # Load existing settings if present
    existing: dict = {}
    if output_path.is_file():
        try:
            existing = json.loads(output_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}

    if mode == "supervised":
        settings = existing  # preserve existing, don't add hooks
    else:
        # Build forge hooks + custom hooks, then merge
        forge_hooks = build_forge_hooks()
        if custom_hooks:
            custom = build_custom_hooks(custom_hooks)
            # Merge custom into forge hooks first
            for event, groups in custom.items():
                forge_hooks.setdefault(event, []).extend(groups)
        settings = merge_hooks(existing, forge_hooks)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"Generated {output_path} (mode={mode})")


def main() -> None:
    """CLI entrypoint for settings generation.

    Reads CLAUDE_MODE and REPO_ROOT env vars. Loads hooks.custom
    from forge config if available.
    """
    import os
    from pathlib import Path as _Path

    mode = os.environ.get("CLAUDE_MODE", "autonomous")
    repo_root = os.environ.get(
        "REPO_ROOT",
        str(_Path.cwd()),
    )
    output_path = _Path(repo_root) / ".claude" / "settings.local.json"

    # Try to load custom hooks from forge config
    custom_hooks: list[dict] = []
    try:
        from forge_workflow.config import get

        custom_hooks = get("hooks.custom", []) or []
    except Exception:
        pass

    generate(output_path=output_path, mode=mode, custom_hooks=custom_hooks)


if __name__ == "__main__":
    main()
