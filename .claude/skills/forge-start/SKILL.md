---
name: forge-start
description: Prepare the local environment to begin implementation on a GitHub issue. Syncs main, creates the feature branch, and scaffolds delivery templates. Run after /forge-plan is approved and before writing any implementation code.
---

## Purpose

Bridge the gap between an approved plan and the first line of implementation code. Ensures the branch is always cut from a fresh `main` and delivery templates are ready before any work begins. Prevents merge conflicts caused by branching off stale main.

## Trigger

Run this skill when:
- `/forge-plan` has been approved and it's time to start implementing
- User says "start work", "let's implement", or "begin issue X"
- Setting up a fresh branch for any approved story

## Arguments

```
/forge-start <issue-number> [branch-slug]
```

- `<issue-number>` — required. GitHub issue number.
- `[branch-slug]` — optional. If omitted, derive from issue title: lowercase, spaces→hyphens, strip special chars, prepend `issue-<number>-`.

Examples:
```
/forge-start 153
/forge-start 153 issue-153-retrieval-topology
/forge-start 200
```

## Procedure

### Step 1 — Read issue title (if branch slug not provided)

Fetch the issue title with a simple jq query:

```bash
gh issue view <number> --json title --jq .title
```

Then derive the branch slug from the title: lowercase, replace non-alphanumeric runs with hyphens, strip leading/trailing hyphens, prepend `issue-<number>-`. Truncate to 60 chars max if needed.

**Do not** use complex jq expressions with pipes (`|`) or `gsub` — they contain characters that fail shell allow-list matching and trigger approval prompts. Do the slug transformation in-context instead.

### Step 1b — Auto-assign issue

Claim the issue by assigning the current bot:

```bash
gh issue edit <number> --add-assignee @me
```

This is idempotent — re-running does not error if already assigned. The `@me` token resolves from the bot's `gh` auth context, so no hardcoded usernames are needed.

### Step 2 — Sync main

```bash
git fetch origin main
git checkout main
git pull --ff-only origin main
```

If `--ff-only` fails (local main has diverged), report the blocker and stop. Do not force-reset main — surface to the user.

Confirm: print the current `main` HEAD commit hash so it's visible in context.

### Step 3 — Create feature branch

```bash
git checkout -b issue-<number>-<branch-slug>
```

Example: `git checkout -b issue-153-retrieval-topology`

### Step 4 — Scaffold delivery templates

```bash
jp5 deliver init --issue <number>
```

This creates `tmp/issue-delivery/<number>/pr-body.md` and `issue-comment.md`. Edit these before running `/forge-deliver`.

### Step 5 — Write session-issue anchor

Write the issue number to `tmp/.session-issue`:

1. Read `tmp/.session-issue` first (may not exist — that's fine, the Read error is expected on first use)
2. Write the issue number to `tmp/.session-issue` using the `Write` tool

```
<issue-number>
```

The Read-before-Write is required because the file may persist from a prior session. Skipping Read causes Write to fail, and falling back to `echo N > file` triggers shell approval prompts.

This single-line file lets the `SessionEnd` telemetry hook know which issue to post auto-captured telemetry to. Matches the `tmp/.plan-issue` format.

### Step 6 — Confirm and hand off

Print a confirmation summary:

```
Ready to implement:
  Branch:    issue-<number>-<branch-slug>
  Main HEAD: <commit-hash>
  Templates: tmp/issue-delivery/<number>/
```

Announce: "Environment ready. Implement on `issue-<number>-<branch-slug>`, then run `/forge-deliver` when done."

## Subagent tool discipline

When spawning system agents (Explore, Plan, general-purpose) during setup, include the subagent prompt preamble from CLAUDE.md's "Subagent prompt preamble" section in the `prompt` parameter to ensure tool-discipline rules are followed.
