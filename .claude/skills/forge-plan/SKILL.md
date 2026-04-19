---
name: forge-plan
description: Run a full implementation planning session using writing-plans methodology with context assembly, or lightweight native plan mode with --lite. Run after /forge-assess approves the story and before /forge-start.
user-invocable: true
---

## Purpose

Drive the implementation planning ritual through two modes:

- **Full mode** (default): Assembles JP5 context from issue, assessment, spec, and codebase exploration, then invokes `superpowers:writing-plans` to produce a detailed implementation plan with file mapping, bite-sized TDD steps, and code-in-plan.
- **Lite mode** (`--lite`): Lightweight planning via native Claude Code plan mode. Posts a high-level plan to the issue. For standalone use outside the delivery workflow.

## Trigger

Run this skill when:
- `/forge-assess` has been approved and it's time to design the implementation
- User says "plan this", "let's plan", or "start planning issue X"
- A story is approved and needs a concrete implementation design before branching

## Arguments

```
/forge-plan <number> [--lite] [--execute=subagent|inline|manual]
```

- `<number>` — required. GitHub issue number.
- `--lite` — optional. Use lightweight native plan mode instead of full writing-plans methodology.
- `--execute=subagent|inline|manual` — optional. Override the default execution strategy in Phase 4. Only applies to full mode.

## Procedure — Full Mode (default)

### Phase 1 — Context Assembly

Build a unified context package from multiple JP5 sources.

#### Step 1 — Fetch issue context

```bash
gh issue view <number> --json title,body,comments,labels,milestone
gh pr list --search "closes:#<number>" --state open
```

#### Step 2 — Extract assessment comment

Scan the issue comments for an assessment comment (posted by `/forge-assess`). Look for comments containing "Pre-Implementation Assessment" or "Spec Conformance Check".

- If found: extract the full assessment content (risks, alternatives, recommendation)
- If not found: warn "No assessment comment found on issue #`<number>`. Assessment is recommended but not required — proceeding without it."

#### Step 3 — Read linked spec (if present)

Check the issue body for a `Spec:` link (e.g. `Spec: docs/specs/2026-03-24-my-feature.md`):

1. Scan the body field for a line matching `Spec: <path>`
2. If found: read the spec file using the `Read` tool. Extract the Design, Analysis, Constraints, and Dependencies sections.
3. If the spec file doesn't exist at the path: warn "Spec file not found at `<path>`, proceeding with unscoped exploration"
4. If no `Spec:` link is present: proceed without spec context

#### Step 4 — Spawn codebase explorer

**When a spec WAS found**, scope the explorer to the spec's affected areas:

```
Agent(model="sonnet", subagent_type="feature-dev:code-explorer", prompt="
TOOL-DISCIPLINE RULES (this project requires these conventions):
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never use cat > file or heredocs — use the Write tool
- Never use ${} in Bash commands — use printenv VAR instead
- Never run mkdir before delivery scripts — they create directories automatically

The spec at <path> identifies these affected areas: <list from spec>.
Explore ONLY these areas. Map existing patterns, dependencies, and
integration points relevant to implementing issue #<number>: <brief description>.
The spec's architecture decisions are: <decisions from spec>.
Do not re-derive architecture — validate that these decisions are
still sound given the current codebase state.
Report file paths, key abstractions, and integration points.")
```

**When NO spec was found**, use open-ended exploration:

```
Agent(model="sonnet", subagent_type="feature-dev:code-explorer", prompt="
TOOL-DISCIPLINE RULES (this project requires these conventions):
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never use cat > file or heredocs — use the Write tool
- Never use ${} in Bash commands — use printenv VAR instead
- Never run mkdir before delivery scripts — they create directories automatically

Explore the codebase areas affected by issue #<number>: <brief description>.
Map existing patterns, reusable utilities, and dependencies.
Report file paths, key abstractions, and integration points.")
```

#### Step 5 — Assemble context package

Combine all gathered context into a single markdown document:

```markdown
## Issue
<title, body, labels, milestone from gh issue view>

## Assessment
<assessment comment content — risks, alternatives, recommendation>
<or: "No assessment available.">

## Spec (if linked)
<Design, Analysis, Constraints sections from the spec file>
<or: omit this section entirely>

## Codebase Context
<explorer findings — affected files, patterns, dependencies, integration points>
```

### Phase 2 — Invoke writing-plans

Invoke `superpowers:writing-plans` with three overrides stated before the skill invocation:

> **IMPORTANT OVERRIDES FOR THIS PLANNING SESSION:**
>
> 1. **Output path override:** Save the plan to `tmp/issue-delivery/<number>/implementation-plan.md` (NOT `docs/superpowers/plans/`).
>
> 2. **Context injection:** Use the following context package as the spec/requirements input for the plan. Do not re-explore the codebase — the exploration is already done:
>
> <paste context package from Phase 1>
>
> 3. **Handoff suppression:** After self-review, STOP. Do NOT offer execution handoff (no subagent-driven vs inline choice). Return control — there is more work to do before execution.
>
> 4. **TDD policy:** Use TDD steps (write failing test → verify failure → implement → verify pass → commit) for tasks that produce code with testable behavior. For config, docs, and skill file changes, substitute appropriate verification steps (e.g., "invoke the skill and confirm output", "validate YAML syntax", "check markdown renders correctly").

