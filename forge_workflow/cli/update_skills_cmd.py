"""forge update-skills — sync local skills with upstream templates."""
from __future__ import annotations

from pathlib import Path

import typer

from forge_workflow import config as forge_config
from forge_workflow.lib.skill_sync import (
    SkillStatus,
    check_skill_status,
    diff_skill,
    get_upstream_skills,
    sync_skill,
)

app = typer.Typer(no_args_is_help=False)


def _find_root() -> Path:
    root = forge_config._find_repo_root()
    if root is None:
        typer.echo("Error: No .forge/config.yaml found.", err=True)
        raise typer.Exit(code=1)
    return root


@app.callback(invoke_without_command=True)
def update_skills(
    force: bool = typer.Option(
        False, "--force", help="Overwrite all skills, even customized ones"
    ),
    show_diff: bool = typer.Option(
        False, "--diff", help="Show diffs for modified skills"
    ),
) -> None:
    """Diff local skills against upstream templates and sync."""
    root = _find_root()
    upstream = get_upstream_skills()

    if not upstream:
        typer.echo("No upstream skill templates found in package.")
        raise typer.Exit(code=1)

    updated = 0
    skipped = 0
    created = 0
    up_to_date = 0

    for skill_name, content in sorted(upstream.items()):
        status = check_skill_status(root, skill_name, content)

        if status == SkillStatus.UP_TO_DATE:
            up_to_date += 1
            continue

        if status == SkillStatus.MISSING:
            sync_skill(root, skill_name, content, auto=True)
            typer.echo(f"  + {skill_name} (created)")
            created += 1
            continue

        if status == SkillStatus.UNMODIFIED or force:
            sync_skill(root, skill_name, content, auto=False)
            typer.echo(f"  ~ {skill_name} (updated)")
            updated += 1
            continue

        # Modified — show diff and skip
        typer.echo(f"  ! {skill_name} (customized — skipped)")
        if show_diff:
            diff_output = diff_skill(root, skill_name, content)
            if diff_output:
                typer.echo(diff_output)
        skipped += 1

    typer.echo(
        f"\nResults: {updated} updated, {created} created, "
        f"{skipped} skipped (customized), {up_to_date} up-to-date"
    )
