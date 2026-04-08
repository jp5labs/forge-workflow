"""Skill sync logic for forge update-skills."""
from __future__ import annotations

import difflib
import hashlib
import json
from enum import Enum
from importlib.resources import files as pkg_files
from pathlib import Path


class SkillStatus(Enum):
    UNMODIFIED = "unmodified"  # Local matches last-known upstream hash
    MODIFIED = "modified"  # Local has been customized
    MISSING = "missing"  # Local file doesn't exist
    UP_TO_DATE = "up_to_date"  # Local matches current upstream


def _load_hashes(repo_root: Path) -> dict[str, str]:
    """Load skill hashes from .forge/skill-hashes.json."""
    hash_path = repo_root / ".forge" / "skill-hashes.json"
    if not hash_path.is_file():
        return {}
    with open(hash_path) as f:
        return json.load(f)


def _save_hashes(repo_root: Path, hashes: dict[str, str]) -> None:
    """Save skill hashes."""
    hash_path = repo_root / ".forge" / "skill-hashes.json"
    hash_path.parent.mkdir(parents=True, exist_ok=True)
    with open(hash_path, "w") as f:
        json.dump(hashes, f, indent=2)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def check_skill_status(
    repo_root: Path, skill_name: str, upstream_content: str
) -> SkillStatus:
    """Determine the sync status of a local skill vs upstream."""
    local_path = repo_root / ".claude" / "skills" / skill_name / "SKILL.md"

    if not local_path.is_file():
        return SkillStatus.MISSING

    local_content = local_path.read_text()
    local_hash = _content_hash(local_content)
    upstream_hash = _content_hash(upstream_content)

    # If local matches upstream, it's up to date
    if local_hash == upstream_hash:
        return SkillStatus.UP_TO_DATE

    # Check if local matches the last-known upstream (unmodified by user)
    known_hashes = _load_hashes(repo_root)
    known_hash = known_hashes.get(skill_name)

    if known_hash and local_hash == known_hash:
        return SkillStatus.UNMODIFIED  # User hasn't touched it, upstream changed

    return SkillStatus.MODIFIED  # User has customized it


def sync_skill(
    repo_root: Path,
    skill_name: str,
    upstream_content: str,
    *,
    auto: bool = False,
) -> str:
    """Sync a single skill. Returns action taken: updated/skipped/created/up_to_date."""
    status = check_skill_status(repo_root, skill_name, upstream_content)

    if status == SkillStatus.UP_TO_DATE:
        return "up_to_date"

    if status == SkillStatus.MODIFIED and auto:
        return "skipped"

    # Write the skill
    dest = repo_root / ".claude" / "skills" / skill_name / "SKILL.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(upstream_content)

    # Update hash
    hashes = _load_hashes(repo_root)
    hashes[skill_name] = _content_hash(upstream_content)
    _save_hashes(repo_root, hashes)

    if status == SkillStatus.MISSING:
        return "created"
    return "updated"


def diff_skill(repo_root: Path, skill_name: str, upstream_content: str) -> str:
    """Generate a unified diff between local and upstream skill."""
    local_path = repo_root / ".claude" / "skills" / skill_name / "SKILL.md"
    if not local_path.is_file():
        return "(local file missing)"
    local_content = local_path.read_text()
    diff = difflib.unified_diff(
        local_content.splitlines(keepends=True),
        upstream_content.splitlines(keepends=True),
        fromfile=f"local/{skill_name}/SKILL.md",
        tofile=f"upstream/{skill_name}/SKILL.md",
    )
    return "".join(diff)


def get_upstream_skills() -> dict[str, str]:
    """Load all upstream skill templates from the package."""
    templates_pkg = pkg_files("forge_workflow.templates.skills")
    skills: dict[str, str] = {}
    for skill_dir in sorted(templates_pkg.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name == "__pycache__":
            continue
        skill_file = skill_dir / "SKILL.md"
        if skill_file.is_file():
            skills[skill_dir.name] = skill_file.read_text()
    return skills
