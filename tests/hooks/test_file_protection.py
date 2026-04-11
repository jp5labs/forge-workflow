"""Behavioral tests for forge_workflow.hooks.file_protection.

Covers is_protected() logic (path matching, keywords, exceptions)
and the main() entry point via subprocess integration tests.

Target: >=70% branch coverage on forge_workflow/hooks/file_protection.py.
"""

import io
import json
import subprocess
import sys
from unittest import mock

import pytest

from forge_workflow.hooks.file_protection import is_protected, main

# ---------------------------------------------------------------------------
# TestIsProtectedPaths
# ---------------------------------------------------------------------------

class TestIsProtectedPaths:
    """Exact filename, wildcard suffix, and directory matches."""

    @pytest.mark.parametrize("filename", [
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Gemfile.lock",
        "poetry.lock",
        "Cargo.lock",
        "credentials",
        "credentials.json",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        ".secrets",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        ".npmrc",
        ".pypirc",
        ".netrc",
        "config.local.json",
    ])
    def test_exact_filename_blocked(self, filename):
        blocked, reason = is_protected(filename)
        assert blocked is True, f"{filename} should be blocked"
        assert reason, f"{filename} should have a reason"

    @pytest.mark.parametrize("filepath,expected_fragment", [
        ("server.pem", "Protected file type"),
        ("/etc/ssl/certs/ca.pem", "Protected file type"),
        ("private.key", "Protected file type"),
        ("cert.p12", "Protected file type"),
        ("keystore.pfx", "Protected file type"),
    ])
    def test_wildcard_suffix_blocked(self, filepath, expected_fragment):
        blocked, reason = is_protected(filepath)
        assert blocked is True, f"{filepath} should be blocked"
        assert expected_fragment in reason

    @pytest.mark.parametrize("filepath", [
        ".git/config",
        ".aws/credentials",
        ".ssh/known_hosts",
        ".gnupg/pubring.kbx",
    ])
    def test_directory_match_blocked(self, filepath):
        blocked, reason = is_protected(filepath)
        assert blocked is True, f"{filepath} should be blocked"
        assert "Protected directory" in reason

    @pytest.mark.parametrize("filepath", [
        "src/main.py",
        "README.md",
        "pyproject.toml",
        "data/output.csv",
    ])
    def test_safe_files_pass(self, filepath):
        blocked, reason = is_protected(filepath)
        assert blocked is False, f"{filepath} should not be blocked"
        assert reason == ""


# ---------------------------------------------------------------------------
# TestIsProtectedKeywords
# ---------------------------------------------------------------------------

class TestIsProtectedKeywords:
    """Sensitive keyword substring and whole-word matching."""

    @pytest.mark.parametrize("filename", [
        "my_api_key.txt",
        "my-api-key.json",
        "my_apikey.conf",
        "user_password.txt",
        "db_passwd.conf",
        "auth_secret.yaml",
        "access_token.json",
        "my_credential.txt",
        "privatekey.txt",
    ])
    def test_sensitive_keyword_blocked(self, filename):
        blocked, reason = is_protected(filename)
        assert blocked is True, f"{filename} should be blocked"
        assert "Sensitive keyword" in reason

    @pytest.mark.parametrize("filename", [
        "pin.txt",
        "pat.conf",
    ])
    def test_whole_word_keyword_blocked(self, filename):
        blocked, reason = is_protected(filename)
        assert blocked is True, f"{filename} should be blocked"
        assert "Sensitive keyword" in reason

    @pytest.mark.parametrize("filename", [
        "Mapping.txt",
        "Pattern.md",
        "spatial.py",
        "pinboard.txt",
    ])
    def test_whole_word_no_false_positive(self, filename):
        blocked, reason = is_protected(filename)
        assert blocked is False, f"{filename} should NOT be blocked"


# ---------------------------------------------------------------------------
# TestIsProtectedExceptions
# ---------------------------------------------------------------------------

class TestIsProtectedExceptions:
    """Allowed exception files, directories, and prefixes."""

    @pytest.mark.parametrize("filename", [
        ".secrets.baseline",
        ".pre-commit-config.yaml",
        "secret-detection.py",
        "secret-file-scanner.py",
        "secret_detection.py",
        "secret_file_scanner.py",
    ])
    def test_allowed_exception_files(self, filename):
        blocked, reason = is_protected(filename)
        assert blocked is False, f"{filename} should be allowed as exception"

    @pytest.mark.parametrize("filepath", [
        "tests/test_secret_handler.py",
        "docs/credential-rotation.md",
        ".forge/scripts/token-refresh.py",
        "forge_workflow/hooks/secret_detection.py",
        ".claude/skills/token-skill.md",
        "src/secret_store.py",
    ])
    def test_allowed_directories(self, filepath):
        blocked, reason = is_protected(filepath)
        assert blocked is False, f"{filepath} should be allowed (directory exception)"

    @pytest.mark.parametrize("filename", [
        "Task - Credential Rotation.md",
        "Concept - Secret Management.md",
        "Pattern - Token Refresh.md",
    ])
    def test_allowed_prefixes(self, filename):
        blocked, reason = is_protected(filename)
        assert blocked is False, f"{filename} should be allowed (prefix exception)"


