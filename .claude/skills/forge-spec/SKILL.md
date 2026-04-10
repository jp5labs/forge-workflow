---
name: forge-spec
description: Root orchestrator for spec-driven ideation. Wraps superpowers brainstorming for design Q&A, then enriches the spec with conditional architecture/ADR/impact analysis. Produces an approved spec file ready for issue decomposition.
user-invocable: true
---

## Purpose

Produce complete design documents enriched with architecture, ADR, and impact analysis. The spec is the creative spine of all work — it captures design decisions, constraints, and rationale. Everything downstream (issues, plans, implementations, reviews) traces back to the spec.

Run after `/forge-discover` classifies work as Medium, High, or Epic complexity. For Trivial/Low complexity, skip this and use `/forge-shape` directly.

## Trigger

Invoke this skill when:
- `/forge-discover` routes work as Medium, High, or Epic complexity
- User says "spec this", "let's design", "draft a spec for"
- User invokes `/forge-spec` directly with a topic
- Work requires formal design before implementation

## Arguments

```
/forge-spec <topic>
```

The topic is a short description of what to design (e.g., "retrieval caching", "bot notification routing").

## Procedure

### Phase 1 — Brainstorming (Interactive Q&A)

This phase leverages the `superpowers:brainstorming` skill for interactive design work. Before invoking it, set three overrides:

**Pre-instruction overrides (state these before invoking brainstorming):**

> **IMPORTANT OVERRIDES FOR THIS BRAINSTORMING SESSION:**
>
> 1. **Template override:** Use the JP5 spec template below instead of the default brainstorming template. The Analysis sections should be left as placeholders — they will be populated by automated analysis after brainstorming completes.
>
> 2. **Output path override:** Write the spec to `docs/specs/YYYY-MM-DD-<topic>.md` (NOT `docs/superpowers/specs/`).
>
> 3. **Exit override:** After the user reviews and approves the written spec, STOP. Do NOT invoke `writing-plans` or any implementation skill. Return control — there is more work to do (analysis enrichment) before implementation planning.

**JP5 spec template for brainstorming to fill in:**

```markdown
# <Title>

**Date:** YYYY-MM-DD
**Author:** <who>
**Status:** Draft | Approved | In Progress | Implemented
**Milestone:** <milestone name, if known>

## Problem
## Decision
## Design

### Architecture
### Components
### Data Flow
### Error Handling

## Analysis

> Analysis sections below are populated by automated analysis after
> brainstorming. Leave as placeholders during design Q&A.

### Constraints
### Blast Radius
### Architecture Alignment
### Dependencies
### Approach Decision

## Verification
## Open Questions
## Brainstorming Record
```

**Then invoke brainstorming:**

```
Skill(skill="superpowers:brainstorming", args="<topic>")
```

Brainstorming runs its full process: context exploration, one-at-a-time clarifying questions, 2-3 approaches with trade-offs, section-by-section design presentation, self-review, and user review of the written spec.

**When brainstorming completes and the user has approved the spec draft, continue to Phase 2.** Do not invoke `writing-plans`.

### Phase 2 — Analysis Enrichment

After brainstorming writes and the user approves the spec draft, read the spec file and determine which analyses to dispatch.

#### Step 1 — Evaluate the dispatch table

Read the spec draft from `docs/specs/YYYY-MM-DD-<topic>.md`. Based on the design content, evaluate which analyses to run. The table below uses skill names as shorthand for the type of analysis — the actual dispatch uses `Agent()` calls in Step 2, not `Skill()` invocations:

| If the spec... | Then run analysis equivalent to... |
|---|---|
| References architecture docs, platform map concepts, service boundaries, or topology | arch-review + adr-check |
| Affects multiple systems, services, or containers | impact-analysis + dependency-graph |
| Brainstorming Record shows 2+ viable approaches and the decision was close | scenario-compare |
| Single-service change, no ADR overlap, clear single approach | **None** — skip to Phase 3 |

Multiple conditions can be true simultaneously. Dispatch all that apply.

If no analyses are needed, state why (e.g., "single-service change, no ADR boundaries, clear approach") and skip to Phase 3.

