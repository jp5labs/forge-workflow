---
name: forge-discover
description: Triage ideas into the right workflow entry point by assessing complexity. Determines whether work needs a full spec, can go directly to issue shaping, or requires decomposition into multiple specs.
---

## Purpose

Prevent over-engineering small things and under-thinking big things. Not every piece of work needs a spec. This skill triages an idea into the right entry point based on its complexity and scope.

## Trigger

Invoke this skill when:
- Starting with a vague idea that needs scoping
- Unsure whether something needs a spec or can go straight to an issue
- User says "I want to build...", "we should add...", "what about..."
- Before `/forge-spec` when the scope is unclear

## Procedure

### Step 1 — Ensure repo is current

Before assessing scope, sync the local repository to ensure context is up to date:

```bash
git fetch origin && git pull origin main
```

### Step 2 — Understand the idea

Accept a description of the idea from the user. Ask one clarifying question if the intent is ambiguous. Do not over-question — the goal is quick triage, not full design.

### Step 3 — Quick context scan

Spawn a Sonnet exploration agent to assess scope:

```
Agent(model="sonnet", subagent_type="Explore", prompt="
TOOL-DISCIPLINE RULES:
- Use Glob for file search, never find/ls
- Use Grep for content search, never grep/rg
- Use Read for file reading, never cat/head/tail

Assess the scope of this idea: <idea description>

1. What files/systems would this touch? List file paths.
2. Does this cross service boundaries (multiple systems/containers)?
3. Are there any ADRs in docs/architecture/ that govern this area?
4. Rough estimate: how many files would need to change?
5. Are there existing issues or specs that overlap? Check:
   - gh issue list --search '<relevant keywords>' --json number,title,state
   - ls docs/specs/

Report findings as a structured summary.
")
```

### Step 4 — Classify complexity

Based on the exploration findings, classify:

| Signal | Complexity |
|---|---|
| 1-2 files, single service, no ADR overlap | **Trivial** |
| 3-5 files, single service, no ADR overlap | **Low** |
| 5-15 files, may cross service boundaries | **Medium** |
| Touches architecture docs, ADR-governed areas, multiple services | **High** |
| Multiple independent subsystems, needs decomposition | **Epic** |

### Step 5 — Route to entry point

Present the classification and recommended entry point:

| Complexity | Recommendation |
|---|---|
| **Trivial** | "Skip spec. Run `/forge-shape` to create an issue directly." |
| **Low** | "Skip spec. Run `/forge-shape` to create an issue directly." |
| **Medium** | "Run `/forge-spec` with light analysis (ADR check only)." |
| **High** | "Run `/forge-spec` with full analysis (ADR + impact + arch review + dependency graph)." |
| **Epic** | "This is multiple specs. Let's decompose first." Then help the user identify 2-4 spec-worthy chunks and prioritize them. |

If existing issues or specs overlap, surface them: "Found existing issue #X / spec Y that covers part of this. Consider whether to extend that work or create new."

### Step 6 — Autonomous gate check

Before waiting for user confirmation, evaluate the gate bypass:

1. **Label override:** If working on a GitHub issue, check for the `needs-human-gate` label:
   ```bash
   gh issue view <number> --json labels
   ```
   If the label is present, or the check fails (API error), skip to Step 7 and wait for user confirmation (supervised behavior).

2. **Mode check:** Check `CLAUDE_MODE` via `printenv CLAUDE_MODE`.
   - If `autonomous`: auto-proceed to the recommended entry point. Post a brief note: "Routing auto-confirmed (autonomous mode) — proceeding to `<recommended skill>`."
   - If `supervised`, unset, or unrecognized: skip to Step 7 and wait for user confirmation.

No skill-specific halt conditions — routing is informational and misclassification is caught by downstream gates.

### Step 7 — Hand off

After the user confirms the route (or after auto-confirmation in autonomous mode):
- For Trivial/Low: suggest running `/forge-shape`
- For Medium/High: suggest running `/forge-spec <topic>`
- For Epic: help decompose, then suggest running `/forge-spec` for the first chunk

## Model Routing

The triage exploration agent runs on **Sonnet** (cheap classification). The interactive conversation runs on the session's model (typically Opus).

When dispatching the exploration:
```
Agent(model="sonnet", subagent_type="Explore", prompt="...")
```

## Authority

This skill does NOT:
- Create issues (that's `/forge-shape`)
- Write specs (that's `/forge-spec`)
- Make architecture decisions (that's `/arch-review`)

It only classifies and routes.
