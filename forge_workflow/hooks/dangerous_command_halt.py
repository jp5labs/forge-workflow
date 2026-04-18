#!/usr/bin/env python3
"""
Dangerous Command Halt -- PreToolUse hook.

Detects non-git destructive commands that are also in the deny list.
If one reaches this hook, the deny list was bypassed -- halt immediately.

Hook Type: PreToolUse
Matcher: Bash
Exit Codes:
  0 - Allow (command is safe)
  2 - Block (dangerous command detected -- halt session)
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from forge_workflow.hooks._repo_root import REPO_ROOT

HALT_FILE = os.path.join(REPO_ROOT, "tmp", "circuit-breaker-halt.json")

DANGEROUS_PATTERNS = [
    (re.compile(r"^\s*rm\s+(-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)\b"), "recursive-delete"),
    (re.compile(r"^\s*sudo\s+"), "sudo"),
    (re.compile(r"mv\s+.*\s+/dev/null"), "mv-to-devnull"),
    (re.compile(r"mv\s+/dev/null"), "mv-from-devnull"),
    (re.compile(r"^\s*gh\s+release\s+create"), "gh-release-create"),
    (re.compile(r"gh\s+api\s+(-X|--method)\s+DELETE"), "gh-api-delete"),
    (re.compile(r"^\s*gh\s+repo\s+delete"), "gh-repo-delete"),
    (re.compile(r"^\s*git\s+config\s+--global"), "git-config-global"),
]

# Exempt path prefixes for recursive delete -- ALL targets must match one
EXEMPT_RM_PREFIXES = [
    "tmp/",
    "/tmp/jp5-",
]


def _is_exempt_rm(command):
    """Return True if the rm command targets only exempt paths.

    Parses path arguments from the command and verifies every target
    matches an exempt prefix. Rejects paths containing '..' components.
    """
    # Strip the rm command and flags to get just the path arguments
    parts = command.strip().split()
    # Skip 'rm' and any flag arguments (start with -)
    paths = [p for p in parts[1:] if not p.startswith("-")]

    if not paths:
        return False

    for path in paths:
        # Reject path traversal
        if ".." in path.split("/"):
            return False
        # Check if this path matches any exempt prefix
        if not any(path.startswith(prefix) for prefix in EXEMPT_RM_PREFIXES):
            return False

    return True


def _write_halt(halt_file, command, matched_pattern):
    """Write halt file and fire notify."""
    halt_data = {
        "breaker": "dangerous-command",
        "reason": f"Dangerous command detected: {command}",
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


def check_dangerous(hook_input, halt_file=HALT_FILE):
    """Check if command is a dangerous operation."""
    tool_name = hook_input.get("tool_name", "")
    if tool_name != "Bash":
        return {"halted": False}

    command = hook_input.get("tool_input", {}).get("command", "")

    for pattern, label in DANGEROUS_PATTERNS:
        if pattern.search(command):
            # For rm patterns, check exemptions first
            if label == "recursive-delete" and _is_exempt_rm(command):
                continue
            _write_halt(halt_file, command, label)
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

    result = check_dangerous(hook_input)

    if result["halted"]:
        print(
            "CIRCUIT BREAKER TRIPPED: dangerous-command. "
            "Read tmp/circuit-breaker-halt.json for details, "
            "notify via Discord, then halt.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
