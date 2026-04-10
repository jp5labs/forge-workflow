"""Tests for forge_workflow.lib.settings_generator."""

from __future__ import annotations

from forge_workflow.lib.settings_generator import build_forge_hooks


class TestBuildForgeHooks:
    """Tests for building the default forge safety hook set."""

    def test_returns_dict_with_hook_events(self):
        hooks = build_forge_hooks()
        assert isinstance(hooks, dict)
        for event in ["SessionStart", "PreToolUse", "PostToolUse", "SessionEnd"]:
            assert event in hooks, f"Missing event: {event}"

    def test_all_hook_commands_use_forge_workflow_modules(self):
        hooks = build_forge_hooks()
        for event, groups in hooks.items():
            for group in groups:
                for hook in group.get("hooks", []):
                    cmd = hook.get("command", "")
                    assert "forge_workflow.hooks." in cmd, (
                        f"Hook in {event} doesn't use forge_workflow.hooks: {cmd}"
                    )

    def test_no_bash_script_references(self):
        """Forge hooks must not reference repo-specific bash scripts."""
        hooks = build_forge_hooks()
        for event, groups in hooks.items():
            for group in groups:
                for hook in group.get("hooks", []):
                    cmd = hook.get("command", "")
                    assert "bash " not in cmd, (
                        f"Bash script reference found in {event}: {cmd}"
                    )

    def test_pretooluse_bash_matcher_has_safety_hooks(self):
        hooks = build_forge_hooks()
        bash_groups = [
            g for g in hooks["PreToolUse"]
            if g.get("matcher") == "Bash"
        ]
        assert len(bash_groups) == 1
        bash_hooks = bash_groups[0]["hooks"]
        hook_cmds = [h["command"] for h in bash_hooks]
        assert any("block_commit_to_main" in c for c in hook_cmds)
        assert any("destructive_git_halt" in c for c in hook_cmds)
        assert any("compound_command_interceptor" in c for c in hook_cmds)
