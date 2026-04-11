"""forge init — scaffold forge config, skills, and Docker infrastructure."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import typer

from forge_workflow.lib.scaffold import (
    detect_existing,
    migrate_old_assets,
    scaffold_config,
    scaffold_docker,
    scaffold_skills,
)

app = typer.Typer(no_args_is_help=False)


def _detect_repo_identity() -> tuple[str, str]:
    """Detect org/repo via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "/" in result.stdout.strip():
            org, name = result.stdout.strip().split("/", 1)
            return org, name
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "", ""


@app.callback(invoke_without_command=True)
def init(
    target: Optional[Path] = typer.Option(
        None, "--target", help="Target repo root (default: cwd)"
    ),
    org: Optional[str] = typer.Option(None, "--org", help="GitHub org"),
    repo_name: Optional[str] = typer.Option(None, "--repo", help="GitHub repo name"),
    rescaffold_skills: bool = typer.Option(
        False, "--rescaffold-skills", help="Keep config, rescaffold skills only"
    ),
    skip_docker: bool = typer.Option(
        False, "--skip-docker", help="Skip Docker file scaffolding"
    ),
) -> None:
    """Initialize forge in a repository — scaffolds config, skills, and Docker."""
    repo_root = target or Path.cwd()

    existing = detect_existing(repo_root)

    # Handle existing config
    if existing["config"] and not rescaffold_skills:
        typer.echo(
            "Error: .forge/config.yaml already exists. Options:\n"
            "  --rescaffold-skills  Keep config, rescaffold skills only\n"
            "  Or delete .forge/config.yaml and re-run.",
            err=True,
        )
        raise typer.Exit(code=1)

    # Migrate assets from old locations (docker/, scripts/) to .forge/
    migrated = migrate_old_assets(repo_root)
    for asset_type in migrated:
        typer.echo(f"  Migrated: {asset_type} → .forge/")

    # Detect or use provided org/repo
    if not rescaffold_skills:
        if org and repo_name:
            final_org, final_repo = org, repo_name
        else:
            final_org, final_repo = _detect_repo_identity()
            final_org = org or final_org
            final_repo = repo_name or final_repo

        if not final_org or not final_repo:
            typer.echo(
                "Error: Could not detect repo identity. Provide --org and --repo.",
                err=True,
            )
            raise typer.Exit(code=1)

        cfg_path = scaffold_config(repo_root, org=final_org, repo_name=final_repo)
        typer.echo(f"  Config: {cfg_path}")

    # Skills
    if rescaffold_skills:
        # Use update-skills logic to avoid overwriting customized files
        from forge_workflow.lib.skill_sync import (
            bootstrap_hashes,
            get_upstream_skills,
            sync_skill,
        )

        # Seed hash file from current local skills if it doesn't exist yet.
        # Without this, repos that pre-date hash tracking classify all
        # skills as MODIFIED and skip them — making rescaffold a no-op.
        bootstrapped = bootstrap_hashes(repo_root)
        if bootstrapped:
            typer.echo(f"  Hashes: bootstrapped {bootstrapped} skill hashes")

        upstream = get_upstream_skills()
        updated = 0
        for skill_name, content in sorted(upstream.items()):
            result = sync_skill(repo_root, skill_name, content, auto=True)
            if result in ("updated", "created"):
                updated += 1
                typer.echo(f"  ~ {skill_name} ({result})")
        typer.echo(f"  Skills: {updated} updated/created (customized skills preserved)")
    else:
        count = scaffold_skills(repo_root)
        typer.echo(f"  Skills: {count} skill templates scaffolded")

    # Docker (skip when only rescaffolding skills, or when just migrated)
    if not skip_docker and not rescaffold_skills and "docker" not in migrated:
        scaffold_docker(repo_root)
        typer.echo("  Docker: Dockerfile, entrypoint.sh, bot.env.example")

    # Statusline script (always update — force during rescaffold to pick up template changes)
    from forge_workflow.lib.scaffold import scaffold_statusline

    sl_path = scaffold_statusline(repo_root, force=rescaffold_skills)
    if sl_path:
        typer.echo(f"  Script: {sl_path}")

    # Configure statusLine directly in project settings.local.json.
    # Previous approach used `claude config set` via subprocess, which hangs
    # when there's no TTY (it prompts interactively for scope selection).
    # The correct format is: {"statusLine": {"type": "command", "command": "bash /path/to/script.sh"}}
    sl_script = repo_root / ".forge" / "scripts" / "statusline-command.sh"
    if sl_script.is_file():
        import json

        abs_script = str(sl_script.resolve())
        cmd_value = f"bash {abs_script}"
        settings_path = repo_root / ".claude" / "settings.local.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if settings_path.is_file():
            try:
                existing = json.loads(settings_path.read_text())
            except (json.JSONDecodeError, OSError):
                existing = {}
        existing.pop("statuslineCommand", None)
        existing["statusLine"] = {"type": "command", "command": cmd_value}
        settings_path.write_text(json.dumps(existing, indent=2) + "\n")
        typer.echo(f"  Config: statusLine → {cmd_value}")

    # Docs (managed sections in CLAUDE.md / AGENTS.md)
    from forge_workflow.lib.scaffold import scaffold_docs

    try:
        from forge_workflow.lib.bot_config import list_bots

        bot_list = list_bots(repo_root)
    except Exception:
        bot_list = []
    doc_result = scaffold_docs(repo_root, bots=bot_list)
    if doc_result["claude_md"]:
        typer.echo("  Docs:   CLAUDE.md managed sections updated")
    if doc_result["agents_md"]:
        typer.echo("  Docs:   AGENTS.md managed sections updated")

    typer.echo(f"\nForge initialized in {repo_root}")
    typer.echo("Next: edit .forge/config.yaml, then run 'forge bot add <name>'")
