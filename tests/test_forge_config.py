"""Tests for forge_workflow.config module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from forge_workflow import config as forge_config


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the config cache before and after each test."""
    forge_config._invalidate_cache()
    yield
    forge_config._invalidate_cache()


@pytest.fixture
def forge_dir(tmp_path: Path) -> Path:
    """Create a minimal .forge/config.yaml in a temp directory."""
    forge_path = tmp_path / ".forge"
    forge_path.mkdir()
    config_data = {
        "forge": {"version": 1},
        "repo": {"org": "test-org", "name": "test-repo"},
    }
    with open(forge_path / "config.yaml", "w") as f:
        yaml.dump(config_data, f)
    return tmp_path


@pytest.fixture
def forge_dir_with_local(forge_dir: Path) -> Path:
    """Create a .forge directory with both config.yaml and config.local.yaml."""
    local_config = {
        "repo": {"org": "local-org"},
        "hooks": {"mode": "interactive"},
    }
    with open(forge_dir / ".forge" / "config.local.yaml", "w") as f:
        yaml.dump(local_config, f)
    return forge_dir


class TestLoad:
    """Tests for config.load()."""

    def test_load_reads_config_yaml(self, forge_dir: Path) -> None:
        config = forge_config.load(root=forge_dir)
        assert config["forge"]["version"] == 1
        assert config["repo"]["org"] == "test-org"
        assert config["repo"]["name"] == "test-repo"

    def test_load_caches_result(self, forge_dir: Path) -> None:
        config1 = forge_config.load(root=forge_dir)
        config2 = forge_config.load(root=forge_dir)
        assert config1 is config2

    def test_load_raises_on_missing_root(self, tmp_path: Path) -> None:
        """load() with a root that has no .forge/ returns empty-ish config."""
        # When root has no config, it falls through to runtime detection
        with patch.object(forge_config, "_detect_repo_identity", return_value={}):
            config = forge_config.load(root=tmp_path)
            # No config file found, so config is minimal
            assert "forge" not in config


class TestGet:
    """Tests for config.get() with dot-notation access."""

    def test_get_simple_key(self, forge_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(forge_dir)
        assert forge_config.get("forge.version") == 1

    def test_get_nested_key(self, forge_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(forge_dir)
        assert forge_config.get("repo.org") == "test-org"
        assert forge_config.get("repo.name") == "test-repo"

    def test_get_missing_key_returns_default(self, forge_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(forge_dir)
        assert forge_config.get("nonexistent.key") is None
        assert forge_config.get("nonexistent.key", "fallback") == "fallback"

    def test_get_with_env_var_override(self, forge_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(forge_dir)
        with patch.dict(os.environ, {"FORGE_REPO_ORG": "env-org"}):
            forge_config._invalidate_cache()
            assert forge_config.get("repo.org") == "env-org"
            # Name should still come from file
            assert forge_config.get("repo.name") == "test-repo"


class TestResolutionChain:
    """Tests for config resolution priority: env > local > yaml."""

    def test_local_overrides_yaml(self, forge_dir_with_local: Path) -> None:
        config = forge_config.load(root=forge_dir_with_local)
        # local overrides org
        assert config["repo"]["org"] == "local-org"
        # yaml value preserved when not overridden
        assert config["repo"]["name"] == "test-repo"
        # local adds new key
        assert config["hooks"]["mode"] == "interactive"

    def test_env_overrides_local(self, forge_dir_with_local: Path) -> None:
        with patch.dict(os.environ, {"FORGE_REPO_ORG": "env-org"}):
            config = forge_config.load(root=forge_dir_with_local)
            # env beats local
            assert config["repo"]["org"] == "env-org"

    def test_env_overrides_yaml(self, forge_dir: Path) -> None:
        with patch.dict(
            os.environ,
            {"FORGE_REPO_ORG": "env-org", "FORGE_REPO_NAME": "env-repo"},
        ):
            config = forge_config.load(root=forge_dir)
            assert config["repo"]["org"] == "env-org"
            assert config["repo"]["name"] == "env-repo"


class TestSetValue:
    """Tests for config.set_value()."""

    def test_set_value_updates_file(self, forge_dir: Path) -> None:
        cfg_path = forge_dir / ".forge" / "config.yaml"
        forge_config.set_value("repo.org", "new-org", config_file=cfg_path)

        # Re-read file directly
        with open(cfg_path) as f:
            data = yaml.safe_load(f)
        assert data["repo"]["org"] == "new-org"

    def test_set_value_validates(self, forge_dir: Path) -> None:
        cfg_path = forge_dir / ".forge" / "config.yaml"
        # Removing a required field should fail validation
        # First, create a config missing forge.version
        with open(cfg_path, "w") as f:
            yaml.dump({"repo": {"org": "x", "name": "y"}}, f)

        # Setting a non-required field should fail because forge.version is missing
        with pytest.raises(ValueError, match="forge.version"):
            forge_config.set_value("hooks.mode", "interactive", config_file=cfg_path)

    def test_set_value_type_coercion(self, forge_dir: Path) -> None:
        cfg_path = forge_dir / ".forge" / "config.yaml"
        forge_config.set_value("forge.version", "2", config_file=cfg_path)

        with open(cfg_path) as f:
            data = yaml.safe_load(f)
        assert data["forge"]["version"] == 2
        assert isinstance(data["forge"]["version"], int)


class TestValidate:
    """Tests for config.validate()."""

    def test_valid_config(self, forge_dir: Path) -> None:
        config = forge_config.load(root=forge_dir)
        errors = forge_config.validate(config)
        assert errors == []

    def test_missing_required_fields(self) -> None:
        errors = forge_config.validate({})
        assert len(errors) == 3
        assert any("forge.version" in e for e in errors)
        assert any("repo.org" in e for e in errors)
        assert any("repo.name" in e for e in errors)

    def test_partial_missing_fields(self) -> None:
        config = {"forge": {"version": 1}, "repo": {"org": "x"}}
        errors = forge_config.validate(config)
        assert len(errors) == 1
        assert "repo.name" in errors[0]

    def test_empty_string_field(self) -> None:
        config = {"forge": {"version": 1}, "repo": {"org": "", "name": "x"}}
        errors = forge_config.validate(config)
        assert len(errors) == 1
        assert "repo.org" in errors[0]


class TestRepoSlug:
    """Tests for config.repo_slug()."""

    def test_repo_slug_format(self, forge_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(forge_dir)
        assert forge_config.repo_slug() == "test-org/test-repo"

    def test_repo_slug_with_env_override(self, forge_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(forge_dir)
        with patch.dict(os.environ, {"FORGE_REPO_ORG": "env-org"}):
            forge_config._invalidate_cache()
            assert forge_config.repo_slug() == "env-org/test-repo"


class TestConfigPath:
    """Tests for config.config_path()."""

    def test_returns_path(self, forge_dir: Path) -> None:
        path = forge_config.config_path(root=forge_dir)
        assert path == forge_dir / ".forge" / "config.yaml"
        assert path.is_file()

    def test_raises_when_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Use a subdir with no .forge/ anywhere in parents
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        monkeypatch.chdir(isolated)
        with pytest.raises(FileNotFoundError):
            # Do not pass root= so it uses _find_repo_root via cwd
            forge_config.config_path()
