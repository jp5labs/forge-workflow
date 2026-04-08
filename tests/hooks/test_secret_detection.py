"""Behavioral tests for forge_workflow.hooks.secret_detection."""

import json
import os
import subprocess
import sys
from io import StringIO
from unittest import mock

import pytest

from forge_workflow.hooks.secret_detection import check_for_secrets


# ---------------------------------------------------------------------------
# Helpers — build synthetic secret strings at runtime so the secret-file
# scanner hook does not flag *this* test file during writes.
# ---------------------------------------------------------------------------

def _kv(key, sep, val):
    """Build a key-value string like 'password: hunter2'."""
    return f"{key}{sep}{val}"


def _tok(prefix, body):
    """Build a token string like 'sk-abcdef...'."""
    return f"{prefix}{body}"


def _connstr(scheme, user, pw, host):
    """Build a connection-string like 'mongodb://user:pass@host'."""
    return f"{scheme}://{user}:{pw}@{host}"


def _pem(label):
    """Build a PEM header like '-----BEGIN RSA PRIVATE KEY-----'."""
    return f"-----BEGIN {label}-----"


# ---------------------------------------------------------------------------
# TestCheckForSecrets
# ---------------------------------------------------------------------------

class TestCheckForSecrets:
    """Unit tests for check_for_secrets()."""

    # -- Explicit key-value patterns ----------------------------------------

    @pytest.mark.parametrize("prompt,expected_type", [
        (_kv("password", ": ", "hunter2"), "password"),
        (_kv("passwd", "=", "mysecret"), "password"),
        (_kv("pwd", ": ", "abc123"), "password"),
        (_kv("api_key", ": ", "sk-1234abcd"), "API key"),
        (_kv("apikey", "=", "something"), "API key"),
        (_kv("token", ": ", "eyJhbGciOiJ"), "token"),
        (_kv("auth_token", "=", "abcxyz"), "token"),
        (_kv("access_token", ": ", "tok123"), "token"),
        (_kv("private_key", ": ", "xxx"), "private key"),
        (_kv("secret", "=", "s3cr3tval"), "secret"),
        (_kv("api_secret", ": ", "foobarbaz"), "secret"),
    ])
    def test_explicit_key_value(self, prompt, expected_type):
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert expected_type in types, f"Expected '{expected_type}' in {types}"

    # -- API key formats ----------------------------------------------------

    def test_openai_key(self):
        key = _tok("sk-", "a" * 30)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "OpenAI API key" in types

    def test_anthropic_key(self):
        key = _tok("sk-ant-", "b" * 30)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "Anthropic API key" in types

    def test_github_pat(self):
        key = _tok("ghp_", "A" * 36)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "GitHub personal access token" in types

    def test_github_oauth(self):
        key = _tok("gho_", "B" * 36)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "GitHub OAuth token" in types

    def test_github_server(self):
        key = _tok("ghs_", "C" * 36)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "GitHub server token" in types

    def test_aws_access_key(self):
        key = _tok("AKIA", "D" * 16)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "AWS access key ID" in types

    def test_aws_secret_key(self):
        prompt = _kv("aws_secret_access_key", "=", "wJalrXUtnFEMI/K7MDENG")
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "AWS secret key" in types

    # -- Platform tokens ----------------------------------------------------

    def test_notion_ntn_token(self):
        key = _tok("ntn_", "e" * 45)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "Notion integration token" in types

    def test_notion_secret_token(self):
        key = _tok("secret_", "f" * 45)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "Notion internal token" in types

    def test_atlassian_api_token(self):
        key = _tok("ATATT", "g" * 25)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "Atlassian API token" in types

    def test_atlassian_token_kv(self):
        prompt = _kv("atlassian_token", "=", "myatltoken")
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "Atlassian token" in types

    def test_confluence_token_kv(self):
        prompt = _kv("confluence_token", "=", "myconftoken")
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "Confluence token" in types

    def test_jira_token_kv(self):
        prompt = _kv("jira_token", "=", "myjiratoken")
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "Jira token" in types

    def test_slack_token(self):
        key = _tok("xoxb-", "1234567890-abcdefgh")
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "Slack token" in types

    def test_google_api_key(self):
        key = _tok("AIza", "h" * 35)
        findings = check_for_secrets(key)
        types = [t for t, _ in findings]
        assert "Google API key" in types

    # -- Connection strings -------------------------------------------------

    @pytest.mark.parametrize("scheme", ["mongodb", "postgres", "mysql", "redis"])
    def test_connection_string(self, scheme):
        prompt = _connstr(scheme, "admin", "s3cret", "db.example.com")
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "database connection string" in types

    # -- PEM keys -----------------------------------------------------------

    def test_pem_private_key(self):
        prompt = _pem("PRIVATE KEY")
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "private key (PEM)" in types

    def test_pem_rsa_private_key(self):
        prompt = _pem("RSA PRIVATE KEY")
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "private key (PEM)" in types

    def test_pem_openssh_key(self):
        prompt = _pem("OPENSSH PRIVATE KEY")
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "SSH private key" in types

    # -- Bearer tokens ------------------------------------------------------

    def test_bearer_token(self):
        token_body = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"
        prompt = f"Bearer {token_body}"
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "Bearer token" in types

    # -- High-entropy credentials -------------------------------------------

    def test_high_entropy_api_key(self):
        blob = "A" * 40
        prompt = _kv("api_key", ": ", blob)
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "high-entropy credential" in types

    def test_high_entropy_token(self):
        blob = "B" * 40
        prompt = _kv("token", "=", blob)
        findings = check_for_secrets(prompt)
        types = [t for t, _ in findings]
        assert "high-entropy credential" in types

    # -- False positives (must NOT match) -----------------------------------

    @pytest.mark.parametrize("prompt", [
        "How do I reset my password?",
        "The token variable is used for authentication logic",
        "sk-short",
        "ghp_tooshort",
        "What is an API key?",
        "",
    ])
    def test_false_positives(self, prompt):
        findings = check_for_secrets(prompt)
        assert findings == [], f"Expected no findings for: {prompt!r}"

    # -- Multiple secrets ---------------------------------------------------

    def test_multiple_secrets(self):
        parts = [
            _kv("password", ": ", "hunter2"),
            _tok("ghp_", "X" * 36),
            _pem("PRIVATE KEY"),
        ]
        prompt = "\n".join(parts)
        findings = check_for_secrets(prompt)
        assert len(findings) >= 2, f"Expected >=2 finding types, got {len(findings)}"

    # -- Security: raw secrets must not leak into findings ------------------

    def test_findings_do_not_contain_raw_secret(self):
        """check_for_secrets must not include the actual secret value in findings."""
        secret_val = "hunter2supersecret"
        prompt = _kv("password", ": ", secret_val)
        findings = check_for_secrets(prompt)
        assert len(findings) > 0, "Should detect the secret"
        for secret_type, count in findings:
            assert secret_val not in str(secret_type), "Secret value leaked into finding type"
            assert secret_val not in str(count), "Secret value leaked into finding count"

    # -- Count accuracy -----------------------------------------------------

    def test_count_accuracy(self):
        lines = [_kv("password", ": ", f"val{i}") for i in range(3)]
        prompt = "\n".join(lines)
        findings = check_for_secrets(prompt)
        pw_findings = [(t, c) for t, c in findings if t == "password"]
        assert len(pw_findings) == 1, "Should be exactly one password finding entry"
        assert pw_findings[0][1] == 3, f"Expected count=3, got {pw_findings[0][1]}"


