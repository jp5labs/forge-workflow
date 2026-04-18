#!/usr/bin/env python3
"""
Sequential Failure Breaker -- PostToolUse hook.

Counts consecutive Bash tool failures. Halts session when threshold is reached.
Resets counter on any successful Bash execution.

Hook Type: PostToolUse
Matcher: Bash
Exit Codes:
  0 - Allow (continue session)
  2 - Block (circuit breaker tripped -- halt session)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from forge_workflow.hooks._repo_root import REPO_ROOT
STATE_DIR = os.path.join(REPO_ROOT, "tmp", "circuit-breaker-state")
HALT_FILE = os.path.join(REPO_ROOT, "tmp", "circuit-breaker-halt.json")
NOTIFY_SCRIPT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "scripts", "hooks", "notify.sh",
))


def get_threshold():
    """Get failure threshold from env var or default."""
    try:
        return int(os.environ.get("CB_FAILURE_LIMIT", "5"))
    except ValueError:
        return 5


def _read_state(state_dir):
    """Read current failure count from state file."""
    state_file = os.path.join(state_dir, "sequential-failures.json")
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"count": 0, "last_error": ""}


def _write_state(state_dir, state):
    """Write failure count to state file."""
    os.makedirs(state_dir, exist_ok=True)
    state_file = os.path.join(state_dir, "sequential-failures.json")
    with open(state_file, "w") as f:
        json.dump(state, f)


def _write_halt(halt_file, count, last_command, last_error):
    """Write halt file and fire notify."""
    halt_data = {
        "breaker": "sequential-failure",
        "reason": f"{count} consecutive tool failures detected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "context": {
            "failure_count": count,
            "last_tool": "Bash",
            "last_command": last_command,
            "last_error": last_error[:500],
        },
        "action": "halt",
    }
    os.makedirs(os.path.dirname(halt_file), exist_ok=True)
    with open(halt_file, "w") as f:
        json.dump(halt_data, f, indent=2)

    # Fire notify webhook as audit trail
    if os.path.exists(NOTIFY_SCRIPT):
        try:
            subprocess.Popen(
                ["bash", NOTIFY_SCRIPT, "circuit-breaker"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def check_failure(hook_input, state_dir=STATE_DIR, halt_file=HALT_FILE, threshold=None):
    """Check tool result and update failure counter."""
    if threshold is None:
        threshold = get_threshold()

    tool_name = hook_input.get("tool_name", "")

    if tool_name != "Bash":
        return {"count": 0, "halted": False}

    was_error = hook_input.get("was_error", False)
    state = _read_state(state_dir)

    if not was_error:
        state = {"count": 0, "last_error": ""}
        _write_state(state_dir, state)
        return {"count": 0, "halted": False}

    state["count"] = state.get("count", 0) + 1
    state["last_error"] = str(hook_input.get("tool_response", ""))[:500]
    _write_state(state_dir, state)

    if state["count"] >= threshold:
        command = hook_input.get("tool_input", {}).get("command", "unknown")
        _write_halt(halt_file, state["count"], command, state["last_error"])
        return {"count": state["count"], "halted": True}

    return {"count": state["count"], "halted": False}


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input or not raw_input.strip():
            sys.exit(0)
        hook_input = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError, EOFError):
        sys.exit(0)

    result = check_failure(hook_input)

    if result["halted"]:
        print(
            "CIRCUIT BREAKER TRIPPED: sequential-failure. "
            "Read tmp/circuit-breaker-halt.json for details, "
            "notify via Discord, then halt.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
