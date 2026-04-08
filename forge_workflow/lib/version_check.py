"""Passive version check for forge-workflow.

Checks GitHub releases API for newer versions. Results are cached
in ~/.forge/update-check.json for 24 hours to avoid spamming the API.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from forge_workflow import __version__

REPO_URL = "https://github.com/jp5labs/forge-workflow.git"
GITHUB_API_URL = "https://api.github.com/repos/jp5labs/forge-workflow/releases/latest"
CACHE_FILE = Path.home() / ".forge" / "update-check.json"
CHECK_INTERVAL_SECONDS = 86400  # 24 hours


def _read_cache() -> dict | None:
    """Read cached update check result."""
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text())
            if time.time() - data.get("checked_at", 0) < CHECK_INTERVAL_SECONDS:
                return data
    except (json.JSONDecodeError, OSError, KeyError):
        pass
    return None


def _write_cache(latest_version: str | None, is_outdated: bool) -> None:
    """Write update check result to cache."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps({
            "checked_at": time.time(),
            "latest_version": latest_version,
            "current_version": __version__,
            "is_outdated": is_outdated,
        }))
    except OSError:
        pass


def _fetch_latest_version() -> str | None:
    """Fetch the latest release tag from GitHub API."""
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            tag = data.get("tag_name", "")
            # Strip leading 'v' for comparison
            return tag.lstrip("v") if tag else None
    except (urllib.error.URLError, json.JSONDecodeError, OSError, KeyError):
        return None


def check_for_update(force: bool = False) -> str | None:
    """Check if a newer version is available.

    Returns a message string if outdated, None if current or unable to check.
    Uses cached result unless force=True or cache is expired (>24h).
    """
    if os.environ.get("FORGE_SKIP_UPDATE_CHECK") == "1":
        return None

    # Check cache first (unless forced)
    if not force:
        cached = _read_cache()
        if cached is not None:
            if cached.get("is_outdated") and cached.get("latest_version"):
                return (
                    f"forge {__version__} installed, "
                    f"{cached['latest_version']} available "
                    f"— run 'forge self-update'"
                )
            return None

    # Fetch from GitHub
    latest = _fetch_latest_version()
    if latest is None:
        _write_cache(None, False)
        return None

    is_outdated = latest != __version__
    _write_cache(latest, is_outdated)

    if is_outdated:
        return (
            f"forge {__version__} installed, "
            f"{latest} available — run 'forge self-update'"
        )
    return None
