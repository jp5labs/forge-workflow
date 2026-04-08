"""Forge config module — load, merge, validate, and access configuration.

Resolution chain (highest priority first):
1. Environment variables (FORGE_REPO_ORG, FORGE_REPO_NAME)
2. .forge/config.local.yaml (machine-level, gitignored)
3. .forge/config.yaml (repo-level, checked in)
4. Runtime detection via gh CLI (fallback for repo identity)
"""

from __future__ import annotations

import copy
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

# Required fields for a valid config (dot-notation paths)
REQUIRED_FIELDS = ["forge.version", "repo.org", "repo.name"]

# Env var to config key mapping
ENV_OVERRIDES: dict[str, str] = {
    "FORGE_REPO_ORG": "repo.org",
    "FORGE_REPO_NAME": "repo.name",
}

# Module-level cache
_cached_config: dict | None = None
_cached_root: Path | None = None


def _find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from start to find a directory containing .forge/config.yaml."""
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / ".forge" / "config.yaml"
        if candidate.is_file():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base, returning a new dict."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _set_nested(d: dict, key: str, value: Any) -> None:
    """Set a value in a nested dict using dot-notation key."""
    parts = key.split(".")
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _get_nested(d: dict, key: str, default: Any = None) -> Any:
    """Get a value from a nested dict using dot-notation key."""
    parts = key.split(".")
    current = d
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _detect_repo_identity() -> dict:
    """Detect repo org/name via gh CLI as fallback."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            name_with_owner = data.get("nameWithOwner", "")
            if "/" in name_with_owner:
                org, name = name_with_owner.split("/", 1)
                return {"repo": {"org": org, "name": name}}
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    return {}


def _apply_env_overrides(config: dict) -> dict:
    """Apply environment variable overrides to config."""
    result = copy.deepcopy(config)
    for env_var, config_key in ENV_OVERRIDES.items():
        value = os.environ.get(env_var)
        if value is not None:
            _set_nested(result, config_key, value)
    return result


def config_path(root: Path | None = None) -> Path:
    """Return the path to .forge/config.yaml."""
    repo_root = root or _find_repo_root()
    if repo_root is None:
        raise FileNotFoundError(
            "No .forge/config.yaml found in any parent directory."
        )
    return Path(repo_root) / ".forge" / "config.yaml"


def load(root: Path | None = None) -> dict:
    """Load and merge the full config resolution chain.

    Returns the resolved config dict. Caches the result for the session.
    """
    global _cached_config, _cached_root

    resolved_root = root or _find_repo_root()

    if _cached_config is not None and _cached_root == resolved_root:
        return _cached_config

    config: dict = {}

    # Layer 4: Runtime detection (lowest priority)
    detected = _detect_repo_identity()
    if detected:
        config = _deep_merge(config, detected)

    # Layer 3: .forge/config.yaml (repo-level)
    if resolved_root is not None:
        yaml_path = Path(resolved_root) / ".forge" / "config.yaml"
        if yaml_path.is_file():
            with open(yaml_path) as f:
                repo_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, repo_config)

        # Layer 2: .forge/config.local.yaml (machine-level)
        local_path = Path(resolved_root) / ".forge" / "config.local.yaml"
        if local_path.is_file():
            with open(local_path) as f:
                local_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, local_config)

    # Layer 1: Environment variables (highest priority)
    config = _apply_env_overrides(config)

    _cached_config = config
    _cached_root = resolved_root
    return config


def get(key: str, default: Any = None) -> Any:
    """Dot-notation access into the loaded config.

    Calls load() if not already cached.
    """
    config = load()
    return _get_nested(config, key, default)


def set_value(key: str, value: str, config_file: Path | None = None) -> None:
    """Update a key in .forge/config.yaml and validate.

    Raises ValueError if the resulting config is invalid.
    """
    target = config_file or config_path()
    target = Path(target)

    # Load existing file content
    if target.is_file():
        with open(target) as f:
            file_config = yaml.safe_load(f) or {}
    else:
        file_config = {}

    # Attempt type coercion for common types
    coerced_value: Any = value
    if value.lower() in ("true", "false"):
        coerced_value = value.lower() == "true"
    else:
        try:
            coerced_value = int(value)
        except ValueError:
            try:
                coerced_value = float(value)
            except ValueError:
                pass

    _set_nested(file_config, key, coerced_value)

    # Validate before writing
    errors = validate(file_config)
    if errors:
        raise ValueError(
            "Config validation failed after set:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    # Write back
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w") as f:
        yaml.dump(file_config, f, default_flow_style=False, sort_keys=False)

    # Invalidate cache
    _invalidate_cache()


def validate(config: dict | None = None) -> list[str]:
    """Validate config against schema. Returns list of errors (empty = valid).

    Required fields: forge.version, repo.org, repo.name.
    """
    if config is None:
        config = load()

    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        val = _get_nested(config, field)
        if val is None:
            errors.append(f"Required field '{field}' is missing.")
        elif isinstance(val, str) and not val.strip():
            errors.append(f"Required field '{field}' is empty.")
    return errors


def repo_slug() -> str:
    """Convenience: returns 'org/name' from config."""
    org = get("repo.org", "")
    name = get("repo.name", "")
    return f"{org}/{name}"


def _invalidate_cache() -> None:
    """Clear the module-level config cache."""
    global _cached_config, _cached_root
    _cached_config = None
    _cached_root = None
