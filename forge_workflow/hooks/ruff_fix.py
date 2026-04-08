#!/usr/bin/env python3
"""PostToolUse hook: run ruff --fix on edited Python files."""
import json
import os
import subprocess
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    path = data.get("tool_input", {}).get("file_path", "")
    if not path.endswith(".py"):
        sys.exit(0)
    if not os.path.exists(path):
        sys.exit(0)

    try:
        result = subprocess.run(["ruff", "check", "--fix", path], capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit(0)  # ruff not installed; skip silently
    if result.returncode not in (0, 1):
        sys.exit(0)
    if result.stdout.strip():
        print(result.stdout.strip())


if __name__ == "__main__":
    main()
