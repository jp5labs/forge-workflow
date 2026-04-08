"""forge self-update — update forge-workflow to the latest release."""
from __future__ import annotations

import subprocess
import sys

import typer

from forge_workflow import __version__
from forge_workflow.lib.version_check import REPO_URL


def self_update(
    version: str = typer.Option(
        None,
        "--version",
        "-v",
        help="Pin to a specific version tag (e.g. v0.2.0). Default: latest.",
    ),
) -> None:
    """Update forge-workflow to the latest release (or a specific version)."""
    typer.echo(f"Current version: {__version__}")

    if version:
        install_ref = f"forge-workflow @ git+{REPO_URL}@{version}"
        typer.echo(f"Updating to {version}...")
    else:
        install_ref = f"forge-workflow @ git+{REPO_URL}"
        typer.echo("Updating to latest...")

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", install_ref],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        typer.echo(f"Update failed:\n{result.stderr}", err=True)
        raise typer.Exit(1)

    # Re-import to get new version
    try:
        import importlib

        import forge_workflow as fw
        importlib.reload(fw)
        new_version = fw.__version__
    except Exception:
        new_version = "(restart to see new version)"

    typer.echo(f"Updated: {__version__} → {new_version}")
