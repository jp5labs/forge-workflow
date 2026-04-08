"""Tests for circuit breaker hooks."""

import json

import pytest

from forge_workflow.hooks.circuit_breaker_init import init_circuit_breakers
from forge_workflow.hooks.destructive_git_halt import check_destructive
from forge_workflow.hooks.secret_file_scanner import escalate_secret_detection
from forge_workflow.hooks.sequential_failure_breaker import check_failure, get_threshold


class TestCircuitBreakerInit:
    """Tests for circuit-breaker-init.py."""

    def test_wipes_state_directory(self, tmp_path):
        """State directory is cleared on init."""
        state_dir = tmp_path / "circuit-breaker-state"
        state_dir.mkdir()
        (state_dir / "sequential-failures.json").write_text('{"count": 3}')
        (state_dir / "secret-detections.json").write_text('{"count": 1}')

        init_circuit_breakers(str(state_dir))

        assert state_dir.exists()
        assert list(state_dir.iterdir()) == []

    def test_creates_state_directory_if_missing(self, tmp_path):
        """State directory is created if it doesn't exist."""
        state_dir = tmp_path / "circuit-breaker-state"

        init_circuit_breakers(str(state_dir))

        assert state_dir.exists()

    def test_removes_halt_file(self, tmp_path):
        """Halt file from previous session is removed."""
        halt_file = tmp_path / "circuit-breaker-halt.json"
        halt_file.write_text('{"breaker": "old"}')

        init_circuit_breakers(
            str(tmp_path / "circuit-breaker-state"),
            halt_file=str(halt_file),
        )

        assert not halt_file.exists()


class TestSequentialFailureBreaker:
    """Tests for sequential-failure-breaker.py."""

    def test_increments_on_failure(self, tmp_path):
        """Failure count increments on non-zero exit code."""
        state_dir = tmp_path / "circuit-breaker-state"
        state_dir.mkdir()

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_response": "Error: command not found",
            "was_error": True,
        }

        result = check_failure(hook_input, state_dir=str(state_dir), threshold=5)
        assert result["count"] == 1
        assert result["halted"] is False

    def test_resets_on_success(self, tmp_path):
        """Counter resets to 0 on successful tool execution."""
        state_dir = tmp_path / "circuit-breaker-state"
        state_dir.mkdir()
        state_file = state_dir / "sequential-failures.json"
        state_file.write_text(json.dumps({"count": 3, "last_error": "old"}))

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "tool_response": "On branch main",
            "was_error": False,
        }

        result = check_failure(hook_input, state_dir=str(state_dir), threshold=5)
        assert result["count"] == 0
        assert result["halted"] is False

    def test_halts_at_threshold(self, tmp_path):
        """Session halts when consecutive failures reach threshold."""
        state_dir = tmp_path / "circuit-breaker-state"
        state_dir.mkdir()
        halt_file = tmp_path / "circuit-breaker-halt.json"
        state_file = state_dir / "sequential-failures.json"
        state_file.write_text(json.dumps({"count": 4, "last_error": "previous"}))

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
            "tool_response": "Error: command not found",
            "was_error": True,
        }

        result = check_failure(
            hook_input,
            state_dir=str(state_dir),
            halt_file=str(halt_file),
            threshold=5,
        )
        assert result["count"] == 5
        assert result["halted"] is True
        assert halt_file.exists()

        halt_data = json.loads(halt_file.read_text())
        assert halt_data["breaker"] == "sequential-failure"
        assert halt_data["action"] == "halt"

    def test_ignores_non_bash_tools(self, tmp_path):
        """Non-Bash tools are ignored (no count change)."""
        state_dir = tmp_path / "circuit-breaker-state"
        state_dir.mkdir()

        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/nonexistent"},
            "tool_response": "File not found",
            "was_error": True,
        }

        result = check_failure(hook_input, state_dir=str(state_dir), threshold=5)
        assert result["count"] == 0
        assert result["halted"] is False

    def test_threshold_from_env(self, tmp_path, monkeypatch):
        """CB_FAILURE_LIMIT env var overrides default threshold."""
        monkeypatch.setenv("CB_FAILURE_LIMIT", "3")

        assert get_threshold() == 3


