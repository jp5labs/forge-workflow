"""Tests for forge_workflow.lib.scaffold.detect_existing."""

from __future__ import annotations

from pathlib import Path

from forge_workflow.lib.scaffold import (
    detect_existing,
)


class TestDetectExisting:
    """Tests for detect_existing() skill detection."""

    def _make_skill(self, target: Path, skill_name: str) -> None:
        """Helper: create a minimal skill directory with SKILL.md."""
        skill_dir = target / ".claude" / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(f"# {skill_name}")

    def test_detects_forge_prefixed_skills(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "forge-deliver")
        result = detect_existing(tmp_path)
        assert result["skills"] is True

    def test_detects_non_forge_prefixed_skills(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "adr-check")
        result = detect_existing(tmp_path)
        assert result["skills"] is True

    def test_detects_mixed_skills(self, tmp_path: Path) -> None:
        self._make_skill(tmp_path, "forge-plan")
        self._make_skill(tmp_path, "arch-review")
        result = detect_existing(tmp_path)
        assert result["skills"] is True

    def test_no_skills_dir(self, tmp_path: Path) -> None:
        result = detect_existing(tmp_path)
        assert result["skills"] is False

    def test_empty_skills_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        result = detect_existing(tmp_path)
        assert result["skills"] is False

    def test_dir_without_skill_md_not_detected(self, tmp_path: Path) -> None:
        """A directory in skills/ without SKILL.md should not count."""
        random_dir = tmp_path / ".claude" / "skills" / "not-a-skill"
        random_dir.mkdir(parents=True)
        (random_dir / "README.md").write_text("not a skill")
        result = detect_existing(tmp_path)
        assert result["skills"] is False

    def test_config_detection(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".forge" / "config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("repo:\n  org: test\n")
        result = detect_existing(tmp_path)
        assert result["config"] is True

    def test_docker_detection(self, tmp_path: Path) -> None:
        dockerfile = tmp_path / ".forge" / "docker" / "claude-dev" / "Dockerfile"
        dockerfile.parent.mkdir(parents=True)
        dockerfile.write_text("FROM ubuntu")
        result = detect_existing(tmp_path)
        assert result["docker"] is True

    def test_nothing_exists(self, tmp_path: Path) -> None:
        result = detect_existing(tmp_path)
        assert result == {"config": False, "skills": False, "docker": False}


class TestScaffoldDocker:
    """Tests for scaffold_docker() writing to .forge/docker/."""

    def test_scaffold_docker_writes_to_forge_dir(self, tmp_path: Path) -> None:
        from forge_workflow.lib.scaffold import scaffold_docker

        scaffold_docker(tmp_path)
        assert (tmp_path / ".forge" / "docker" / "claude-dev" / "Dockerfile").is_file()
        assert (
            tmp_path / ".forge" / "docker" / "claude-dev" / "entrypoint.sh"
        ).is_file()
        assert (
            tmp_path / ".forge" / "docker" / "claude-dev" / "bots" / "bot.env.example"
        ).is_file()

    def test_scaffold_docker_does_not_write_to_old_path(self, tmp_path: Path) -> None:
        from forge_workflow.lib.scaffold import scaffold_docker

        scaffold_docker(tmp_path)
        assert not (tmp_path / "docker").exists()


class TestScaffoldStatusline:
    """Tests for scaffold_statusline() writing to .forge/scripts/."""

    def test_scaffold_statusline_writes_to_forge_dir(self, tmp_path: Path) -> None:
        from forge_workflow.lib.scaffold import scaffold_statusline

        result = scaffold_statusline(tmp_path, force=True)
        assert result == tmp_path / ".forge" / "scripts" / "statusline-command.sh"
        assert result.is_file()

    def test_scaffold_statusline_does_not_write_to_old_path(
        self, tmp_path: Path
    ) -> None:
        from forge_workflow.lib.scaffold import scaffold_statusline

        scaffold_statusline(tmp_path, force=True)
        assert not (tmp_path / "scripts" / "statusline-command.sh").exists()


class TestMigrateOldAssets:
    """Tests for migrate_old_assets() moving files from old to new locations."""

    def test_migrates_docker_files(self, tmp_path: Path) -> None:
        from forge_workflow.lib.scaffold import migrate_old_assets

        old_docker = tmp_path / "docker" / "claude-dev"
        old_docker.mkdir(parents=True)
        (old_docker / "Dockerfile").write_text("FROM ubuntu")
        (old_docker / "entrypoint.sh").write_text("#!/bin/bash")
        bots_dir = old_docker / "bots"
        bots_dir.mkdir()
        (bots_dir / "bot.env.example").write_text("KEY=val")

        result = migrate_old_assets(tmp_path)

        new_docker = tmp_path / ".forge" / "docker" / "claude-dev"
        assert (new_docker / "Dockerfile").read_text() == "FROM ubuntu"
        assert (new_docker / "entrypoint.sh").read_text() == "#!/bin/bash"
        assert (new_docker / "bots" / "bot.env.example").read_text() == "KEY=val"
        assert not (tmp_path / "docker").exists()
        assert "docker" in result

    def test_migrates_statusline_script(self, tmp_path: Path) -> None:
        from forge_workflow.lib.scaffold import migrate_old_assets

        old_sl = tmp_path / "scripts" / "statusline-command.sh"
        old_sl.parent.mkdir(parents=True)
        old_sl.write_text("#!/bin/bash\necho hi")

        result = migrate_old_assets(tmp_path)

        new_sl = tmp_path / ".forge" / "scripts" / "statusline-command.sh"
        assert new_sl.read_text() == "#!/bin/bash\necho hi"
        assert not (tmp_path / "scripts" / "statusline-command.sh").exists()
        assert "statusline" in result

    def test_preserves_user_files_in_scripts(self, tmp_path: Path) -> None:
        from forge_workflow.lib.scaffold import migrate_old_assets

        scripts = tmp_path / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "statusline-command.sh").write_text("#!/bin/bash")
        (scripts / "my-custom-script.sh").write_text("custom")

        migrate_old_assets(tmp_path)

        assert (scripts / "my-custom-script.sh").read_text() == "custom"
        assert not (scripts / "statusline-command.sh").exists()

    def test_no_old_assets_returns_empty(self, tmp_path: Path) -> None:
        from forge_workflow.lib.scaffold import migrate_old_assets

        result = migrate_old_assets(tmp_path)
        assert result == []

    def test_already_migrated_is_noop(self, tmp_path: Path) -> None:
        from forge_workflow.lib.scaffold import migrate_old_assets

        new_docker = tmp_path / ".forge" / "docker" / "claude-dev"
        new_docker.mkdir(parents=True)
        (new_docker / "Dockerfile").write_text("FROM ubuntu")

        result = migrate_old_assets(tmp_path)
        assert "docker" not in result
