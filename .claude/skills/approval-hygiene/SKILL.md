---
name: approval-hygiene
description: Analyze session re-approvals, grade patterns A-F, recommend settings.json changes. Works standalone or via /forge-cleanup.
user-invocable: true
---

## Purpose

Track and analyze permission re-approval prompts from a session, grade each pattern for safety (A-F), and recommend concrete actions — promote to allow list, narrow the pattern, or suggest alternative toil-reduction approaches. Applies approved changes via `/update-config`.

## Trigger

Run this skill when:
- User invokes `/approval-hygiene` directly
- At the end of `/forge-cleanup` when `/tmp/forge-approval-log.jsonl` exists
- User asks to review or audit session permissions

## Data Source

The `PermissionRequest` hook (`scripts/hooks/approval-logger.py`) appends one JSONL line per re-approval to `/tmp/forge-approval-log.jsonl`:

```json
{"ts":"2026-03-26T16:00:00Z","tool":"Bash","input":{"command":"pip install requests","description":"Install package dependencies"},"session_id":"abc123"}
```

Key fields:
- `tool` — the tool type (Bash, Edit, Write, etc.)
- `input` — the full tool_input object; for Bash calls, includes `command` and `description` (the agent's stated intent)
- `session_id` — groups entries by session

## Procedure

### Step 0 — Mode guard

Check the `CLAUDE_MODE` environment variable by running `printenv CLAUDE_MODE`.

If the value is `autonomous`, exit immediately with the message: **"Skipped — approval logging is not active in autonomous mode."** Do not proceed to Step 1.

If the value is `supervised` or unset (empty/not present), continue normally.

### Step 1 — Read the log

Read `/tmp/forge-approval-log.jsonl` using the Read tool. If the file doesn't exist or is empty, report "No re-approval data found for this session" and stop.

**Session filtering:** The log may contain entries from multiple sessions within a container lifetime. When running standalone (not via `/forge-cleanup`), filter entries to the current `session_id` only. If the current session has no entries but older sessions do, note: "No re-approvals in current session. Log contains <N> entries from previous sessions — run cleanup to clear, or analyze all sessions by request."

### Step 2 — Group and normalize patterns

Group log entries by `tool` + normalized command pattern:
- Strip variable arguments to create generic patterns (e.g., `pip install requests` → `pip install *`)
- Keep tool-specific prefixes (e.g., `Bash(pip install *)`, `Edit(/workspace/some/file.py)`)
- Count occurrences of each pattern
- Collect unique `input.description` values per pattern (these represent the agent's intent)

### Step 3 — Grade each pattern A-F

Apply the following grading criteria to each normalized pattern:

| Grade | Criteria | Primary Action |
|-------|----------|----------------|
| **A** | Read-only, no side effects, no network (e.g., `git log`, `ls`, `head`, `tail`) | Auto-elevate to project settings |
| **B** | Scoped writes, plugin-gated, project-path-restricted, known safe hosts (e.g., `pip install -e .`, `gh api`) | Elevate with operator review |
| **C** | Install commands, network to known hosts, scoped wildcards (e.g., `pip install <pkg>`, `curl https://pypi.org/*`) | Suggest narrower allow-list pattern + alternative toil reduction |
| **D** | Broad wildcards, unknown scripts, arbitrary network (e.g., `python unknown_script.py`, `curl *`) | Suggest deny rule + alternative toil reduction |
| **E** | Privilege escalation, global config changes (e.g., `sudo *`, `chmod 777 *`) | Hard deny recommendation + alternative approach |
| **F** | Destructive ops, force push, secret exposure (e.g., `rm -rf *`, `git push --force`, reading `.env`) | Hard deny, flag if not already in deny list |

### Step 4 — Generate the report

Produce a report using a **stacked card layout** — one card per pattern, no wide tables. This format is readable on narrow screens (Discord, mobile, terminal panels).

```
## Session Approval Hygiene Report
Re-approvals: <total> | Safety: <overall grade>

---

### 1. `Bash(pip install -e .)`
**Grade:** B — Elevate with review
**Count:** 3
**Intent:** "Install package dependencies"
**Justification:** Runs `pip install` scoped to the current project (`-e .`). Writes only to the local virtualenv. No arbitrary package names, no network to unknown hosts. Safe for project-scoped development.
**Recommendation:** Elevate → `Bash(pip install -e *)`

---

### 2. `Bash(docker build *)`
**Grade:** C — Suggest narrower pattern
**Count:** 2
**Intent:** "Build Docker image for testing"
**Justification:** Docker build executes a Dockerfile which can run arbitrary commands (RUN steps), pull from external registries, and modify the build context. The broad `*` wildcard would allow building any Dockerfile in any directory.
**Recommendation:** Narrow → `Bash(docker build -t jp5-*)`
**Alternatives:**
1. Narrow allow: `Bash(docker build -t jp5-*)` (effort: xs, safety: B)
2. Skill change: update build skill to use pre-approved `jp5 build` CLI (effort: s)

---

### 3. `Bash(rm -rf dist/)`
**Grade:** D — Suggest deny + alternative
**Count:** 1
**Intent:** "Clean build artifacts"
**Justification:** `rm -rf` is a destructive operation. While `dist/` is a known build output directory, the pattern could be broadened to match other paths. Already partially covered by the existing `Bash(rm -rf*)` deny rule.
**Recommendation:** Deny — already covered
**Alternatives:**
1. Agent instruction: add to tool-discipline — "use `jp5 clean` instead of `rm -rf`"
2. Already denied by `Bash(rm -rf*)` — agent should use dedicated cleanup

---

### Suggested changes

**Allow:**
+ `Bash(pip install -e *)` [B]
+ `Bash(curl -s https://pypi.org/*)` [B]

**Deny:**
+ `Bash(rm -rf /*)` [F — not currently denied]

**Narrow:**
~ `Bash(docker build *)` → `Bash(docker build -t jp5-*)` [C→B]
```

Each card must include:
- **Grade** with the letter and a short label (e.g., "B — Elevate with review")
- **Count** of occurrences
- **Intent** from `input.description` (the agent's stated reason)
- **Justification** — 1-3 sentences explaining: what the command does, what its blast radius is, and why it received this grade. Be specific about side effects, network access, write scope, and privilege level.
- **Recommendation** — the concrete action
- **Alternatives** (C-F only) — prioritized list of toil-reduction approaches

#### Alternative toil-reduction strategies (for C-F patterns)

When a pattern is not safe to promote, include alternatives in the card. Explore in priority order:

1. **Agent instructions** — agent uses a shell command when a dedicated tool or pre-approved pattern exists (e.g., `grep -r "foo"` → use `Grep` tool)
2. **Skill changes** — a skill generates commands that aren't pre-approved (e.g., refactor to use pre-approved CLI)
3. **Hook automation** — a manual step could be automated via hook (e.g., auto-run `ruff check`)
4. **Narrower allow-list pattern** — command is safe but current form is too broad (e.g., `pip install *` → `pip install -e .`)
5. **Compound pattern addition** — two approved commands chained but compound isn't listed
6. **Deny + document** — operation is genuinely unsafe, add deny rule + document why

### Step 5 — Present for operator confirmation

Display the full report to the operator. Wait for explicit confirmation before applying any changes.

Highlight any escalation items:
- F-grade patterns not already in the deny list
- Patterns that appear >5 times (high-toil)
- Patterns where intent suggests a safer built-in alternative exists

### Step 6 — Apply approved changes

For each change the operator approves, invoke `/update-config` to apply the change to settings.json:
- Allow-list additions
- Deny-list additions
- Pattern narrowing (remove broad pattern, add narrow replacement)

Do not apply changes the operator did not explicitly approve.

### Step 7 — Cleanup confirmation

After applying approved changes, present a single cleanup confirmation covering both items:

**Local settings purge:**
Check `.claude/settings.local.json` for entries that overlap with session re-approvals but were not promoted. List them and explain: "If a pattern is too risky to promote to project settings, it's too risky to keep in local settings without re-approval."

**Log file cleanup:**
Offer to delete `/tmp/forge-approval-log.jsonl` now that analysis is complete. The log accumulates across sessions within a container lifetime — clearing it keeps future reports scoped to the next session only.

Present both items together and ask for a single confirmation:
- "Clean up local settings + delete log? (y/n)"
- If confirmed, purge the unpromoted local entries and delete the log file
- If declined, leave both in place — the operator may want to review the raw data or keep local settings for now