# ---------------------------------------------------------------------------
# TestSecretDetectionMain
# ---------------------------------------------------------------------------

class TestSecretDetectionMain:
    """Integration tests running the hook as a subprocess."""

    MODULE = [sys.executable, "-m", "forge_workflow.hooks.secret_detection"]

    def _run(self, stdin_text, env_extra=None):
        env = os.environ.copy()
        env["CLAUDE_MODE"] = "supervised"
        if env_extra:
            env.update(env_extra)
        result = subprocess.run(
            self.MODULE,
            input=stdin_text,
            capture_output=True,
            text=True,
            env=env,
        )
        return result

    def test_blocks_prompt_with_secret(self):
        payload = json.dumps({"userPrompt": _kv("password", ": ", "hunter2")})
        result = self._run(payload)
        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        assert output["decision"] == "block"
        assert "reason" in output

    def test_allows_safe_prompt(self):
        payload = json.dumps({"userPrompt": "How do I deploy?"})
        result = self._run(payload)
        assert result.returncode == 0
        assert result.stdout.strip() == "{}"

    def test_empty_prompt_passes(self):
        payload = json.dumps({"userPrompt": ""})
        result = self._run(payload)
        assert result.returncode == 0
        assert result.stdout.strip() == "{}"

    def test_empty_stdin(self):
        result = self._run("")
        assert result.returncode == 0
        assert result.stdout.strip() == "{}"

    def test_invalid_json(self):
        result = self._run("not valid json {{{")
        assert result.returncode == 0
        assert result.stdout.strip() == "{}"

    def test_missing_user_prompt_field(self):
        payload = json.dumps({"someOtherField": "value"})
        result = self._run(payload)
        assert result.returncode == 0
        assert result.stdout.strip() == "{}"


