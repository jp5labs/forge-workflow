"""forge pin — update forge-workflow version pin in pyproject.toml."""
from __future__ import annotations

import re
from pathlib import Path

import typer

from forge_workflow import __version__
from forge_workflow import config as forge_config
from forge_workflow.lib.version_check import REPO_URL

# Captures the forge-workflow @ git+<url> prefix and optionally matches an
# existing tag suffix so replacement can append the updated tag.
_PIN_PATTERN = re.compile(
    r'(forge-workflow\s*@\s*git\+' + re.escape(REPO_URL) + r')(?:@[^\s"\'#]+)?'
)


def _find_pyproject(root: Path) -> Path | None:
    """Locate pyproject.toml starting from root."""
    candidate = root / "pyproject.toml"
    return candidate if candidate.is_file() else None


def pin(
    path: Path | None = typer.Option(
        None,
        "--path",
        "-p",
        help="Path to pyproject.toml (default: repo root).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would change without modifying the file.",
    ),
) -> None:
    """Update forge-workflow version pin in pyproject.toml to match the installed version."""
    tag = f"v{__version__}"

    if path:
        pyproject = Path(path)
    else:
        root = forge_config._find_repo_root()
        if root is None:
            typer.echo("Error: No .forge/config.yaml found. Use --path to specify pyproject.toml.", err=True)
            raise typer.Exit(code=1)
        pyproject = _find_pyproject(root)
        if pyproject is None:
            typer.echo(f"Error: No pyproject.toml found in {root}", err=True)
            raise typer.Exit(code=1)

    if not pyproject.is_file():
        typer.echo(f"Error: {pyproject} does not exist.", err=True)
        raise typer.Exit(code=1)

    content = pyproject.read_text()

    if not _PIN_PATTERN.search(content):
        typer.echo(f"No forge-workflow git pin found in {pyproject}.", err=True)
        raise typer.Exit(code=1)

    new_content = _PIN_PATTERN.sub(rf'\1@{tag}', content)

    if new_content == content:
        typer.echo(f"Already pinned to {tag}.")
        return

    # Show the change
    for old_line, new_line in zip(content.splitlines(), new_content.splitlines()):
        if old_line != new_line:
            typer.echo(f"  - {old_line.strip()}")
            typer.echo(f"  + {new_line.strip()}")

    if dry_run:
        typer.echo(f"\nDry run: would update pin to {tag} in {pyproject}")
        return

    pyproject.write_text(new_content)
    typer.echo(f"\nUpdated pin to {tag} in {pyproject}")
