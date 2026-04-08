"""Tests for compound-command-interceptor.py mode awareness and detection functions."""

import json
import os
import subprocess
import sys

import pytest

from forge_workflow.hooks.compound_command_interceptor import (
    detect_for_loop,
    detect_long_chain,
    detect_pipe_to_tool,
    detect_redirect_antipatterns,
    detect_stderr_suppression,
    detect_subshell_substitution,
    is_approved_compound,
    main,
    pipe_guidance,
    should_check_long_chains,
    should_check_pipes,
    should_check_redirects,
    should_check_stderr_suppression,
)


class TestModeAwareness:
    """Verify mode-aware behavior of compound-command-interceptor."""

    def test_for_loop_blocked_in_autonomous(self, monkeypatch):
        """For-loops are blocked in autonomous mode."""
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        assert detect_for_loop("for i in 1 2 3; do echo $i; done") is True

    def test_subshell_blocked_in_autonomous(self, monkeypatch):
        """Subshell substitution is blocked in autonomous mode."""
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        assert detect_subshell_substitution("echo $(whoami)") is True

    def test_pipe_to_jq_allowed_in_autonomous(self, monkeypatch):
        """Pipes to jq are allowed in autonomous mode."""
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        assert should_check_pipes() is False

    def test_pipe_to_jq_blocked_in_supervised(self, monkeypatch):
        """Pipes to jq are blocked in supervised mode."""
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        assert should_check_pipes() is True

    def test_stderr_suppression_allowed_in_autonomous(self, monkeypatch):
        """2>/dev/null is allowed in autonomous mode."""
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        assert should_check_stderr_suppression() is False

    def test_stderr_suppression_blocked_in_supervised(self, monkeypatch):
        """2>/dev/null is blocked in supervised mode."""
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        assert should_check_stderr_suppression() is True

    def test_long_chain_allowed_in_autonomous(self, monkeypatch):
        """Long && chains are allowed in autonomous mode."""
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        assert should_check_long_chains() is False

    def test_long_chain_blocked_in_supervised(self, monkeypatch):
        """Long && chains are blocked in supervised mode."""
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        assert should_check_long_chains() is True

    def test_redirect_antipatterns_allowed_in_autonomous(self, monkeypatch):
        """Redirect anti-patterns are allowed in autonomous mode."""
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        assert should_check_redirects() is False

    def test_default_mode_is_supervised(self, monkeypatch):
        """When CLAUDE_MODE is not set, defaults to supervised (all checks)."""
        monkeypatch.delenv("CLAUDE_MODE", raising=False)
        assert should_check_pipes() is True
        assert should_check_stderr_suppression() is True
        assert should_check_long_chains() is True
        assert should_check_redirects() is True


# ---------------------------------------------------------------------------
# Detection function tests
# ---------------------------------------------------------------------------


class TestDetectForLoop:
    """Tests for detect_for_loop detection."""

    def test_simple_for_in_loop(self):
        assert detect_for_loop("for i in 1 2 3; do echo $i; done") is True

    def test_for_file_glob_loop(self):
        assert detect_for_loop("for file in *.txt; do cat $file; done") is True

    def test_multiline_for_loop(self):
        cmd = "for x in a b c\ndo\necho $x\ndone"
        assert detect_for_loop(cmd) is True

    def test_c_style_for_loop(self):
        assert detect_for_loop("for ((i=0; i<10; i++)); do echo $i; done") is True

    def test_simple_command_not_detected(self):
        assert detect_for_loop("echo hello") is False

    def test_python_for_not_detected(self):
        assert detect_for_loop("python -c 'for x in [1,2]: print(x)'") is False

    def test_grep_for_not_detected(self):
        assert detect_for_loop("grep 'for' file.txt") is False


class TestDetectLongChain:
    """Tests for detect_long_chain segment counting."""

    def test_single_command(self):
        assert detect_long_chain("echo hello") == 1

    def test_two_segments(self):
        assert detect_long_chain("echo a && echo b") == 2

    def test_three_segments(self):
        assert detect_long_chain("echo a && echo b && echo c") == 3

    def test_four_segments(self):
        assert detect_long_chain("a && b && c && d") == 4


