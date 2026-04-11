"""Behavioral tests for forge_workflow.hooks.secret_file_scanner."""

import json
import os
import subprocess
import sys
from io import StringIO
from unittest import mock

import pytest

from forge_workflow.hooks.secret_file_scanner import (
    check_content_for_secrets,
    escalate_secret_detection,
    main,
    should_skip_file,
)

# ---------------------------------------------------------------------------
# TestShouldSkipFile
# ---------------------------------------------------------------------------


class TestShouldSkipFile:
    """Verify that skip patterns match the expected file paths."""

    @pytest.mark.parametrize(
        "path",
        [
            ".pre-commit-config.yaml",
            "secret-detection.py",
            "secret_detection.py",
            "secret-file-scanner.py",
            "secret_file_scanner.py",
            "file-protection.py",
            "file_protection.py",
            ".secrets.baseline",
            "CLAUDE.md",
            "AGENTS.md",
            "vault-conventions.md",
            ".claude/rules/some-rule.md",
            ".claude/skills/my-skill.md",
            "scripts/hooks/my-hook.py",
            ".forge/scripts/hooks/my-hook.py",
            "forge_workflow/hooks/my-hook.py",
            "docs/plans/my-plan.md",
            "Pattern - NFR Sample Something.md",
        ],
    )
    def test_skip_patterns_return_true(self, path):
        assert should_skip_file(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "app/config.py",
            "data/output.csv",
        ],
    )
    def test_non_skip_files_return_false(self, path):
        assert should_skip_file(path) is False


# ---------------------------------------------------------------------------
# TestCheckContentForSecrets
# ---------------------------------------------------------------------------


class TestCheckContentForSecrets:
    """Verify that secret patterns are detected in content strings."""

    def test_password_detected(self):
        findings = check_content_for_secrets("password: hunter2")
        types = [t for t, _ in findings]
        assert "password" in types

    def test_api_key_detected(self):
        findings = check_content_for_secrets("api_key=sk-1234567890abcdef")
        types = [t for t, _ in findings]
        assert "API key" in types

    def test_github_pat_detected(self):
        token = "ghp_" + "a" * 36
        findings = check_content_for_secrets(token)
        types = [t for t, _ in findings]
        assert "GitHub personal access token" in types

    def test_aws_access_key_detected(self):
        findings = check_content_for_secrets("AKIAIOSFODNN7EXAMPLE")
        types = [t for t, _ in findings]
        assert "AWS access key ID" in types

    def test_database_connection_string_detected(self):
        findings = check_content_for_secrets(
            "mongodb://user:pass@host:27017/db"
        )
        types = [t for t, _ in findings]
        assert "database connection string" in types

    def test_private_key_pem_detected(self):
        findings = check_content_for_secrets("-----BEGIN PRIVATE KEY-----")
        types = [t for t, _ in findings]
        assert "private key (PEM)" in types

    def test_slack_token_detected(self):
        findings = check_content_for_secrets("xoxb-1234567890-abcdefgh")
        types = [t for t, _ in findings]
        assert "Slack token" in types

    def test_safe_python_code_not_flagged(self):
        content = (
            "def hello():\n"
            "    print('Hello, world!')\n"
            "    return 42\n"
        )
        findings = check_content_for_secrets(content)
        assert findings == []

    def test_safe_comments_not_flagged(self):
        content = "# This is a safe comment\n# Nothing secret here\n"
        findings = check_content_for_secrets(content)
        assert findings == []

    def test_empty_string_not_flagged(self):
        findings = check_content_for_secrets("")
        assert findings == []

    def test_multiple_secret_types_detected(self):
        content = (
            "password: hunter2\n"
            "AKIAIOSFODNN7EXAMPLE\n"
            "-----BEGIN PRIVATE KEY-----\n"
        )
        findings = check_content_for_secrets(content)
        types = [t for t, _ in findings]
        assert "password" in types
        assert "AWS access key ID" in types
        assert "private key (PEM)" in types
        assert len(findings) >= 3


# ---------------------------------------------------------------------------
# TestSecretFileScannerMain
# ---------------------------------------------------------------------------


