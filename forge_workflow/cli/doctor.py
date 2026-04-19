"""forge doctor — validate environment and configuration health."""

from __future__ import annotations

import subprocess

import typer

from forge_workflow import config as forge_config


def _check(label: str, passed: bool, detail: str = "") -> bool:
    """Print a check result line and return the pass/fail status."""
    mark = "\u2713" if passed else "\u2717"
    msg = f"  {mark} {label}"
    if detail:
        msg += f" ({detail})"
    typer.echo(msg)
    return passed


def doctor() -> None:
    """Validate Forge environment and configuration health."""
    typer.echo("Forge Doctor\n")
    all_passed = True

    # 1. Config file exists
    try:
        cfg_path = forge_config.config_path()
        exists = cfg_path.is_file()
    except FileNotFoundError:
        cfg_path = None
        exists = False

    if not _check("Config file exists", exists, str(cfg_path) if cfg_path else "not found"):
        all_passed = False

    # 2. Required fields populated
    if exists:
        try:
            config = forge_config.load()
            errors = forge_config.validate(config)
            fields_ok = len(errors) == 0
            detail = "all present" if fields_ok else "; ".join(errors)
        except Exception as e:
            fields_ok = False
            detail = str(e)
    else:
        fields_ok = False
        detail = "no config file"

    if not _check("Required fields populated", fields_ok, detail):
        all_passed = False

    # 3. GitHub auth
    gh_ok = False
    gh_detail = ""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        gh_ok = result.returncode == 0
        if gh_ok:
            # Extract token scopes info from stderr (gh outputs to stderr)
            output = result.stderr + result.stdout
            if "Token scopes" in output:
                scope_line = [
                    line for line in output.splitlines() if "Token scopes" in line
                ]
                gh_detail = scope_line[0].strip() if scope_line else "authenticated"
            else:
                gh_detail = "authenticated"
        else:
            gh_detail = "not authenticated"
    except FileNotFoundError:
        gh_detail = "gh CLI not found"
    except subprocess.TimeoutExpired:
        gh_detail = "timed out"

    if not _check("GitHub auth", gh_ok, gh_detail):
        all_passed = False

    # 4. Docker available (skip if no bots configured)
    bots = forge_config.get("bots") if exists else None
    if bots:
        docker_ok = False
        docker_detail = ""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            docker_ok = result.returncode == 0
            docker_detail = "available" if docker_ok else "not running"
        except FileNotFoundError:
            docker_detail = "docker not found"
        except subprocess.TimeoutExpired:
            docker_detail = "timed out"

        if not _check("Docker available", docker_ok, docker_detail):
            all_passed = False

        # 5. Bot identity files
        repo_root = cfg_path.parent.parent  # .forge/config.yaml -> repo root
        for bot in bots:
            bot_name = bot.get("name", "unknown")
            bots_base = repo_root / "bots"
            if not bots_base.is_dir():
                bots_base = repo_root / ".forge" / "docker" / "claude-dev" / "bots"
            identity_path = bots_base / f"{bot_name}-identity.md"
            bot_ok = identity_path.is_file()
            if not _check(
                f"Bot identity: {bot_name}",
                bot_ok,
                str(identity_path) if bot_ok else "missing",
            ):
                all_passed = False
    else:
        _check("Docker available", True, "skipped (no bots configured)")

    # 6. Managed doc sections
    if exists and cfg_path:
        repo_root = cfg_path.parent.parent
        doc_issues = _check_managed_docs(repo_root)
        if doc_issues:
            for issue in doc_issues:
                if not _check("Managed doc section", False, issue):
                    all_passed = False
        else:
            _check("Managed doc sections", True, "present")

    # 7. pyproject.toml pin drift
    if exists and cfg_path:
        repo_root = cfg_path.parent.parent
        pin_result = _check_pin_drift(repo_root)
        if pin_result is not None:
            passed, detail = pin_result
            if not _check("pyproject.toml pin", passed, detail):
                all_passed = False

    # 8. Version check (always force-check, not cached)
    try:
        from forge_workflow import __version__
        from forge_workflow.lib.version_check import check_for_update
        update_msg = check_for_update(force=True)
        if update_msg:
            _check("forge version", False, update_msg)
        else:
            _check("forge version", True, f"v{__version__} (latest)")
    except Exception:
        _check("forge version", True, "unable to check")

    # Summary
    typer.echo("")
    if all_passed:
        typer.echo("All checks passed.")
    else:
        typer.echo("Some checks failed. Review the output above.")
        raise typer.Exit(code=1)


def _check_managed_docs(root: object = None) -> list[str]:
    """Check for presence of forge-managed sections in doc files.

    Returns list of warning strings for missing sections.
    """
    from pathlib import Path

    from forge_workflow.lib.doc_manager import find_section

    repo_root = Path(str(root)) if root else Path.cwd()
    issues: list[str] = []

    claude_md = repo_root / "CLAUDE.md"
    if claude_md.is_file():
        content = claude_md.read_text()
        for section in ["remote-sessions", "bot-identity", "workflow"]:
            if find_section(content, section) is None:
                issues.append(
                    f"CLAUDE.md missing forge-managed section: {section}. "
                    f"Run 'forge init --rescaffold-skills' to add it."
                )

    agents_md = repo_root / "AGENTS.md"
    if agents_md.is_file():
        content = agents_md.read_text()
        for section in ["bot-fleet", "bot-identity", "mode", "autonomous-detail", "gate-policy", "workflow"]:
            if find_section(content, section) is None:
                issues.append(
                    f"AGENTS.md missing forge-managed section: {section}. "
                    f"Run 'forge init --rescaffold-skills' to add it."
                )

    return issues


def _check_pin_drift(root: object = None) -> tuple[bool, str] | None:
    """Compare installed forge-workflow version against pyproject.toml pin.

    Returns (passed, detail) or None if no pin is found.
    """
    import re
    from pathlib import Path

    from forge_workflow import __version__
    from forge_workflow.lib.version_check import REPO_URL

    repo_root = Path(str(root)) if root else Path.cwd()
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return None

    content = pyproject.read_text()
    pattern = re.compile(
        r'forge-workflow\s*@\s*git\+' + re.escape(REPO_URL) + r'@v?([\w.]+)'
    )
    match = pattern.search(content)
    if not match:
        return None

    pinned = match.group(1)
    if pinned == __version__:
        return True, f"v{pinned} (matches installed)"

    return False, (
        f"pinned v{pinned}, installed v{__version__} "
        f"— run 'forge pin' to update"
    )
