#!/usr/bin/env python3
"""PreToolUse hook: post plan to GitHub issue before ExitPlanMode approval.

Fires when ExitPlanMode is called. Reads tmp/.plan-issue for the current issue
number, finds the most recently modified plan file in ~/.claude/plans/, and posts
it to the GitHub issue so it's visible before the user approves in Claude Code.

Exits 0 always (best-effort) -- GitHub post failure must not block plan approval.
"""
import sys
import json
import subprocess
from pathlib import Path


def find_latest_plan_file():
    plans_dir = Path.home() / '.claude' / 'plans'
    if not plans_dir.exists():
        return None
    md_files = list(plans_dir.glob('*.md'))
    if not md_files:
        return None
    return max(md_files, key=lambda p: p.stat().st_mtime)


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    issue_file = Path('tmp') / '.plan-issue'
    if not issue_file.exists():
        return

    issue_num = issue_file.read_text(encoding='utf-8').strip()
    if not issue_num.isdigit():
        return

    plan_file = find_latest_plan_file()
    if plan_file is None:
        return

    plan_content = plan_file.read_text(encoding='utf-8')

    out_dir = Path('tmp') / 'issue-delivery' / issue_num
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / 'implementation-plan.md'

    header = '## Implementation Plan\n\n_Plan approved. Proceeding to implementation._\n\n---\n\n'
    out_file.write_text(header + plan_content, encoding='utf-8')

    # Lazy import to avoid slowing down hooks that don't need config
    from forge_workflow.config import repo_slug
    subprocess.run(
        ['gh', 'issue', 'comment', issue_num,
         '--repo', repo_slug(), '--body-file', str(out_file)],
        capture_output=True,
    )


try:
    main()
except Exception:
    pass