class TestDestructiveGitHalt:
    """Tests for destructive-git-halt.py."""

    @pytest.mark.parametrize("command", [
        "git push --force origin main",
        "git push -f origin main",
        "git reset --hard HEAD~1",
        "git reset --hard origin/main",
        "git clean -fd",
        "git clean -f",
        "git checkout .",
        "git checkout . -- src/",
        "git restore .",
        "git restore . -- src/",
    ])
    def test_halts_on_destructive_commands(self, tmp_path, command):
        """Destructive git commands trigger halt."""
        halt_file = tmp_path / "circuit-breaker-halt.json"

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }

        result = check_destructive(hook_input, halt_file=str(halt_file))
        assert result["halted"] is True
        assert halt_file.exists()

        halt_data = json.loads(halt_file.read_text())
        assert halt_data["breaker"] == "destructive-git"
        assert halt_data["action"] == "halt"

    @pytest.mark.parametrize("command", [
        "git push origin feature-branch",
        "git push --force-with-lease origin feature",
        "git reset HEAD file.txt",
        "git branch -d feature-branch",
        "git branch -D feature-branch",
        "git checkout main",
        "git checkout -b new-branch",
        "git restore --staged file.txt",
        "git status",
        "git log --oneline",
        "npm test",
    ])
    def test_allows_safe_commands(self, tmp_path, command):
        """Safe commands pass through without halt."""
        halt_file = tmp_path / "circuit-breaker-halt.json"

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }

        result = check_destructive(hook_input, halt_file=str(halt_file))
        assert result["halted"] is False
        assert not halt_file.exists()

    def test_ignores_non_bash_tools(self, tmp_path):
        """Non-Bash tools are ignored."""
        halt_file = tmp_path / "circuit-breaker-halt.json"

        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/workspace/file.py"},
        }

        result = check_destructive(hook_input, halt_file=str(halt_file))
        assert result["halted"] is False


class TestSecretEscalation:
    """Tests for secret detection escalation in autonomous mode."""

    def test_increments_counter_on_detection(self, tmp_path, monkeypatch):
        """Secret detection increments escalation counter."""
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        state_dir = tmp_path / "circuit-breaker-state"
        state_dir.mkdir()

        result = escalate_secret_detection(
            "password detected",
            state_dir=str(state_dir),
            halt_file=str(tmp_path / "halt.json"),
            threshold=3,
        )
        assert result["count"] == 1
        assert result["halted"] is False

    def test_halts_at_threshold(self, tmp_path, monkeypatch):
        """Session halts after 3 secret detections."""
        monkeypatch.setenv("CLAUDE_MODE", "autonomous")
        state_dir = tmp_path / "circuit-breaker-state"
        state_dir.mkdir()
        halt_file = tmp_path / "halt.json"

        # Pre-seed with 2 detections
        (state_dir / "secret-detections.json").write_text(
            json.dumps({"count": 2, "detections": ["first", "second"]})
        )

        result = escalate_secret_detection(
            "third secret found",
            state_dir=str(state_dir),
            halt_file=str(halt_file),
            threshold=3,
        )
        assert result["count"] == 3
        assert result["halted"] is True
        assert halt_file.exists()

    def test_no_escalation_in_supervised_mode(self, tmp_path, monkeypatch):
        """Supervised mode does not use escalation counter."""
        monkeypatch.setenv("CLAUDE_MODE", "supervised")
        state_dir = tmp_path / "circuit-breaker-state"
        state_dir.mkdir()

        result = escalate_secret_detection(
            "password detected",
            state_dir=str(state_dir),
            halt_file=str(tmp_path / "halt.json"),
            threshold=3,
        )
        assert result["count"] == 0
        assert result["halted"] is False
