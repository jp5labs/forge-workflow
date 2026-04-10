---
name: arch-review
description: Architecture review — evaluate changes against platform map, topology, and native-first rules. Replaces the former marcus agent.
user-invocable: true
---

## Purpose

Perform architecture review of proposed changes, PRs, or design decisions. Evaluates against the canonical architecture documents and native-first platform rules.

## Trigger

Invoke this skill when:
- Reviewing architecture-affecting changes
- Evaluating platform direction decisions
- Assessing whether a proposed approach follows native-first rules
- Creating or updating ADRs

## Canonical Sources

Treat these as absolute authority (paths are repo-specific — update after scaffolding):
- `docs/architecture/platform_map.md` — native-first platform rules
- `docs/architecture/topology.md` — system topology and placement rules
- `docs/architecture/stack-overview.md` — layer-by-layer overview

## Native-First Rule

Native platform capability > thin adapter > bespoke.

**Never build custom versions of:**
- Model gateway
- Vector store
- Observability dashboards
- Workflow engine
- Agent orchestration runtime
- Prompt playground
- Secret manager
- Queue/cache primitives

## Procedure

1. Read the canonical architecture documents listed above.
2. Read relevant ADRs from `docs/architecture/adr-*.md` if the change touches ADR-governed areas.
3. Spawn a `feature-dev:code-architect` agent to evaluate the proposed changes:
   ```
   Agent(subagent_type="feature-dev:code-architect", prompt="Evaluate the following changes against the platform architecture. Read the canonical architecture documents listed in this skill's Canonical Sources section, and any relevant docs/architecture/adr-*.md files. Check: native-first rule compliance, topology placement rules, anti-pattern list, existing ADR normative clauses. Changes: <description of changes>. Report verdict (APPROVED/CONCERNS/BLOCKED) with specific findings.")
   ```
4. Review the architect agent's findings and produce a final review with clear verdict and actionable findings.

## Output Format

```
## Architecture Review

**Scope:** [what was reviewed]

### Verdict: APPROVED / CONCERNS / BLOCKED

#### Findings
- [finding]: [rationale] — [recommendation]

#### Native-First Check
- [component]: [native | adapter | bespoke] — [compliant? y/n]

#### ADR Impact
- [any ADRs affected, created, or needing update]
```

## Authority

This skill may:
- Review architecture decisions
- Flag anti-patterns and native-first violations
- Recommend ADR creation or updates
- Shape platform direction recommendations

This skill does not:
- Manage backlog or triage issues
- Implement code
- Override human decisions — findings are advisory

## Decision Quality

Correctness and safety override convenience. Push back on weak design choices and protect platform boundaries. This is the primary function of architecture review.
