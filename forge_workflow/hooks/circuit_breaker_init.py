#!/usr/bin/env python3
"""
Circuit Breaker Init -- SessionStart hook.

Wipes circuit breaker state files so each session starts clean.
Also removes any halt file left over from a previous session.

Hook Type: SessionStart
Exit Codes:
  0 - Always (never blocks session start)
"""

import os
import shutil
import sys

REPO_ROOT = os.environ.get(
    "REPO_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
STATE_DIR = os.path.join(REPO_ROOT, "tmp", "circuit-breaker-state")
HALT_FILE = os.path.join(REPO_ROOT, "tmp", "circuit-breaker-halt.json")


def init_circuit_breakers(state_dir=STATE_DIR, halt_file=HALT_FILE):
    """Wipe state directory and halt file."""
    # Remove and recreate state dir
    if os.path.exists(state_dir):
        shutil.rmtree(state_dir)
    os.makedirs(state_dir, exist_ok=True)

    # Remove stale halt file
    if os.path.exists(halt_file):
        os.remove(halt_file)


def main():
    try:
        init_circuit_breakers()
    except Exception:
        pass  # Never block session start
    sys.exit(0)


if __name__ == "__main__":
    main()
