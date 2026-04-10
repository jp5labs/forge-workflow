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


class TestMergeHooks:
    """Tests for merging forge hooks into existing settings."""

    def test_merge_into_empty_settings(self):
        from forge_workflow.lib.settings_generator import merge_hooks

        existing = {}
        forge_hooks = {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "cmd1"}]}]}
        result = merge_hooks(existing, forge_hooks)
        assert result == {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "cmd1"}]}]}}

    def test_preserves_non_hook_settings(self):
        from forge_workflow.lib.settings_generator import merge_hooks

        existing = {"allowedTools": ["Read", "Write"], "permissions": {"allow": ["*.py"]}}
        forge_hooks = {"SessionEnd": [{"hooks": [{"type": "command", "command": "cmd1"}]}]}
        result = merge_hooks(existing, forge_hooks)
        assert result["allowedTools"] == ["Read", "Write"]
        assert result["permissions"] == {"allow": ["*.py"]}
        assert "SessionEnd" in result["hooks"]

    def test_appends_to_matching_matcher(self):
        from forge_workflow.lib.settings_generator import merge_hooks

        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "existing-cmd"}]}
                ]
            }
        }
        forge_hooks = {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "forge-cmd"}]}
            ]
        }
        result = merge_hooks(existing, forge_hooks)
        bash_groups = [g for g in result["hooks"]["PreToolUse"] if g.get("matcher") == "Bash"]
        assert len(bash_groups) == 1, "Should merge into same matcher group, not duplicate"
        hook_cmds = [h["command"] for h in bash_groups[0]["hooks"]]
        assert "existing-cmd" in hook_cmds
        assert "forge-cmd" in hook_cmds

    def test_adds_new_event_without_touching_existing(self):
        from forge_workflow.lib.settings_generator import merge_hooks

        existing = {
            "hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": "existing"}]}]
            }
        }
        forge_hooks = {
            "SessionEnd": [{"hooks": [{"type": "command", "command": "forge-end"}]}]
        }
        result = merge_hooks(existing, forge_hooks)
        assert "SessionStart" in result["hooks"]
        assert "SessionEnd" in result["hooks"]
        assert result["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "existing"

    def test_no_duplicate_hooks_on_repeated_merge(self):
        from forge_workflow.lib.settings_generator import merge_hooks

        existing = {}
        forge_hooks = {"SessionEnd": [{"hooks": [{"type": "command", "command": "cmd1"}]}]}
        result = merge_hooks(existing, forge_hooks)
        result2 = merge_hooks(result, forge_hooks)
        end_hooks = result2["hooks"]["SessionEnd"][0]["hooks"]
        assert len(end_hooks) == 1, "Should not duplicate hooks on re-merge"

    def test_appends_new_matcher_group_to_existing_event(self):
        from forge_workflow.lib.settings_generator import merge_hooks

        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "existing"}]}
                ]
            }
        }
        forge_hooks = {
            "PreToolUse": [
                {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "forge-edit"}]}
            ]
        }
        result = merge_hooks(existing, forge_hooks)
        matchers = [g.get("matcher") for g in result["hooks"]["PreToolUse"]]
        assert "Bash" in matchers
        assert "Edit|Write" in matchers


class TestBuildCustomHooks:
    """Tests for building hooks from hooks.custom config."""

    def test_empty_custom_returns_empty(self):
        from forge_workflow.lib.settings_generator import build_custom_hooks

        result = build_custom_hooks([])
        assert result == {}

    def test_single_custom_hook(self):
        from forge_workflow.lib.settings_generator import build_custom_hooks

        custom = [
            {"event": "Notification", "command": "bash scripts/hooks/notify.sh notification"}
        ]
        result = build_custom_hooks(custom)
        assert "Notification" in result
        assert len(result["Notification"]) == 1
        assert result["Notification"][0]["hooks"][0]["command"] == "bash scripts/hooks/notify.sh notification"

    def test_custom_hook_with_matcher(self):
        from forge_workflow.lib.settings_generator import build_custom_hooks

        custom = [
            {"event": "PreToolUse", "matcher": "Bash", "command": "bash scripts/hooks/cancel-notify.sh"}
        ]
        result = build_custom_hooks(custom)
        assert result["PreToolUse"][0]["matcher"] == "Bash"

    def test_multiple_hooks_same_event_grouped(self):
        from forge_workflow.lib.settings_generator import build_custom_hooks

        custom = [
            {"event": "Notification", "command": "cmd1"},
            {"event": "Notification", "command": "cmd2"},
        ]
        result = build_custom_hooks(custom)
        assert len(result["Notification"]) == 2


class TestGenerate:
    """Tests for the top-level generate function."""

    def test_generate_creates_settings_file(self, tmp_path):
        import json

        from forge_workflow.lib.settings_generator import generate

        output = tmp_path / ".claude" / "settings.local.json"
        generate(output_path=output, mode="autonomous", custom_hooks=[])
        assert output.is_file()
        settings = json.loads(output.read_text())
        assert "hooks" in settings

    def test_generate_supervised_mode_empty(self, tmp_path):
        import json

        from forge_workflow.lib.settings_generator import generate

        output = tmp_path / ".claude" / "settings.local.json"
        generate(output_path=output, mode="supervised", custom_hooks=[])
        settings = json.loads(output.read_text())
        assert settings == {}

    def test_generate_merges_with_existing(self, tmp_path):
        import json

        from forge_workflow.lib.settings_generator import generate

        output = tmp_path / ".claude" / "settings.local.json"
        output.parent.mkdir(parents=True)
        output.write_text(json.dumps({"allowedTools": ["Read"]}))
        generate(output_path=output, mode="autonomous", custom_hooks=[])
        settings = json.loads(output.read_text())
        assert settings["allowedTools"] == ["Read"]
        assert "hooks" in settings

    def test_generate_includes_custom_hooks(self, tmp_path):
        import json

        from forge_workflow.lib.settings_generator import generate

        output = tmp_path / ".claude" / "settings.local.json"
        custom = [{"event": "Notification", "command": "bash notify.sh"}]
        generate(output_path=output, mode="autonomous", custom_hooks=custom)
        settings = json.loads(output.read_text())
        assert "Notification" in settings["hooks"]
