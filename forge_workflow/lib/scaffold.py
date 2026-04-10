"""Scaffold logic for forge init — create config, skills, Docker files."""
from __future__ import annotations

import hashlib
import json
from importlib.resources import files as pkg_files
from pathlib import Path

import yaml


def detect_existing(target: Path) -> dict[str, bool]:
    """Detect what forge artifacts already exist in the target repo."""
    config_exists = (target / ".forge" / "config.yaml").is_file()
    skills_dir = target / ".claude" / "skills"
    skills_exist = (
        any(skills_dir.glob("forge-*/SKILL.md")) if skills_dir.is_dir() else False
    )
    docker_exists = (target / "docker" / "claude-dev" / "Dockerfile").is_file()
    return {
        "config": config_exists,
        "skills": skills_exist,
        "docker": docker_exists,
    }


def scaffold_config(target: Path, *, org: str, repo_name: str) -> Path:
    """Create .forge/config.yaml from template with repo identity."""
    template_content = _read_template("config.yaml")
    config = yaml.safe_load(template_content) or {}
    config["repo"]["org"] = org
    config["repo"]["name"] = repo_name

    cfg_path = target / ".forge" / "config.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    return cfg_path


def scaffold_skills(target: Path) -> int:
    """Copy all bundled skill templates into target/.claude/skills/.

    Returns the number of skills scaffolded. Also writes hash file for
    future update-skills diffing.
    """
    templates_pkg = pkg_files("forge_workflow.templates.skills")
    hashes: dict[str, str] = {}
    count = 0

    for skill_dir in sorted(templates_pkg.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_name = skill_dir.name
        if skill_name == "__pycache__":
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue

        content = skill_file.read_text()
        dest_dir = target / ".claude" / "skills" / skill_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "SKILL.md").write_text(content)

        hashes[skill_name] = hashlib.sha256(content.encode()).hexdigest()
        count += 1

    # Write hash file for update-skills
    hash_path = target / ".forge" / "skill-hashes.json"
    hash_path.parent.mkdir(parents=True, exist_ok=True)
    with open(hash_path, "w") as f:
        json.dump(hashes, f, indent=2)

    return count


def scaffold_docker(target: Path) -> None:
    """Copy Docker template files into target/docker/claude-dev/."""
    docker_dir = target / "docker" / "claude-dev"
    docker_dir.mkdir(parents=True, exist_ok=True)
    bots_dir = docker_dir / "bots"
    bots_dir.mkdir(parents=True, exist_ok=True)

    for filename in ["Dockerfile", "entrypoint.sh"]:
        content = _read_template(f"docker/{filename}")
        (docker_dir / filename).write_text(content)

    env_content = _read_template("docker/bot.env.example")
    (bots_dir / "bot.env.example").write_text(env_content)


def scaffold_docs(
    target: Path,
    bots: list | None = None,
) -> dict[str, bool]:
    """Upsert forge-managed sections in CLAUDE.md and AGENTS.md.

    Only updates files that already exist — does not create them.
    Returns dict indicating which files were modified.
    """
    from forge_workflow.lib.doc_manager import upsert_doc_sections
    from forge_workflow.lib.doc_sections import (
        render_agents_autonomous_detail,
        render_agents_bot_fleet,
        render_agents_bot_identity,
        render_agents_gate_policy,
        render_agents_mode_table,
        render_claude_bot_identity,
        render_claude_remote_sessions,
        render_workflow_choreography,
    )

    bot_list = bots or []

    claude_updated = upsert_doc_sections(
        target / "CLAUDE.md",
        {
            "remote-sessions": render_claude_remote_sessions(bot_list),
            "bot-identity": render_claude_bot_identity(bot_list),
            "workflow": render_workflow_choreography(),
        },
    )

    agents_updated = upsert_doc_sections(
        target / "AGENTS.md",
        {
            "bot-fleet": render_agents_bot_fleet(bot_list),
            "bot-identity": render_agents_bot_identity(bot_list),
            "mode": render_agents_mode_table(bot_list),
            "autonomous-detail": render_agents_autonomous_detail(bot_list),
            "gate-policy": render_agents_gate_policy(bot_list),
            "workflow": render_workflow_choreography(),
        },
    )

    return {"claude_md": claude_updated, "agents_md": agents_updated}


def scaffold_statusline(target: Path, *, force: bool = False) -> Path | None:
    """Copy the statusline script template to scripts/statusline-command.sh.

    Returns the path if created/updated, None if unchanged.
    When force=True, overwrites existing file (used during rescaffold).
    """
    dest = target / "scripts" / "statusline-command.sh"
    content = _read_template("scripts/statusline-command.sh")
    if dest.is_file():
        if not force:
            return None
        if dest.read_text() == content:
            return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    dest.chmod(0o755)
    return dest


def _read_template(relative_path: str) -> str:
    """Read a template file from the forge_workflow.templates package."""
    parts = relative_path.split("/")
    resource = pkg_files("forge_workflow.templates")
    for part in parts:
        resource = resource.joinpath(part)
    return resource.read_text()
