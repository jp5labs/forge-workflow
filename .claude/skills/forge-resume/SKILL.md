---
name: forge-resume
description: Reconstruct session context from persistent GitHub artifacts when resuming work on an issue. Reads spec, assessment, plan, branch status, and milestone siblings to present current state and suggest next action.
---

## Purpose

Reconstruct full context from persistent artifacts when starting a new session or handing off work between bots. All artifacts are read from GitHub (the shared store across isolated bot containers), not local filesystem.

## Trigger

Invoke this skill when:
- Resuming work on an issue in a new session
- A bot is picking up work started by another bot
- User says "resume", "pick up where we left off", "continue work on #X"
- Starting any issue work where prior context may exist

## Procedure

### Step 1 — Read issue from GitHub

Accept the issue number from the invocation argument (e.g. `/forge-resume 401`).

```bash
gh issue view <number> --json title,body,comments,labels,milestone,state
```

Extract from the issue body:
- `Spec:` link (if present) — path to the spec file in the repo
- Parent spec issue (if this is a sub-issue)

### Step 2 — Read spec file (if linked)

If the issue body contains a `Spec:` link, read the spec file from the repo:

```
Read: <spec-file-path>
```

This provides the full design context in ~500 tokens — architecture decisions, constraints, blast radius, dependencies.

### Step 3 — Read assessment from GitHub comments

Scan issue comments for the assessment (posted by `post-assessment-to-issue.py` hook). Look for comments containing "## Pre-Implementation Assessment".

If found, extract the assessment content. If not found, note "No assessment posted yet."

### Step 4 — Read plan from GitHub comments

Scan issue comments for the implementation plan (posted by `post-plan-to-issue.py` hook). Look for comments containing the plan content.

If found, extract the plan content. If not found, note "No plan posted yet."

### Step 5 — Check branch and PR status

```bash
git fetch origin
```

Use the Glob tool to check for a matching branch:
```
Glob(pattern="refs/remotes/origin/issue-<number>-*", path=".git")
```

Or use `gh` to check for PRs from the branch:
```bash
gh pr list --search "head:issue-<number>" --json number,title,state,headRefName
```

If a branch exists:
```bash
git log main..origin/issue-<number>-* --oneline
```

Check for an open PR:
```bash
gh pr list --search "head:issue-<number>" --json number,title,state,reviews,reviewDecision
```

If a PR exists, also fetch review comments:
```bash
gh api repos/{owner}/{repo}/pulls/<pr-number>/comments
```

### Step 6 — Check milestone siblings

If the issue belongs to a milestone or has a parent spec issue:

```bash
gh issue list --milestone "<milestone-name>" --json number,title,state
```

Or if tracking via spec issue parent:
```bash
gh api repos/{owner}/{repo}/issues/<spec-issue>/timeline
```

Report which sibling issues are open, in progress, or closed.

### Step 7 — Present status summary and suggest next action

Present a structured summary:

```
Issue #<number>: <title>
Spec: <path or "none">
Branch: <branch name or "no branch yet">
Commits: <N commits ahead of main>
PR: <#number (state) or "no PR">
Assessment: <posted / not posted>
Plan: <posted / not posted>
Milestone: <name> (<N/M issues closed>)

Suggested next action: <one of the following>
```

Decision logic for suggested action:
- No branch exists → "Run `/forge-start <number>` to create branch and scaffold"
- Branch exists, no assessment → "Run `/forge-assess <number>` for spec conformance check"
- Assessment posted, no plan → "Run `/forge-plan <number>` to design implementation"
- Plan posted, work not started → "Run `/forge-start <number>` if branch not scaffolded, then begin implementation"
- Work in progress (commits exist) → "Continue implementation. Last commit: <message>"
- PR open, reviews pending → "Address review comments on PR #<number>"
- PR open, approved → "Merge PR #<number>, then run `/forge-cleanup`"
- PR merged → "Run `/forge-cleanup` to complete post-merge cleanup"

## Model Routing

This skill runs on **Sonnet** — it reads artifacts and classifies state, no creative judgment needed.

When spawning as a subagent:
```
Agent(model="sonnet", prompt="/forge-resume <number> ...")
```
