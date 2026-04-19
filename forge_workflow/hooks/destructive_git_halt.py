#!/usr/bin/env python3
"""
Destructive Git Halt -- PreToolUse hook.

Detects destructive git commands that are also in the deny list.
If one reaches this hook, the deny list was bypassed -- halt immediately.

Hook Type: PreToolUse
Matcher: Bash
Exit Codes:
  0 - Allow (command is safe)
  2 - Block (destructive git command detected -- halt session)
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from forge_workflow.hooks._repo_root import REPO_ROOT

HALT_FILE = os.path.join(REPO_ROOT, "tmp", "circuit-breaker-halt.json")

DESTRUCTIVE_PATTERNS = [
    r"^\s*git\s+push\s+--force(?!-with-lease)\b",
    r"^\s*git\s+push\s+-f\b",
    r"^\s*git\s+reset\s+--hard\b",
    r"^\s*git\s+clean\s+-f",
    r"^\s*git\s+checkout\s+\.\s*$",
    r"^\s*git\s+checkout\s+\.\s+",
    r"^\s*git\s+restore\s+\.\s*$",
    r"^\s*git\s+restore\s+\.\s+",
]


def _write_halt(halt_file, command, matched_pattern):
    """Write halt file and fire notify."""
    halt_data = {
        "breaker": "destructive-git",
        "reason": f"Destructive git command detected: {command}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "context": {
            "command": command,
            "matched_pattern": matched_pattern,
        },
        "action": "halt",
    }
    os.makedirs(os.path.dirname(halt_file), exist_ok=True)
    with open(halt_file, "w") as f:
        json.dump(halt_data, f, indent=2)

    notify_script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "scripts", "hooks", "notify.sh",
    )
    notify_script = os.path.normpath(notify_script)
    if os.path.exists(notify_script):
        try:
            subprocess.Popen(
                ["bash", notify_script, "circuit-breaker"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def check_destructive(hook_input, halt_file=HALT_FILE):
    """Check if command is a destructive git operation."""
    tool_name = hook_input.get("tool_name", "")
    if tool_name != "Bash":
        return {"halted": False}

    command = hook_input.get("tool_input", {}).get("command", "")

    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command):
            _write_halt(halt_file, command, pattern)
            return {"halted": True}

    return {"halted": False}


def main():
    try:
        raw_input = sys.stdin.read()
        if not raw_input or not raw_input.strip():
            sys.exit(0)
        hook_input = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError, EOFError):
        sys.exit(0)

    result = check_destructive(hook_input)

    if result["halted"]:
        print(
            "CIRCUIT BREAKER TRIPPED: destructive-git. "
            "Read tmp/circuit-breaker-halt.json for details, "
            "notify via Discord, then halt.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
