#!/usr/bin/env python3
"""PostToolUse hook: auto-post pre-implementation assessment to GitHub issue.

Fires on Write. When the written file matches
tmp/issue-delivery/<number>/assessment.md, posts it to the linked
GitHub issue.

Exits 0 always (best-effort) -- posting failure must not block the
agent's approval flow.
"""
import sys
import json
import subprocess
import os
import re
from pathlib import Path


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    path = data.get('tool_input', {}).get('file_path', '')
    if not path:
        return

    normalized = path.replace(os.sep, '/').replace('\\', '/')
    match = re.search(r'tmp/issue-delivery/(\d+)/assessment\.md$', normalized)
    if not match:
        return

    issue_num = match.group(1)

    assessment_path = Path(path)
    if not assessment_path.exists() or assessment_path.stat().st_size == 0:
        return

    # Lazy import to avoid slowing down hooks that don't need config
    from forge_workflow.config import repo_slug
    result = subprocess.run(
        ['gh', 'issue', 'comment', issue_num,
         '--repo', repo_slug(), '--body-file', str(assessment_path)],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        print(f'[HOOK] Assessment posted to issue #{issue_num}.')
    else:
        stderr_snippet = (result.stderr or '').strip()[:200]
        print(f'[HOOK] Failed to post assessment to issue #{issue_num} '
              f'(rc={result.returncode}). {stderr_snippet}')
        print('[HOOK] Continuing -- posting failure does not block approval.')


try:
    main()
except Exception:
    pass
