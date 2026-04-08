#!/usr/bin/env python3
"""PermissionRequest hook: log re-approval prompts.

Fires every time Claude Code is about to show a permission prompt
(i.e., the command is NOT in the allow list). Appends one JSONL line
to /tmp/forge-approval-log.jsonl for later analysis by /approval-hygiene.

Always exits 0 -- observational only, never blocks.
"""
import json
import os
import sys
from datetime import datetime, timezone

LOG_PATH = "/tmp/forge-approval-log.jsonl"
MAX_INPUT_LEN = 1024


def _summarise_input(tool_name, tool_input):
    """For Write/Edit tools, capture only metadata -- not full file content."""
    if tool_name in ("Write", "Edit"):
        summary = {}
        for key in ("file_path", "old_string", "new_string", "description"):
            if key in tool_input:
                val = tool_input[key]
                if isinstance(val, str) and len(val) > MAX_INPUT_LEN:
                    summary[key] = val[:MAX_INPUT_LEN] + "...<truncated>"
                else:
                    summary[key] = val
        # Always include file_path even if it wasn't iterated
        if "file_path" in tool_input and "file_path" not in summary:
            summary["file_path"] = tool_input["file_path"]
        return summary
    return tool_input


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    session_id = data.get("session_id", "")

    if not tool_name:
        return

    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": tool_name,
        "input": _summarise_input(tool_name, tool_input),
        "session_id": session_id,
    }

    fd = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