Then invoke:

```
Skill(skill="superpowers:writing-plans")
```

When writing-plans completes and the plan is written to `tmp/issue-delivery/<number>/implementation-plan.md`, Phase 2 is done.

**Fallback:** If writing-plans invocation fails or produces inadequate output, announce: "Full planning methodology unavailable — falling back to lightweight plan." Then execute the Lite Mode procedure below.

### Phase 3 — JP5 Enrichment

#### Step 1 — Risk cross-check

If an assessment was extracted in Phase 1 Step 2, scan the plan for coverage of each risk identified in the assessment:

1. List the risks from the assessment (each "Risk N:" line or bullet under "Key Risks / Regressions" or "Spec Risks")
2. For each risk, check whether the plan addresses it — either directly in a task, in a verification step, or in the plan's architecture section
3. If any risks are unaddressed, flag them to the user:
   > "The following assessment risks are not addressed in the plan:"
   > - Risk: [description] — not covered by any plan task
4. Ask whether to revise the plan to address them or accept as-is

If no assessment was available (Phase 1 warned about missing assessment), skip this step with: "No assessment available — skipping risk cross-check."

#### Step 2 — Post plan to GitHub issue

Post the plan as a GitHub issue comment:

```bash
gh issue comment <number> --body-file tmp/issue-delivery/<number>/implementation-plan.md
```

- If the post succeeds: confirm "Plan posted to issue #`<number>`."
- If the post fails: non-blocking warning. Announce: "GitHub comment post failed — plan exists locally at `tmp/issue-delivery/<number>/implementation-plan.md`." Continue to approval gate.

#### Step 3 — Approval gate (hard)

Wait for explicit human approval before proceeding. The human reviews the plan (on the GitHub issue or locally) and either approves or requests revisions.

**Enforcement gate: do not proceed to execution or write any implementation code without explicit human approval.**

If revisions are requested:
1. Incorporate the feedback
2. Re-enter Phase 2 — re-invoke writing-plans with the revision feedback added to the context
3. Re-run Phase 3 (risk cross-check and re-post)
4. Repeat until approved

### Phase 4 — Execution Handoff

After the plan is approved in Phase 3, determine the execution strategy and dispatch.

#### Step 1 — Analyze task dependency graph

Read the plan from `tmp/issue-delivery/<number>/implementation-plan.md` and analyze the task structure:

- **Mostly independent:** Tasks can run in parallel with no ordering constraints between them
- **Mostly sequential:** Tasks depend on prior tasks (shared state, file modifications that build on each other)
- **Mixed:** Some clusters of independent tasks, with sequential dependencies between clusters

#### Step 2 — Determine execution strategy

**If `--execute` argument was provided**, use the specified strategy directly (skip auto-selection).

**If no `--execute` argument**, determine the default strategy from `CLAUDE_MODE` and task structure:

| CLAUDE_MODE | Task structure | Default strategy |
|---|---|---|
| autonomous | mostly independent | subagent-driven (parallel dispatch) |
| autonomous | mostly sequential | inline (single session) |
| autonomous | mixed | subagent-driven per cluster, sequential within |
| supervised (or unset) | any | offer choice: subagent-driven, inline, or manual |

To check `CLAUDE_MODE`:

```bash
printenv CLAUDE_MODE
```

If the variable is not set or empty, treat as supervised mode.

**When offering a choice (supervised mode):**

> "Plan approved. How would you like to execute?"
>
> 1. **Subagent-driven** — fresh subagent per task, parallel where possible, review between tasks
> 2. **Inline** — execute tasks in this session with checkpoints
> 3. **Manual** — I'll announce the plan is ready; you drive implementation yourself

#### Step 3 — Run /forge-start

Before dispatching any execution, invoke `/forge-start` to sync main, create the feature branch, and scaffold delivery templates:

```
Skill(skill="forge-start", args="<number>")
```

#### Step 4 — Dispatch execution

**Subagent-driven:**

```
Skill(skill="superpowers:subagent-driven-development")
```

Provide the plan file path (`tmp/issue-delivery/<number>/implementation-plan.md`) as context.

**Inline:**

```
Skill(skill="superpowers:executing-plans")
```

Provide the plan file path as context.

**Manual handoff:**

Announce: "Plan approved. Branch `issue-<number>-<slug>` is ready. Run `/forge-start <number>` if not already done, then implement per the plan at `tmp/issue-delivery/<number>/implementation-plan.md`."

**Fallback:** If execution dispatch fails (skill invocation error), fall back to manual handoff. Announce: "Execution dispatch failed — falling back to manual handoff." Then print the manual handoff message.

---

## Procedure — Lite Mode (`--lite`)

