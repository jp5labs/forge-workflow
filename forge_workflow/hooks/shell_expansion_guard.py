#!/usr/bin/env python3
"""PreToolUse hook: block ${} variable expansion in Bash commands.

Claude Code's platform flags ${} as a shell injection risk and prompts
for approval -- even in bypassPermissions mode. In autonomous (unattended)
mode this causes a session stall with no human to approve.

This hook catches ${} before the platform does, returns a hard block
with actionable guidance, so the bot retries with a safe alternative
instead of stalling.

Active in both autonomous and supervised modes.
"""

import json
import re
import sys

# ${...} pattern -- match ${ followed by any content and closing }
# Exclude $() which is handled by compound_command_interceptor.py
SHELL_VAR_EXPANSION = re.compile(r"\$\{[^}]*\}")


GUIDANCE = """\
[HOOK] Shell variable expansion ${} blocked.

${} in Bash commands triggers a platform-level approval prompt that
stalls unattended sessions. Use direct alternatives instead:

1. **Read an env var** -- use `printenv VAR_NAME` or `env | grep VAR_NAME`
2. **Default values** -- run `printenv VAR_NAME`, check the output in-context,
   and use the value (or your default) in the next command.
3. **String interpolation** -- construct the full command string in-context
   using values from previous tool calls.

Common replacements:
- `echo "${CLAUDE_MODE}"` -> `printenv CLAUDE_MODE`
- `echo "${VAR:-default}"` -> `printenv VAR` then handle empty in-context
- `cmd --flag "${VALUE}"` -> get VALUE via printenv, then `cmd --flag <literal>`"""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command or not command.strip():
        return

    if SHELL_VAR_EXPANSION.search(command):
        result = {
            "decision": "block",
            "reason": GUIDANCE,
        }
        print(json.dumps(result))
        sys.exit(2)


try:
    main()
except Exception:
    # Best-effort -- never block session on hook failure
    pass
