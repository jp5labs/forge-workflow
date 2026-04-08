"""Tests for dangerous-command-halt.py hook."""

import json

import pytest

from forge_workflow.hooks.dangerous_command_halt import check_dangerous


class TestDangerousCommandHalt:
    """Tests for dangerous-command-halt.py."""

    @pytest.mark.parametrize("command", [
        "rm -rf /workspace",
        "rm -r /workspace/src",
        "rm -fr /workspace/src",
        "rm -rfv /workspace",
        "rm -rvf /important",
        "rm --recursive /data",
        "rm -rf tmp/ /etc/passwd",
        "rm -rf tmp/../../etc",
        "sudo apt-get install foo",
        "sudo rm -rf /",
        "mv important.py /dev/null",
        "mv /dev/null important.py",
        "gh release create v1.0",
        "gh api -X DELETE repos/example-org/example-repo/issues/1",
        "gh api --method DELETE repos/example-org/example-repo/pulls/1",
        "gh repo delete example-org/example-repo",
        "git config --global user.name 'Bad Actor'",
    ])
    def test_halts_on_dangerous_commands(self, tmp_path, command):
        """Dangerous commands trigger circuit breaker halt."""
        halt_file = tmp_path / "circuit-breaker-halt.json"
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
        result = check_dangerous(hook_input, halt_file=str(halt_file))
        assert result["halted"] is True, f"Expected halt for: {command}"
        assert halt_file.exists()
        halt_data = json.loads(halt_file.read_text())
        assert halt_data["breaker"] == "dangerous-command"
        assert halt_data["action"] == "halt"

    @pytest.mark.parametrize("command", [
        "rm -rf tmp/session-data",
        "rm -rf tmp/circuit-breaker-state",
        "rm -rfv tmp/session-data",
        "rm -rf /tmp/jp5-venv",
        "rm -rf /tmp/jp5-build",
        "git status",
        "gh pr create --title test",
        "gh api -X PATCH repos/example-org/example-repo/issues/1",
        "gh api --method PUT repos/example-org/example-repo/labels",
        "git config user.name 'Bot Name'",
        "mv old.py new.py",
        "npm test",
    ])
    def test_allows_safe_commands(self, tmp_path, command):
        """Safe commands and exempt paths pass through."""
        halt_file = tmp_path / "circuit-breaker-halt.json"
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
        result = check_dangerous(hook_input, halt_file=str(halt_file))
        assert result["halted"] is False, f"Unexpected halt for: {command}"
        assert not halt_file.exists()

    def test_ignores_non_bash_tools(self, tmp_path):
        """Non-Bash tools are ignored."""
        halt_file = tmp_path / "circuit-breaker-halt.json"
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/workspace/file.py"},
        }
        result = check_dangerous(hook_input, halt_file=str(halt_file))
        assert result["halted"] is False