Preserves the original `/forge-plan` behavior exactly.

### Step 1 — Gather issue context

```bash
gh issue view <number> --json title,body,comments,labels,milestone
gh pr list --search "closes:#<number>" --state open
```

Read any existing assessment comment on the issue (posted by `/forge-assess`).

#### Spec detection

Check the issue body for a `Spec:` link:
1. Scan the body for a line matching `Spec: <path>`
2. If found: read the spec file. Extract affected areas/components, architecture decisions, and arch-review findings.
3. If spec file doesn't exist: warn and continue without spec scoping
4. If no `Spec:` link: proceed with standard behavior

### Step 2 — Write issue anchor for the hook

Write the issue number to `tmp/.plan-issue`:

1. Read `tmp/.plan-issue` first (may not exist — expected)
2. Write the issue number using the `Write` tool

This lets the `post-plan-to-issue.py` PreToolUse hook find the issue when `ExitPlanMode` fires.

### Step 3 — Enter plan mode

Call `EnterPlanMode` to begin native Claude Code planning.

In plan mode:

#### Explorer dispatch (spec-aware)

**When a spec WAS found**, scope the explorer:

```
Agent(subagent_type="feature-dev:code-explorer", prompt="
TOOL-DISCIPLINE RULES (this project requires these conventions):
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never use cat > file or heredocs — use the Write tool
- Never use ${} in Bash commands — use printenv VAR instead
- Never run mkdir before delivery scripts — they create directories automatically

The spec at <path> identifies these affected areas: <list from spec>.
Explore ONLY these areas. Map existing patterns, dependencies, and
integration points relevant to implementing issue #<number>: <brief description>.
The spec's architecture decisions are: <decisions from spec>.
Do not re-derive architecture — validate that these decisions are
still sound given the current codebase state.
Report file paths, key abstractions, and integration points.")
```

**When NO spec was found:**

```
Agent(subagent_type="feature-dev:code-explorer", prompt="
TOOL-DISCIPLINE RULES (this project requires these conventions):
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never use cat > file or heredocs — use the Write tool
- Never use ${} in Bash commands — use printenv VAR instead
- Never run mkdir before delivery scripts — they create directories automatically

Explore the codebase areas affected by issue #<number>: <brief description>.
Map existing patterns, reusable utilities, and dependencies.
Report file paths, key abstractions, and integration points.")
```

#### Plan content

- Use the explorer's findings to design the implementation approach informed by the pre-impl assessment
- Write the plan to the session plan file (path provided by the system when plan mode activates)
- The plan must include:
  - **Context** section — why this change, what prompted it, intended outcome
  - **Verification** section — how to test end-to-end
  - Coverage of key risks and alternatives identified in the assessment
  - **When spec-driven:** explicit statement that the plan implements the spec's design for this issue, with spec arch-review findings carried forward (not re-derived)

Call `ExitPlanMode` to signal the plan is complete and ready for user approval.

**The `post-plan-to-issue.py` hook fires automatically before `ExitPlanMode` completes** — it posts the plan to the GitHub issue.

**Enforcement gate: do not write any implementation code before `ExitPlanMode` is called and the plan is approved by explicit human approval.**

### Step 4 — Wait for approval

After the plan is posted to the issue, wait for explicit human approval. If revisions requested, update the plan, call `ExitPlanMode` again to re-post, and repeat.

### Step 5 — Hand off to start-work

Once approved, announce: "Plan posted to issue #`<number>`. Run `/forge-start <number>` to sync main, create the branch, and scaffold delivery templates."

## Error Handling

- **No assessment comment found:** Warn but proceed — assessment is recommended but not required. Risk cross-check (Phase 3 Step 1) is skipped.
- **No spec linked:** Proceed with unscoped exploration. Context package omits the Spec section.
- **writing-plans invocation fails:** Fall back to lite mode. Announce: "Full planning methodology unavailable — falling back to lightweight plan."
- **GitHub comment post fails (full mode, Phase 3):** Non-blocking warning — plan exists locally at `tmp/issue-delivery/<number>/implementation-plan.md`. Continue to approval gate.
- **Execution dispatch fails (full mode, Phase 4):** Fall back to manual handoff. Announce failure and print manual handoff message.
- **CLAUDE_MODE not set:** Treat as supervised mode — offer choice rather than auto-selecting.
- **GitHub comment post fails (lite mode hook):** Non-blocking — the hook logs the error but does not block approval.

## Model Routing

| Actor | Model | Rationale |
|---|---|---|
| Orchestrator (interactive session) | Opus | Judgment, routing, context assembly |
| Code explorer | Sonnet | Fast codebase exploration |
| writing-plans (Phase 2) | Opus (inherited) | Detailed plan authoring |

## Subagent tool discipline

When spawning system agents (Explore, Plan, general-purpose) during planning, include the subagent prompt preamble from CLAUDE.md's "Subagent prompt preamble" section in the `prompt` parameter to ensure tool-discipline rules are followed.
