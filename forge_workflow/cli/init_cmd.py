"""forge init — scaffold forge config, skills, and Docker infrastructure."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import typer

from forge_workflow.lib.scaffold import (
    detect_existing,
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
        from forge_workflow.lib.skill_sync import get_upstream_skills, sync_skill

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

    # Docker (skip when only rescaffolding skills)
    if not skip_docker and not rescaffold_skills:
        scaffold_docker(repo_root)
        typer.echo("  Docker: Dockerfile, entrypoint.sh, bot.env.example")

    typer.echo(f"\nForge initialized in {repo_root}")
    typer.echo("Next: edit .forge/config.yaml, then run 'forge bot add <name>'")