#### Step 2 — Dispatch parallel analysis subagents

Launch all applicable analyses as parallel Sonnet subagents. Each gets a focused prompt with only the spec sections relevant to that analysis — not the full document.

**ADR compliance check:**
```
Agent(model="sonnet", subagent_type="feature-dev:code-architect",
      prompt="TOOL-DISCIPLINE RULES:
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never run mkdir before delivery scripts — they create directories automatically

Read all docs/architecture/adr-*.md files and docs/architecture/ai_stack_platform_map.md.
Evaluate the following spec for ADR compliance. Flag any normative clause violations
(must/must not/required/denied/always/never). Also check platform map anti-patterns.

Spec summary:
<paste Problem, Decision, and Architecture sections>

Return structured findings per ADR with verdict PASS/FAIL.")
```

**Architecture review:**
```
Agent(model="sonnet", subagent_type="feature-dev:code-architect",
      prompt="TOOL-DISCIPLINE RULES:
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never run mkdir before delivery scripts — they create directories automatically

Read docs/architecture/ai_stack_platform_map.md, docs/architecture/node-topology.md,
and docs/architecture/stack-overview.md. Evaluate the following spec for architecture
alignment. Check native-first rule compliance, topology placement, and anti-pattern list.

Spec summary:
<paste Problem, Decision, and Architecture sections>

Return verdict (APPROVED/CONCERNS/BLOCKED) with specific findings.")
```

**Impact analysis:**
```
Agent(model="sonnet", subagent_type="feature-dev:code-architect",
      prompt="TOOL-DISCIPLINE RULES:
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never run mkdir before delivery scripts — they create directories automatically

Assess the blast radius of the following spec. Identify affected systems, teams,
integration points, and risks. Score impact by system (low/medium/high).

Spec summary:
<paste Problem, Decision, Components, and Data Flow sections>

Return structured impact assessment with affected systems table and risk scores.")
```

**Dependency graph:**
```
Agent(model="sonnet", subagent_type="Explore",
      prompt="TOOL-DISCIPLINE RULES:
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never run mkdir before delivery scripts — they create directories automatically

Map upstream and downstream dependencies for the systems affected by this spec.
Read relevant source files and documentation to identify integration points.

Spec summary:
<paste Components and Data Flow sections>

Return a Mermaid dependency diagram with critical paths and single points of failure.")
```

**Scenario comparison** (only if 2+ close approaches in Brainstorming Record):
```
Agent(model="sonnet", subagent_type="feature-dev:code-architect",
      prompt="TOOL-DISCIPLINE RULES:
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never run mkdir before delivery scripts — they create directories automatically

Compare the following architectural approaches from a brainstorming session.
Evaluate cost, complexity, risk, timeline, and scalability for each.

Approaches:
<paste the 2+ approaches from Brainstorming Record with their trade-offs>

Return a weighted decision matrix (Cost 25%, Technical fit 25%, Risk 20%,
Timeline 15%, Scalability 15%) with recommendation.")
```

#### Step 3 — Merge findings into spec

Map analysis results to spec sections:

| Analysis | Spec Section | Content to write |
|---|---|---|
| ADR check | **Constraints** | ADR compliance findings, normative clause violations |
| Impact analysis | **Blast Radius** | Affected systems, teams, risk scores |
| Architecture review | **Architecture Alignment** | Native-first compliance, topology placement, verdict |
| Dependency graph | **Dependencies** | Mermaid diagram, critical paths, SPOFs |
| Scenario comparison | **Approach Decision** | Decision matrix, weighted scores, recommendation |

For sections where no analysis was dispatched, write a one-liner: "No analysis required — [reason]."

Use the `Edit` tool to update each Analysis section in the spec file.

#### Step 4 — Resolve conflicts

When an analysis finding contradicts a design decision from brainstorming:

1. **Identify** the specific conflict (e.g., "Design section says X, but ADR-004 requires Y")
2. **Recommend** a resolution with rationale: revise the spec, update the ADR, or accept with documented exception
3. **Present** all conflicts together so the user sees the full picture
4. **Wait** for the user to decide on each conflict
5. **Apply** the user's decisions to the spec file

