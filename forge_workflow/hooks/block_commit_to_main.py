#!/usr/bin/env python3
"""PreToolUse hook: block git commit on main.

Fires on every Bash tool call. Blocks if the command is a git commit
and the current branch is main or master (exit 2).

Exits 2 (blocking) when committing to main.
Exits 0 (pass-through) for all other commands.
"""
import json
import re
import subprocess
import sys

BLOCK_MESSAGE = """\
[HOOK] Direct commit to main blocked.

All changes must go through a PR with review. Create a feature branch first:
  git checkout -b issue-<N>-<slug>

See CLAUDE.md ### Delivery workflow for details.
"""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool_input = data.get('tool_input', {})
    command = tool_input.get('command', '')

    if not command:
        return

    # Only act on git commit commands
    if not re.match(r'^\s*git\s+commit\b', command):
        return

    # Check current branch
    try:
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return

    if branch == 'main' or branch == 'master':
        print(BLOCK_MESSAGE)
        sys.exit(2)


try:
    main()
except Exception:
    pass
