---
name: forge-cleanup
description: Execute post-merge cleanup after a PR is merged using jp5 pr cleanup CLI. Checks out main, syncs from origin, deletes local and remote feature branches, optionally posts a final issue comment and sets project Status to Review.
user-invocable: true
---

## Purpose

Standardize post-merge cleanup after a GitHub PR lands. Uses `jp5 pr cleanup` to ensure branch deletion and optionally set project Status to Review.

## Trigger

Invoke this skill when the user signals a PR has been merged (e.g., "PR done", "it merged", "pr is in").

## Standard cleanup (no issue management)

```bash
jp5 pr cleanup --pr <number>
```

This:
1. Checks out `main` and syncs from `origin/main`
2. Deletes local feature branch
3. Deletes remote feature branch

## With issue comment and set project Status to Review

```bash
jp5 pr cleanup --pr <number> \
  --issue <issue-number> \
  --issue-comment-file tmp/issue-delivery/<number>/post-merge-comment.md \
  --set-review
```

## Options reference

| Flag | Purpose |
|------|---------|
| `--pr <int>` | Merged PR number (required) |
| `--issue <int>` | Issue to comment on / set review |
| `--issue-comment-file <path>` | Markdown file with final issue comment |
| `--set-review` | Set project Status to Review for the linked issue |
| `--skip-local-branch-delete` | Keep local branch |
| `--skip-remote-branch-delete` | Keep remote branch |
| `--allow-dirty` | Allow running with uncommitted changes |
| `--dry-run` | Validate without mutating |

## Preflight checks

If the working tree has unrelated dirty files, add `--allow-dirty` to bypass the clean-tree check.

## Worktree usage

When invoked from a git worktree, the script automatically:
- Skips `git checkout main` (main is owned by the parent repo)
- Fetches `origin/main` and rebases the worktree branch onto it, preserving any local changes
- Skips local branch deletion (the worktree branch can't be deleted from within)
- Still deletes the remote branch and handles issue comments / set-review

After post-merge completes in a worktree, clean up with `ExitWorktree` or `git worktree remove <path>` from the parent repo.

## After cleanup

Confirm final `git status` showing clean `main`. Report completion to the user.

## Telemetry comment (final step)

After confirming clean `main`, post session telemetry. Prefer the hook-generated exact file when available; fall back to an estimated template otherwise.

**Step 1 — Check for hook-generated exact telemetry:**

Look for files matching `tmp/session-telemetry/*/telemetry-comment.md`. If one exists and was created today, it contains exact transcript-derived token counts. Copy it to `tmp/issue-delivery/<number>/telemetry-comment.md` and post it.

**Step 2 — Fallback: estimated template (if no hook file found):**

Write the comment to `tmp/issue-delivery/<number>/telemetry-comment.md` using the Write tool, then post it via `gh issue comment`.

```markdown
## Session Telemetry

- **Model:** claude-sonnet-4-6
- **Session date:** <YYYY-MM-DD>
- **Estimated wall time:** ~<N> min
- **PRs opened:** #<n>[, #<n>...]
- **Commits:** <count>
- **Files modified:** <count>
- **Context pressure:** low | moderate | high
- **Skills invoked:** <skill1>, <skill2>, ... (<N> total)
- **Agents spawned:** <agent1> ×<n>[, <agent2> ×<n>...] (<N> total)
- **Token cost:** Exact figures not available in-session — check the [Anthropic Console](https://console.anthropic.com).
```

Post to linked issue or PR:

```bash
gh issue comment <issue-number> --body-file tmp/issue-delivery/<number>/telemetry-comment.md
```

## Approval hygiene (final step)

**Skip this section entirely when `CLAUDE_MODE=autonomous`.** Approval logging is disabled in autonomous mode (`--dangerously-skip-permissions` means `PermissionRequest` events never fire), so the log file is never created and this step is dead weight.

To check the mode, run `printenv CLAUDE_MODE`. If the result is `autonomous`, skip to the Token hygiene section.

When `CLAUDE_MODE` is `supervised` or unset (the default), proceed normally:

1. Check if `/tmp/forge-approval-log.jsonl` exists and is non-empty
2. If it exists, invoke `/approval-hygiene` to analyze session re-approvals and suggest settings improvements
3. If it doesn't exist or is empty, skip this step

## Token hygiene (optional)

After approval hygiene completes (or is skipped), check for token cost data:

1. Check if `tmp/usage-log.jsonl` exists and is non-empty
2. If it exists, ask: "Run /token-hygiene for cost analysis? (y/n)"
3. If the user says yes, invoke `/token-hygiene`
4. If they decline or the file doesn't exist, skip this step
