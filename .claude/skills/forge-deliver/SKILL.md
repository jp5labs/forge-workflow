---
name: forge-deliver
description: Execute the issue delivery workflow (commit → push → PR → issue comment) using jp5 deliver CLI. Supports four modes (full, standard, quick, ship) for different levels of ceremony. Invoke after implementation is approved and ready to ship, or to orchestrate the full lifecycle. Invokes /forge-assess, /forge-plan, /forge-start, and /forge-cleanup as sub-skills.
user-invocable: true
---

## Purpose

Orchestrate the delivery workflow for a GitHub issue. Supports four modes that control how much ceremony surrounds the implementation.

## Modes

| Mode | Steps | Use case |
|------|-------|----------|
| **full** | assess → plan → start-work → implement → log → deliver → post-merge | Architecture-touching, multi-file, high-risk |
| **standard** | plan → start-work → implement → log → deliver → post-merge | Normal feature work, moderate complexity |
| **quick** | start-work → implement → log → deliver | Config, docs, single-file fixes |
| **ship** | log → commit → push → PR only | Already on branch, just ship it |

## Invocation

```
/forge-deliver [mode] [issue-number]
```

- `/forge-deliver` or `/forge-deliver ship` — ship mode (default when no mode specified and implementation is done)
- `/forge-deliver quick 153` — quick mode for issue #153
- `/forge-deliver standard 153` — standard mode
- `/forge-deliver full 153` — full ceremony

If mode is omitted, infer from context:
- If implementation is already done and user says "ship it" / "deliver" → **ship**
- If issue number is provided without explicit mode → **standard**
- If changes are docs/config only → suggest **quick**

---

## Mode: full

Run each step in order. Wait for human approval at gates before proceeding.

### Step 1 — Pre-implementation assessment
Invoke the `/forge-assess` skill with the issue number. Wait for human approval.

### Step 2 — Plan
Invoke the `/forge-plan` skill with the issue number. Wait for human approval of the plan.

### Step 3 — Start work
Invoke the `/forge-start` skill with the issue number. This syncs main, creates the feature branch, and scaffolds delivery templates.

### Step 4 — Implement
Implement the approved plan on the feature branch.

**Implementation review gate:**

1. **Label override:** Check for the `needs-human-gate` label on the issue:
   ```bash
   gh issue view <number> --json labels
   ```
   If present, or the check fails (API error), wait for human review signal before delivering.

2. **Mode check:** Check `CLAUDE_MODE` via `printenv CLAUDE_MODE`.
   - If `autonomous`: skip the review wait — the PR is the review artifact. Proceed directly to Step 5.
   - If `supervised`, unset, or unrecognized: wait for human review signal before proceeding.

### Step 5 — Deliver
Run the delivery CLI:
```bash
jp5 deliver run \
  --issue <number> \
  --commit-message "<type>: <description>" \
  --pr-title "<type>: <title>" \
  --pr-body-file tmp/issue-delivery/<number>/pr-body.md \
  --issue-comment-file tmp/issue-delivery/<number>/issue-comment.md
```

### Step 6 — Post-merge
After PR is merged, invoke the `/forge-cleanup` skill.

---

## Mode: standard

Same as full but skips the pre-implementation assessment.

### Step 1 — Plan
Invoke `/forge-plan` with the issue number. Wait for approval.

### Step 2 — Start work
Invoke `/forge-start` with the issue number.

### Step 3 — Implement
Implement on the feature branch.

**Implementation review gate:** Same as full mode Step 4 — check `needs-human-gate` label, then `CLAUDE_MODE`. If autonomous, skip review wait and proceed directly to Step 4. Otherwise, wait for human review signal.

### Step 4 — Deliver
Run `jp5 deliver run` (same as full mode Step 5).

### Step 5 — Post-merge
After PR is merged, invoke `/forge-cleanup`.

---

## Mode: quick

Minimal ceremony for low-risk changes.

### Step 1 — Start work
Invoke `/forge-start` with the issue number. This syncs main, creates the branch, and scaffolds templates.

### Step 2 — Implement
Make the changes. No formal plan required.

### Step 3 — Deliver
```bash
jp5 deliver run \
  --issue <number> \
  --commit-message "<type>: <description>" \
  --pr-title "<type>: <title>" \
  --pr-body-file tmp/issue-delivery/<number>/pr-body.md \
  --issue-comment-file tmp/issue-delivery/<number>/issue-comment.md
```

No post-merge step is orchestrated automatically — invoke `/forge-cleanup` manually if needed.

---

## Mode: ship

Bare minimum — commit, push, and open a PR. Use when already on a feature branch with changes ready.

### With linked issue

First, assign the implementing bot to the issue (ship mode skips `/forge-start`, so assignment must happen here):

```bash
gh issue edit <number> --add-assignee @me
```

This is idempotent — re-running does not error if already assigned.

Then deliver:

```bash
jp5 deliver run \
  --issue <number> \
  --commit-message "<type>: <description>" \
  --pr-title "<type>: <title>"
```
Templates are scaffolded automatically if they don't exist.

### Without linked issue
```bash
jp5 deliver run \
  --skip-comment \
  --commit-message "<type>: <description>" \
  --pr-title "<type>: <title>"
```

### Skip commit (already committed)
Add `--skip-commit` if changes are already committed.

### Dry-run
Add `--dry-run` to validate without mutating.

---

## Subcommands reference (jp5 deliver)

| Subcommand | Purpose |
|------------|---------|
| `jp5 deliver init --issue <N>` | Scaffold editable delivery templates |
| `jp5 deliver run [options]` | Full commit/push/PR/comment delivery flow |
| `jp5 deliver review --issue <N>` | Post an issue comment only (no commit/push/PR) |

## Options reference (jp5 deliver run)

| Flag | Purpose |
|------|---------|
| `--issue <int>` | GitHub issue number |
| `--commit-message` | Commit message string |
| `--pr-title` | PR title string |
| `--pr-body-file` | Path to PR body markdown file |
| `--issue-comment-file` | Path to issue comment markdown file |
| `--skip-commit/push/pr/comment` | Skip individual workflow steps |
| `--allow-mixed-scope-commit` | Allow policy + ops files in one commit |
| `--dry-run` | Validate flow without mutations |

## Staging before delivery

`jp5 deliver` does **not** run `git add`. It commits whatever is already staged. To deliver a subset of dirty files, stage them first then call deliver normally:

```bash
git add <file1> <file2>
jp5 deliver run --commit-message "..." --pr-title "..."
```

Do **not** manually `git commit` + `--skip-commit` to work around this — staging is the intended mechanism.

## Scaffold templates (any mode)

```bash
jp5 deliver init --issue <number>
```

Creates `tmp/issue-delivery/<number>/pr-body.md` and `issue-comment.md`. Edit before delivering. Keep `<replace-with-pr-link>` placeholder — it's replaced automatically.

## Branch naming

`issue-<number>-<slug>` (e.g., `issue-153-retrieval-topology`).

## Commit scope split

Policy/governance and ops/resilience changes must land in **separate commits**. Stage explicitly:

```bash
git add AGENTS.md CLAUDE.md docs/ && git commit -m "docs: <description>"
git add scripts/ .claude/ && git commit -m "feat: <description>"
```

Then deliver with `--skip-commit`.

## Context management

For multi-file or multi-round work:
- Use `Agent` tool with `subagent_type=jp5-dev` and `isolation: "worktree"` for implementation.
- Write intermediate state to `tmp/` files.