class TestSecretFileScannerMain:
    """Integration tests running the scanner as a subprocess."""

    MODULE = "forge_workflow.hooks.secret_file_scanner"

    def _run_scanner(self, payload_dict=None, raw_input=None):
        """Run the scanner module and return (returncode, stdout, stderr)."""
        env = os.environ.copy()
        env["CLAUDE_MODE"] = "supervised"

        stdin_data = raw_input
        if stdin_data is None and payload_dict is not None:
            stdin_data = json.dumps(payload_dict)
        if stdin_data is None:
            stdin_data = ""

        result = subprocess.run(
            [sys.executable, "-m", self.MODULE],
            input=stdin_data,
            capture_output=True,
            text=True,
            env=env,
        )
        return result.returncode, result.stdout, result.stderr

    def test_blocks_write_with_secret_content(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/config.py",
                "content": "password: hunter2",
            },
        }
        code, stdout, _ = self._run_scanner(payload)
        output = json.loads(stdout)
        assert output["decision"] == "block"

    def test_blocks_edit_with_secret_in_new_string(self):
        payload = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "src/config.py",
                "old_string": "placeholder",
                "new_string": "password: hunter2",
            },
        }
        code, stdout, _ = self._run_scanner(payload)
        output = json.loads(stdout)
        assert output["decision"] == "block"

    def test_allows_safe_write(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/main.py",
                "content": "print('hello world')",
            },
        }
        code, stdout, _ = self._run_scanner(payload)
        assert code == 0
        assert "block" not in stdout

    def test_skips_hook_implementation_files(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "forge_workflow/hooks/secret_detection.py",
                "content": "password: hunter2",
            },
        }
        code, stdout, _ = self._run_scanner(payload)
        assert code == 0
        assert "block" not in stdout

    def test_ignores_non_edit_write_tools(self):
        payload = {
            "tool_name": "Read",
            "tool_input": {
                "file_path": "src/config.py",
            },
        }
        code, stdout, _ = self._run_scanner(payload)
        assert code == 0
        assert "block" not in stdout

    def test_empty_content_passes(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/empty.py",
                "content": "",
            },
        }
        code, stdout, _ = self._run_scanner(payload)
        assert code == 0
        assert "block" not in stdout

    def test_empty_stdin_exits_gracefully(self):
        code, stdout, _ = self._run_scanner(raw_input="")
        assert code == 0

    def test_invalid_json_exits_gracefully(self):
        code, stdout, _ = self._run_scanner(raw_input="not json at all{{{")
        assert code == 0


# ---------------------------------------------------------------------------
# TestEscalateSecretDetection
# ---------------------------------------------------------------------------


class TestEscalateSecretDetection:
    """Tests for the escalate_secret_detection function."""

    def test_supervised_mode_no_escalation(self, tmp_path):
        """In supervised mode, returns immediately with count=0."""
        with mock.patch.dict(os.environ, {"CLAUDE_MODE": "supervised"}):
            result = escalate_secret_detection(
                "test finding",
                state_dir=str(tmp_path / "state"),
                halt_file=str(tmp_path / "halt.json"),
            )
        assert result == {"count": 0, "halted": False}

    def test_autonomous_mode_increments_counter(self, tmp_path):
        """In autonomous mode, counter increments on each call."""
        state_dir = str(tmp_path / "state")
        halt_file = str(tmp_path / "halt.json")
        with mock.patch.dict(os.environ, {"CLAUDE_MODE": "autonomous"}):
            r1 = escalate_secret_detection("finding 1", state_dir, halt_file)
            assert r1["count"] == 1
            assert r1["halted"] is False

            r2 = escalate_secret_detection("finding 2", state_dir, halt_file)
            assert r2["count"] == 2
            assert r2["halted"] is False

    def test_autonomous_mode_halts_at_threshold(self, tmp_path):
        """At threshold, halt file is written and halted=True."""
        state_dir = str(tmp_path / "state")
        halt_file = str(tmp_path / "halt.json")
        with mock.patch.dict(os.environ, {"CLAUDE_MODE": "autonomous"}):
            for i in range(2):
                escalate_secret_detection(
                    f"finding {i}", state_dir, halt_file, threshold=3
                )
            result = escalate_secret_detection(
                "finding 3", state_dir, halt_file, threshold=3
            )
        assert result["halted"] is True
        assert result["count"] == 3
        assert os.path.exists(halt_file)
        with open(halt_file) as f:
            halt_data = json.load(f)
        assert halt_data["breaker"] == "secret-escalation"

    def test_autonomous_mode_corrupt_state_file(self, tmp_path):
        """Corrupt state file is handled gracefully."""
        state_dir = str(tmp_path / "state")
        halt_file = str(tmp_path / "halt.json")
        os.makedirs(state_dir, exist_ok=True)
        with open(os.path.join(state_dir, "secret-detections.json"), "w") as f:
            f.write("not json")
        with mock.patch.dict(os.environ, {"CLAUDE_MODE": "autonomous"}):
            result = escalate_secret_detection(
                "finding", state_dir, halt_file
            )
        assert result["count"] == 1
        assert result["halted"] is False

    def test_default_mode_is_supervised(self, tmp_path):
        """When CLAUDE_MODE is not set, defaults to supervised."""
        env = os.environ.copy()
        env.pop("CLAUDE_MODE", None)
        with mock.patch.dict(os.environ, env, clear=True):
            result = escalate_secret_detection(
                "finding",
                state_dir=str(tmp_path / "state"),
                halt_file=str(tmp_path / "halt.json"),
            )
        assert result == {"count": 0, "halted": False}