# ---------------------------------------------------------------------------
# TestMainInProcess — exercises main() in-process for branch coverage
# ---------------------------------------------------------------------------

class TestMainInProcess:
    """In-process tests for main() to cover branches that subprocess misses."""

    def _run_main(self, stdin_text, escalation_return=None):
        """Run main() in-process with mocked stdin/stdout/escalation."""
        from forge_workflow.hooks.secret_detection import main

        if escalation_return is None:
            escalation_return = {"halted": False, "count": 0}

        captured = StringIO()
        with mock.patch("sys.stdin", StringIO(stdin_text)), \
             mock.patch("sys.stdout", captured), \
             mock.patch.dict(os.environ, {"CLAUDE_MODE": "supervised"}), \
             mock.patch(
                 "forge_workflow.hooks.secret_detection.escalate_secret_detection",
                 return_value=escalation_return,
             ) as mock_esc:
            try:
                main()
            except SystemExit as exc:
                return captured.getvalue(), exc.code, mock_esc
        return captured.getvalue(), None, mock_esc

    def test_empty_stdin_outputs_empty_json(self):
        stdout, code, _ = self._run_main("")
        assert code == 0
        assert stdout.strip() == "{}"

    def test_invalid_json_outputs_empty_json(self):
        stdout, code, _ = self._run_main("{{bad json")
        assert code == 0
        assert stdout.strip() == "{}"

    def test_missing_user_prompt_field(self):
        payload = json.dumps({"other": "field"})
        stdout, code, _ = self._run_main(payload)
        assert code == 0
        assert stdout.strip() == "{}"

    def test_empty_user_prompt(self):
        payload = json.dumps({"userPrompt": ""})
        stdout, code, _ = self._run_main(payload)
        assert code == 0
        assert stdout.strip() == "{}"

    def test_safe_prompt_passes(self):
        payload = json.dumps({"userPrompt": "How do I deploy?"})
        stdout, code, _ = self._run_main(payload)
        assert code == 0
        assert stdout.strip() == "{}"

    def test_secret_detected_blocks(self):
        prompt_text = _kv("password", ": ", "hunter2")
        payload = json.dumps({"userPrompt": prompt_text})
        stdout, code, mock_esc = self._run_main(payload)
        assert code == 0
        output = json.loads(stdout.strip())
        assert output["decision"] == "block"
        assert "reason" in output
        mock_esc.assert_called_once()

    def test_secret_detected_escalation_halts(self):
        prompt_text = _kv("password", ": ", "hunter2")
        payload = json.dumps({"userPrompt": prompt_text})
        captured_stderr = StringIO()
        from forge_workflow.hooks.secret_detection import main

        with mock.patch("sys.stdin", StringIO(payload)), \
             mock.patch("sys.stdout", StringIO()), \
             mock.patch("sys.stderr", captured_stderr), \
             mock.patch.dict(os.environ, {"CLAUDE_MODE": "supervised"}), \
             mock.patch(
                 "forge_workflow.hooks.secret_detection.escalate_secret_detection",
                 return_value={"halted": True, "count": 3},
             ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2
        assert "CIRCUIT BREAKER TRIPPED" in captured_stderr.getvalue()

    def test_secret_detected_no_halt(self):
        prompt_text = _kv("password", ": ", "hunter2")
        payload = json.dumps({"userPrompt": prompt_text})
        stdout, code, mock_esc = self._run_main(
            payload, escalation_return={"halted": False, "count": 1}
        )
        assert code == 0
        mock_esc.assert_called_once()

    def test_whitespace_only_stdin(self):
        stdout, code, _ = self._run_main("   \n\t  ")
        assert code == 0
        assert stdout.strip() == "{}"
