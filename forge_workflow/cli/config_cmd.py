"""forge config subcommands — get, set, discover-project."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

import typer
import yaml

from forge_workflow import config as forge_config

app = typer.Typer(no_args_is_help=True)


@app.command("get")
def config_get(
    key: str = typer.Argument(help="Dot-notation config key (e.g. repo.org)"),
) -> None:
    """Print the resolved value for a dot-notation config key."""
    try:
        value = forge_config.get(key)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    if value is None:
        typer.echo(f"Key '{key}' not found in config.", err=True)
        raise typer.Exit(code=1)

    if isinstance(value, (dict, list)):
        typer.echo(yaml.dump(value, default_flow_style=False).rstrip())
    else:
        typer.echo(value)


@app.command("set")
def config_set(
    key: str = typer.Argument(help="Dot-notation config key (e.g. repo.org)"),
    value: str = typer.Argument(help="Value to set"),
    config_file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="Path to config file (default: .forge/config.yaml)"
    ),
) -> None:
    """Update a key in .forge/config.yaml with validation."""
    try:
        forge_config.set_value(key, value, config_file=config_file)
        typer.echo(f"Set {key} = {value}")
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command("discover-project")
def discover_project(
    org: Optional[str] = typer.Option(
        None, "--org", "-o", help="GitHub org (default: from config)"
    ),
) -> None:
    """Discover GitHub Projects V2 and populate project_board IDs in config."""
    try:
        config_org = org or forge_config.get("repo.org")
    except FileNotFoundError:
        config_org = org

    if not config_org:
        typer.echo("Error: No org specified and repo.org not found in config.", err=True)
        raise typer.Exit(code=1)

    # Step 1: List org projects
    typer.echo(f"Discovering projects for org '{config_org}'...")
    query = (
        '{ organization(login: "' + config_org + '") '
        "{ projectsV2(first: 20) { nodes { id title } } } }"
    )
    try:
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={query}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        typer.echo(f"Error running gh CLI: {e}", err=True)
        raise typer.Exit(code=1)

    if result.returncode != 0:
        typer.echo(f"GraphQL query failed: {result.stderr}", err=True)
        raise typer.Exit(code=1)

    data = json.loads(result.stdout)
    projects = (
        data.get("data", {})
        .get("organization", {})
        .get("projectsV2", {})
        .get("nodes", [])
    )

    if not projects:
        typer.echo("No projects found.", err=True)
        raise typer.Exit(code=1)

    # Display projects for selection
    typer.echo("\nAvailable projects:")
    for i, proj in enumerate(projects):
        typer.echo(f"  [{i}] {proj['title']}  ({proj['id']})")

    if len(projects) == 1:
        selected = projects[0]
        typer.echo(f"\nAuto-selected: {selected['title']}")
    else:
        choice = typer.prompt("\nSelect project number", default="0")
        try:
            selected = projects[int(choice)]
        except (IndexError, ValueError):
            typer.echo("Invalid selection.", err=True)
            raise typer.Exit(code=1)

    project_id = selected["id"]

    # Step 2: Fetch project fields
    typer.echo(f"\nFetching fields for '{selected['title']}'...")
    fields_query = (
        '{ node(id: "' + project_id + '") { ... on ProjectV2 { '
        "fields(first: 30) { nodes { "
        "... on ProjectV2SingleSelectField { id name options { id name } } "
        "} } } } }"
    )
    try:
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={fields_query}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        typer.echo(f"Error running gh CLI: {e}", err=True)
        raise typer.Exit(code=1)

    if result.returncode != 0:
        typer.echo(f"Fields query failed: {result.stderr}", err=True)
        raise typer.Exit(code=1)

    fields_data = json.loads(result.stdout)
    field_nodes = (
        fields_data.get("data", {})
        .get("node", {})
        .get("fields", {})
        .get("nodes", [])
    )

    # Build project_board config
    project_board: dict = {
        "enabled": True,
        "project_id": project_id,
        "fields": {},
        "options": {},
    }

    for field in field_nodes:
        if not field or "id" not in field:
            continue
        field_name = field.get("name", "").lower().replace(" ", "_")
        field_id = field["id"]
        project_board["fields"][field_name] = field_id

        options = field.get("options", [])
        if options:
            project_board["options"][field_name] = {}
            for opt in options:
                opt_key = opt["name"].lower().replace(" ", "_").replace("-", "_")
                project_board["options"][field_name][opt_key] = opt["id"]

    # Step 3: Write to config
    try:
        cfg_path = forge_config.config_path()
    except FileNotFoundError:
        typer.echo("Error: No .forge/config.yaml found.", err=True)
        raise typer.Exit(code=1)

    with open(cfg_path) as f:
        file_config = yaml.safe_load(f) or {}

    file_config["project_board"] = project_board

    with open(cfg_path, "w") as f:
        yaml.dump(file_config, f, default_flow_style=False, sort_keys=False)

    forge_config._invalidate_cache()

    typer.echo(f"\nProject board config written to {cfg_path}")
    typer.echo(f"  project_id: {project_id}")
    typer.echo(f"  fields discovered: {len(project_board['fields'])}")
