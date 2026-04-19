"""Tests for _check_pin_drift in forge_workflow.cli.doctor."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from forge_workflow.cli.doctor import _check_pin_drift

REPO_URL = "https://github.com/jp5labs/forge-workflow.git"


def _write_pyproject(tmp_path: Path, dep_line: str) -> Path:
    """Write a minimal pyproject.toml with the given dependency line."""
    content = f'[project]\ndependencies = [\n    "{dep_line}",\n]\n'
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(content)
    return tmp_path


class TestCheckPinDrift:
    """Tests for _check_pin_drift."""

    @patch("forge_workflow.__version__", "0.2.6")
    def test_matching_version(self, tmp_path: Path) -> None:
        root = _write_pyproject(
            tmp_path,
            f"forge-workflow @ git+{REPO_URL}@v0.2.6",
        )
        result = _check_pin_drift(root)
        assert result is not None
        passed, detail = result
        assert passed is True
        assert "matches installed" in detail

    @patch("forge_workflow.__version__", "0.2.6")
    def test_mismatched_version(self, tmp_path: Path) -> None:
        root = _write_pyproject(
            tmp_path,
            f"forge-workflow @ git+{REPO_URL}@v0.1.3",
        )
        result = _check_pin_drift(root)
        assert result is not None
        passed, detail = result
        assert passed is False
        assert "v0.1.3" in detail
        assert "v0.2.6" in detail
        assert "forge pin" in detail

    def test_no_pin_found(self, tmp_path: Path) -> None:
        """No forge-workflow dependency at all."""
        root = _write_pyproject(tmp_path, "some-other-package>=1.0")
        result = _check_pin_drift(root)
        assert result is None

    def test_no_pyproject(self, tmp_path: Path) -> None:
        """No pyproject.toml file."""
        result = _check_pin_drift(tmp_path)
        assert result is None

    @patch("forge_workflow.__version__", "1.0.0")
    def test_hyphenated_tag(self, tmp_path: Path) -> None:
        """Tags with hyphens (e.g. v1.0.0-rc1) should be matched."""
        root = _write_pyproject(
            tmp_path,
            f"forge-workflow @ git+{REPO_URL}@v1.0.0-rc1",
        )
        result = _check_pin_drift(root)
        assert result is not None
        passed, detail = result
        assert passed is False
        assert "v1.0.0-rc1" in detail

    @patch("forge_workflow.__version__", "0.2.7.dev8")
    def test_dev_version_match(self, tmp_path: Path) -> None:
        """Dev versions like v0.2.7.dev8 should match."""
        root = _write_pyproject(
            tmp_path,
            f"forge-workflow @ git+{REPO_URL}@v0.2.7.dev8",
        )
        result = _check_pin_drift(root)
        assert result is not None
        passed, detail = result
        assert passed is True

    @patch("forge_workflow.__version__", "0.2.6")
    def test_no_v_prefix(self, tmp_path: Path) -> None:
        """Pin without 'v' prefix should still match."""
        root = _write_pyproject(
            tmp_path,
            f"forge-workflow @ git+{REPO_URL}@0.2.6",
        )
        result = _check_pin_drift(root)
        assert result is not None
        passed, detail = result
        assert passed is True

    @patch("forge_workflow.__version__", "0.2.6")
    def test_pin_to_main_no_tag(self, tmp_path: Path) -> None:
        """Pin without @tag (pointing at main) should not be flagged."""
        root = _write_pyproject(
            tmp_path,
            f"forge-workflow @ git+{REPO_URL}",
        )
        result = _check_pin_drift(root)
        assert result is None