class TestDetectSubshellSubstitution:
    """Tests for detect_subshell_substitution detection."""

    def test_dollar_paren(self):
        assert detect_subshell_substitution("echo $(whoami)") is True

    def test_backticks(self):
        assert detect_subshell_substitution("echo `hostname`") is True

    def test_file_content_substitution(self):
        assert detect_subshell_substitution("$(<file.txt)") is True

    def test_simple_command_not_detected(self):
        assert detect_subshell_substitution("echo hello") is False

    def test_env_var_not_detected(self):
        assert detect_subshell_substitution("echo $HOME") is False

    def test_git_status_not_detected(self):
        assert detect_subshell_substitution("git status") is False


class TestDetectStderrSuppression:
    """Tests for detect_stderr_suppression detection."""

    def test_stderr_no_space(self):
        assert detect_stderr_suppression("ls 2>/dev/null") is True

    def test_stderr_with_space(self):
        assert detect_stderr_suppression("ls 2> /dev/null") is True

    def test_normal_command_not_detected(self):
        assert detect_stderr_suppression("ls -la") is False


class TestDetectRedirectAntipatterns:
    """Tests for detect_redirect_antipatterns detection."""

    def test_redirect_then_cat_same_file(self):
        result = detect_redirect_antipatterns("gh pr diff 414 > /tmp/x && cat /tmp/x")
        assert result is not None
        assert "Redirect-then-cat" in result

    def test_redirect_then_cat_different_files(self):
        result = detect_redirect_antipatterns("cmd > /tmp/a && cat /tmp/b")
        assert result is not None
        assert "Redirect-then-cat" in result

    def test_simple_tmp_redirect(self):
        result = detect_redirect_antipatterns("gh pr diff > /tmp/out.txt")
        assert result is not None
        assert "Unnecessary redirect" in result

    def test_no_redirect(self):
        assert detect_redirect_antipatterns("echo hello") is None


class TestDetectPipeToTool:
    """Tests for detect_pipe_to_tool detection."""

    @pytest.mark.parametrize("tool", ["grep", "jq", "head", "tail", "awk", "sed", "wc"])
    def test_pipe_to_tool_detected(self, tool):
        cmd = f"ls | {tool}"
        result = detect_pipe_to_tool(cmd)
        assert result is not None

    def test_no_pipe(self):
        assert detect_pipe_to_tool("echo hello") is None

    def test_pipe_to_unknown_tool(self):
        assert detect_pipe_to_tool("ls | sort") is None


class TestIsApprovedCompound:
    """Tests for is_approved_compound allowlist matching."""

    def test_export_git_commit(self):
        cmd = "export GIT_AUTHOR_NAME='Bot' && export GIT_COMMITTER_NAME='Bot' && git commit -m 'test'"
        assert is_approved_compound(cmd) is True

    def test_git_add_commit(self):
        assert is_approved_compound("git add file.py && git commit -m 'test'") is True

    def test_git_fetch_pull(self):
        assert is_approved_compound("git fetch origin && git pull") is True

    def test_git_checkout_pull(self):
        assert is_approved_compound("git checkout main && git pull") is True

    def test_git_stash_checkout(self):
        assert is_approved_compound("git stash && git checkout main") is True

    def test_unapproved_chain(self):
        assert is_approved_compound("echo hello && echo world && echo done") is False

    def test_dangerous_chain(self):
        assert is_approved_compound("rm -rf / && echo oops") is False


# ---------------------------------------------------------------------------
# In-process main() tests (for coverage)
# ---------------------------------------------------------------------------


