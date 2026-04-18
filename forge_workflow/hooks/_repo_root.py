"""Shared REPO_ROOT resolution for all hooks.

When pip-installed, __file__-based dirname traversal resolves to the
site-packages directory -- not the project repo.  This module uses
``git rev-parse --show-toplevel`` (with a cwd fallback) so hooks
reliably find the repo they are operating on.
"""

import os
import subprocess


def _get_repo_root() -> str:
    """Return the repository root directory.

    Resolution order:
      1. ``REPO_ROOT`` environment variable (explicit override).
      2. ``git rev-parse --show-toplevel`` (works inside any git repo).
      3. Current working directory (last resort).
    """
    explicit = os.environ.get("REPO_ROOT")
    if explicit:
        return explicit
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return os.getcwd()


REPO_ROOT = _get_repo_root()