If no conflicts exist, state "No conflicts between design and analysis findings" and proceed.

### Phase 3 — Review and Approval

#### Step 1 — Sonnet spec review

After analysis findings are merged (or skipped), spawn a Sonnet reviewer:

```
Agent(model="sonnet", subagent_type="feature-dev:code-reviewer",
      prompt="TOOL-DISCIPLINE RULES:
- Use Write tool for file creation, never cat/heredoc
- Use Read tool for file reading, never cat/head/tail
- Use Glob tool for file search, never find/ls
- Use Grep tool for content search, never grep/rg
- Use Edit tool for file modification, never sed/awk
- Use gh CLI for all GitHub operations (reads and mutations)
- All common gh commands are pre-approved in the allowlist
- Never use python -c or python3 -c (denied) — process data in-context
- Commit identity: use export GIT_AUTHOR_NAME/GIT_COMMITTER_NAME, not git -c
- Never run mkdir before delivery scripts — they create directories automatically

Review the following spec for quality. Check:
1. Integration quality — are analysis findings addressed in the design, not just appended?
2. Internal consistency — do Design sections and Analysis sections contradict each other?
3. Completeness — are all template sections filled? Any leftover placeholders?
4. Unresolved items — any Open Questions that should have been answered by analysis?

Spec:
<paste full spec content>

Report issues found with specific section references. If no issues, say 'Spec is clean.'")
```

If the reviewer finds issues, present them to the user. Propose fixes and apply after user approval. If clean, proceed.

#### Step 2 — User approval gate

Present the final spec with a summary of what changed since brainstorming:

- Which analyses ran and key findings
- Any conflicts that were resolved and how
- Any reviewer issues that were fixed

Ask: "Spec is ready for approval. Review `docs/specs/<file>.md` and confirm to proceed."

**Wait for explicit user approval before continuing.**

#### Step 3 — Exit with next-step guidance

After approval, evaluate the spec's scope and present the appropriate next step:

- **Multi-issue scope** (multiple components, phases, or independent slices):
  > "Spec approved and written to `docs/specs/<file>.md`. Next step: `/forge-shape --from-spec docs/specs/<file>.md` to decompose into issues."

- **Single-issue scope** (one bounded deliverable):
  > "This spec maps to a single story — it can go directly to implementation. You can proceed with `/forge-plan` to plan the implementation, or run `/forge-shape` first to create a tracking issue."

## Error Handling

- **Brainstorming aborted by user:** Spec draft may or may not exist. Do not continue to analysis. No cleanup needed — a partial Draft spec in `docs/specs/` is fine.
- **Analysis subagent fails:** Report the failure and skip that analysis section with a note: "Analysis unavailable — [error summary]." Do not block the rest of the flow. The user can re-run the specific analysis later.
- **No analyses triggered:** Normal case for lightweight specs. State the reason and proceed directly to Phase 3 review.
- **All conflicts unresolved:** If the user defers all conflict decisions, write them to the Open Questions section. The spec review will flag them as unresolved.

## Model Routing

| Actor | Model | Rationale |
|---|---|---|
| Orchestrator (interactive session) | Opus | Judgment, routing, conflict resolution |
| Brainstorming Q&A | Opus (inherited) | Creative design work |
| Analysis subagents (ADR, arch, impact, deps) | Sonnet | Pattern matching against known docs |
| Scenario comparison | Sonnet | Structured evaluation |
| Spec reviewer | Sonnet | Checklist validation |

## Authority

This skill **does:**
- Orchestrate the full ideation-to-approved-spec flow
- Invoke `superpowers:brainstorming` for interactive design Q&A
- Dispatch analysis subagents conditionally based on spec content
- Merge analysis findings into the spec
- Surface conflicts with recommendations for user decision
- Run spec quality review

This skill **does not:**
- Create GitHub issues (that's `/forge-shape`)
- Write implementation plans (that's `/forge-plan`)
- Implement code
- Make final architecture decisions — it recommends, the user decides
- Skip the user approval gate under any circumstances