# ---------------------------------------------------------------------------
# TestMainInProcess
# ---------------------------------------------------------------------------


class TestMainInProcess:
    """In-process tests for main() to get coverage on the main function."""

    def _run_main(self, payload_dict=None, raw_input=None):
        """Call main() with mocked stdin, return exit code and stdout."""
        stdin_data = raw_input
        if stdin_data is None and payload_dict is not None:
            stdin_data = json.dumps(payload_dict)
        if stdin_data is None:
            stdin_data = ""

        captured_stdout = StringIO()
        with mock.patch("sys.stdin", StringIO(stdin_data)), \
             mock.patch("sys.stdout", captured_stdout), \
             mock.patch.dict(os.environ, {"CLAUDE_MODE": "supervised"}):
            try:
                main()
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code if e.code is not None else 0
        return exit_code, captured_stdout.getvalue()

    def test_main_blocks_write_with_secret(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/config.py",
                "content": "password: hunter2",
            },
        }
        code, stdout = self._run_main(payload)
        assert code == 0  # supervised mode does not exit 2
        output = json.loads(stdout)
        assert output["decision"] == "block"

    def test_main_blocks_edit_with_secret(self):
        payload = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "src/config.py",
                "old_string": "x",
                "new_string": "api_key=sk-12345678901234567890abcdef",
            },
        }
        code, stdout = self._run_main(payload)
        output = json.loads(stdout)
        assert output["decision"] == "block"

    def test_main_allows_safe_write(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/main.py",
                "content": "x = 1",
            },
        }
        code, stdout = self._run_main(payload)
        assert code == 0
        assert "block" not in stdout

    def test_main_skips_non_edit_write_tools(self):
        payload = {
            "tool_name": "Read",
            "tool_input": {"file_path": "src/main.py"},
        }
        code, stdout = self._run_main(payload)
        assert code == 0

    def test_main_skips_hook_files(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "forge_workflow/hooks/my_hook.py",
                "content": "password: hunter2",
            },
        }
        code, stdout = self._run_main(payload)
        assert code == 0
        assert "block" not in stdout

    def test_main_empty_content_passes(self):
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": "src/x.py", "content": ""},
        }
        code, stdout = self._run_main(payload)
        assert code == 0

    def test_main_empty_stdin(self):
        code, stdout = self._run_main(raw_input="")
        assert code == 0

    def test_main_invalid_json(self):
        code, stdout = self._run_main(raw_input="{bad json")
        assert code == 0

    def test_main_whitespace_only_stdin(self):
        code, stdout = self._run_main(raw_input="   \n  \n  ")
        assert code == 0

    def test_main_autonomous_mode_escalation_halt(self):
        """In autonomous mode, hitting threshold causes exit code 2."""
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/config.py",
                "content": "password: hunter2",
            },
        }
        stdin_data = json.dumps(payload)
        captured_stdout = StringIO()

        # Mock escalation to return halted=True
        with mock.patch("sys.stdin", StringIO(stdin_data)), \
             mock.patch("sys.stdout", captured_stdout), \
             mock.patch.dict(os.environ, {"CLAUDE_MODE": "autonomous"}), \
             mock.patch(
                 "forge_workflow.hooks.secret_file_scanner.escalate_secret_detection",
                 return_value={"count": 3, "halted": True},
             ):
            try:
                main()
                exit_code = 0
            except SystemExit as e:
                exit_code = e.code if e.code is not None else 0

        assert exit_code == 2
        output = json.loads(captured_stdout.getvalue())
        assert output["decision"] == "block"