class TestMainInProcess:
    """Test main() in-process to capture branch coverage."""

    def _make_stdin(self, command):
        """Return a JSON string for stdin."""
        return json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": command},
        })

    def test_main_empty_stdin(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
        # Should not raise -- returns gracefully
        main()

    def test_main_invalid_json(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("not json"))
        main()

    def test_main_empty_command(self, monkeypatch):
        payload = json.dumps({"tool_input": {"command": ""}})
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        main()

    def test_main_whitespace_command(self, monkeypatch):
        payload = json.dumps({"tool_input": {"command": "   "}})
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        main()

    def test_main_no_command_key(self, monkeypatch):
        payload = json.dumps({"tool_input": {}})
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        main()

    def test_main_approved_compound_passes(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        payload = self._make_stdin("git add file.py && git commit -m 'x'")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        main()

    def test_main_simple_command_passes(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        payload = self._make_stdin("echo hello")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        main()

    def test_main_blocks_stderr_suppression(self, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        payload = self._make_stdin("ls 2>/dev/null")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
        output = json.loads(capsys.readouterr().out)
        assert output["decision"] == "block"

    def test_main_blocks_for_loop(self, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        payload = self._make_stdin("for i in 1 2 3; do echo $i; done")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2
        output = json.loads(capsys.readouterr().out)
        assert "For-loop" in output["reason"]

    def test_main_blocks_pipe_supervised(self, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        payload = self._make_stdin("ls | grep foo")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_main_allows_pipe_autonomous(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        payload = self._make_stdin("ls | grep foo")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        # Should not block -- pipe checks skipped in autonomous
        main()

    def test_main_blocks_redirect_antipattern(self, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        payload = self._make_stdin("gh pr diff > /tmp/out.txt")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_main_blocks_subshell(self, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        payload = self._make_stdin("echo $(whoami)")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_main_blocks_long_chain_supervised(self, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        payload = self._make_stdin("a && b && c")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 2

    def test_main_allows_long_chain_autonomous(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        payload = self._make_stdin("a && b && c")
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
        main()

    def test_pipe_guidance_format(self):
        result = pipe_guidance("Use Grep instead.")
        assert "Use Grep instead." in result
        assert "[HOOK]" in result


# ---------------------------------------------------------------------------
# Integration tests via subprocess
# ---------------------------------------------------------------------------


class TestCompoundCommandInterceptorMain:
    """Integration tests running the hook as a subprocess."""

    def _run_hook(self, command, mode="supervised"):
        """Run the hook via subprocess with the given command and mode."""
        payload = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": command},
        })
        env = os.environ.copy()
        env["CLAUDE_MODE"] = mode
        result = subprocess.run(
            [sys.executable, "-m", "forge_workflow.hooks.compound_command_interceptor"],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
        )
        return result

    def test_blocks_for_loop_supervised(self):
        r = self._run_hook("for i in 1 2 3; do echo $i; done", mode="supervised")
        assert r.returncode == 2
        output = json.loads(r.stdout)
        assert output["decision"] == "block"
        assert "For-loop" in output["reason"]

    def test_blocks_for_loop_autonomous(self):
        r = self._run_hook("for i in 1 2 3; do echo $i; done", mode="autonomous")
        assert r.returncode == 2

    def test_blocks_pipe_supervised(self):
        r = self._run_hook("ls | grep foo", mode="supervised")
        assert r.returncode == 2

    def test_allows_pipe_autonomous(self):
        r = self._run_hook("ls | grep foo", mode="autonomous")
        assert r.returncode == 0

    def test_blocks_subshell_always(self):
        r = self._run_hook("echo $(whoami)", mode="supervised")
        assert r.returncode == 2
        r2 = self._run_hook("echo $(whoami)", mode="autonomous")
        assert r2.returncode == 2

    def test_allows_approved_compound(self):
        r = self._run_hook("git add file.py && git commit -m 'test'", mode="supervised")
        assert r.returncode == 0

    def test_allows_two_segment_chain_supervised(self):
        """2-segment chain is below the 3+ threshold — must pass."""
        r = self._run_hook("echo a && echo b", mode="supervised")
        assert r.returncode == 0

    def test_blocks_long_chain_supervised(self):
        r = self._run_hook("a && b && c", mode="supervised")
        assert r.returncode == 2

    def test_allows_long_chain_autonomous(self):
        r = self._run_hook("a && b && c", mode="autonomous")
        assert r.returncode == 0

    def test_simple_command_passes(self):
        r = self._run_hook("echo hello", mode="supervised")
        assert r.returncode == 0

    def test_empty_stdin_exits_gracefully(self):
        env = os.environ.copy()
        env["CLAUDE_MODE"] = "supervised"
        result = subprocess.run(
            [sys.executable, "-m", "forge_workflow.hooks.compound_command_interceptor"],
            input="",
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0

    def test_blocks_stderr_suppression_supervised(self):
        r = self._run_hook("ls 2>/dev/null", mode="supervised")
        assert r.returncode == 2

    def test_allows_stderr_suppression_autonomous(self):
        r = self._run_hook("ls 2>/dev/null", mode="autonomous")
        assert r.returncode == 0

    def test_blocks_redirect_antipattern_supervised(self):
        r = self._run_hook("gh pr diff > /tmp/out.txt", mode="supervised")
        assert r.returncode == 2
