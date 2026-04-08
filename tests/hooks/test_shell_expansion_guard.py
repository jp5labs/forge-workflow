"""Tests for forge_workflow.hooks.shell_expansion_guard."""

import json
import subprocess
import sys


def _run_hook(command_str):
    """Run the hook with a simulated tool_input and return (exit_code, stdout)."""
    payload = json.dumps({"tool_input": {"command": command_str}})
    result = subprocess.run(
        [sys.executable, "-m", "forge_workflow.hooks.shell_expansion_guard"],
        input=payload,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


class TestShellExpansionGuard:
    """Tests for shell-expansion-guard.py."""

    def test_blocks_simple_variable_expansion(self):
        """${VAR} is blocked."""
        code, stdout = _run_hook('echo "${CLAUDE_MODE}"')
        assert code == 2
        output = json.loads(stdout)
        assert output["decision"] == "block"
        assert "${}" in output["reason"]

    def test_blocks_default_value_expansion(self):
        """${VAR:-default} is blocked."""
        code, stdout = _run_hook('echo "${CLAUDE_MODE:-autonomous}"')
        assert code == 2
        output = json.loads(stdout)
        assert output["decision"] == "block"

    def test_blocks_nested_in_command(self):
        """${} inside a longer command is blocked."""
        code, stdout = _run_hook('git commit -m "version ${VERSION}"')
        assert code == 2

    def test_allows_plain_commands(self):
        """Commands without ${} pass through."""
        code, _ = _run_hook("printenv CLAUDE_MODE")
        assert code == 0

    def test_allows_dollar_sign_without_braces(self):
        """Plain $VAR (no braces) is not blocked by this hook."""
        code, _ = _run_hook("echo $HOME")
        assert code == 0

    def test_allows_empty_command(self):
        """Empty command passes through."""
        code, _ = _run_hook("")
        assert code == 0

    def test_allows_git_commands(self):
        """Standard git commands pass through."""
        code, _ = _run_hook("git status")
        assert code == 0

    def test_allows_printenv(self):
        """printenv is the recommended alternative."""
        code, _ = _run_hook("printenv CLAUDE_MODE")
        assert code == 0

    def test_blocks_multiple_expansions(self):
        """Multiple ${} in one command is still blocked."""
        code, stdout = _run_hook('cmd --a "${X}" --b "${Y}"')
        assert code == 2

    def test_graceful_on_malformed_input(self):
        """Malformed JSON input doesn't crash."""
        result = subprocess.run(
            [sys.executable, "-m", "forge_workflow.hooks.shell_expansion_guard"],
            input="not json",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0  # best-effort pass-through