# ---------------------------------------------------------------------------
# TestFileProtectionMain
# ---------------------------------------------------------------------------

class TestFileProtectionMain:
    """Integration tests running the hook as a subprocess."""

    def _run_hook(self, input_data=None, raw_input=None):
        """Run file_protection as a module and return (returncode, stdout, stderr)."""
        stdin_bytes = raw_input if raw_input is not None else (
            json.dumps(input_data).encode() if input_data is not None else b""
        )
        result = subprocess.run(
            [sys.executable, "-m", "forge_workflow.hooks.file_protection"],
            input=stdin_bytes,
            capture_output=True,
            timeout=10,
        )
        return result.returncode, result.stdout.decode(), result.stderr.decode()

    def test_blocks_protected_file(self):
        data = {
            "tool_name": "Write",
            "tool_input": {"file_path": ".env"},
        }
        rc, stdout, _ = self._run_hook(data)
        assert rc == 0
        output = json.loads(stdout)
        assert output["decision"] == "block"

    def test_allows_safe_file(self):
        data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "src/main.py"},
        }
        rc, stdout, _ = self._run_hook(data)
        assert rc == 0
        # Safe files with no config keywords produce no output
        assert stdout.strip() == ""

    def test_ignores_non_edit_write_tools(self):
        data = {
            "tool_name": "Read",
            "tool_input": {"file_path": ".env"},
        }
        rc, stdout, _ = self._run_hook(data)
        assert rc == 0
        assert stdout.strip() == ""

    def test_empty_stdin_exits_gracefully(self):
        rc, stdout, _ = self._run_hook(raw_input=b"")
        assert rc == 0

    def test_invalid_json_exits_gracefully(self):
        rc, stdout, _ = self._run_hook(raw_input=b"not json at all{{{")
        assert rc == 0

    def test_missing_file_path_exits_gracefully(self):
        data = {
            "tool_name": "Write",
            "tool_input": {},
        }
        rc, stdout, _ = self._run_hook(data)
        assert rc == 0
        assert stdout.strip() == ""

    def test_config_file_gets_additional_context(self):
        data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "app/settings.py"},
        }
        rc, stdout, _ = self._run_hook(data)
        assert rc == 0
        output = json.loads(stdout)
        assert "additionalContext" in output
        assert "settings.py" in output["additionalContext"]

    def test_edit_tool_also_checked(self):
        data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".env"},
        }
        rc, stdout, _ = self._run_hook(data)
        assert rc == 0
        output = json.loads(stdout)
        assert output["decision"] == "block"


# ---------------------------------------------------------------------------
# TestFileProtectionMainDirect
# ---------------------------------------------------------------------------

class TestFileProtectionMainDirect:
    """Direct unit tests for main() to get branch coverage on lines 175-221."""

    def _run_main(self, stdin_text):
        """Call main() with mocked stdin and capture stdout/exit code."""
        with mock.patch("sys.stdin", io.StringIO(stdin_text)):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                try:
                    main()
                except SystemExit as exc:
                    return exc.code, mock_stdout.getvalue()
        return 0, mock_stdout.getvalue()

    def test_empty_stdin(self):
        code, _ = self._run_main("")
        assert code == 0

    def test_invalid_json(self):
        code, _ = self._run_main("{bad json")
        assert code == 0

    def test_non_edit_write_tool(self):
        data = json.dumps({"tool_name": "Read", "tool_input": {"file_path": ".env"}})
        code, output = self._run_main(data)
        assert code == 0
        assert output.strip() == ""

    def test_missing_file_path(self):
        data = json.dumps({"tool_name": "Write", "tool_input": {}})
        code, output = self._run_main(data)
        assert code == 0
        assert output.strip() == ""

    def test_blocks_protected(self):
        data = json.dumps({"tool_name": "Write", "tool_input": {"file_path": ".env"}})
        code, output = self._run_main(data)
        assert code == 0
        parsed = json.loads(output)
        assert parsed["decision"] == "block"

    def test_config_hint(self):
        data = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "app/settings.py"}})
        code, output = self._run_main(data)
        assert code == 0
        parsed = json.loads(output)
        assert "additionalContext" in parsed

    def test_safe_file_no_output(self):
        data = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/utils.py"}})
        code, output = self._run_main(data)
        assert code == 0
        assert output.strip() == ""

    def test_setup_keyword_hint(self):
        data = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "setup.cfg"}})
        code, output = self._run_main(data)
        assert code == 0
        parsed = json.loads(output)
        assert "additionalContext" in parsed

    def test_whitespace_only_stdin(self):
        code, _ = self._run_main("   \n  \n  ")
        assert code == 0
