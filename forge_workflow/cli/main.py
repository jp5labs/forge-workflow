"""Forge CLI entry point.

Portable delivery workflow commands. The forge CLI provides bot fleet
management, config, scaffolding, and self-update. Platform-specific
commands (deliver, pr, ops) live in the consumer's CLI and import
forge_workflow as a library.
"""

import typer

from forge_workflow.cli import (
    bot_cmd,
    config_cmd,
    doctor,
    init_cmd,
    self_update,
    update_skills_cmd,
)


def _check_version() -> None:
    """Passive version check on every CLI invocation (cached, non-blocking)."""
    try:
        from forge_workflow.lib.version_check import check_for_update
        msg = check_for_update()
        if msg:
            typer.echo(msg, err=True)
    except Exception:
        pass  # Never block the CLI on update check failures


app = typer.Typer(
    name="forge",
    help="Forge -- portable delivery workflow CLI.",
    no_args_is_help=True,
    callback=_check_version,
)


# Forge-native commands
app.add_typer(bot_cmd.app, name="bot", help="Bot fleet management.")
app.add_typer(config_cmd.app, name="config", help="Configuration management.")
app.add_typer(init_cmd.app, name="init", help="Initialize forge in a repository.")
app.add_typer(update_skills_cmd.app, name="update-skills", help="Sync skills with upstream templates.")
app.add_typer(self_update.app, name="self-update", help="Update forge-workflow.")
app.command()(doctor.doctor)


if __name__ == "__main__":
    app()
