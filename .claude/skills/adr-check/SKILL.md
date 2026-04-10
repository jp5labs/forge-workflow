---
name: adr-check
description: Validate proposed changes against existing ADRs and the platform map. Invoke before architecture-affecting PRs or when reviewing changes that touch ADR-governed boundaries.
user-invocable: true
---

## Purpose

Check proposed changes for compliance with Architecture Decision Records and the native-first platform map. Replaces the former `adr-guardian` agent with a lighter-weight skill.

## Trigger

Invoke this skill when:
- Reviewing a PR that touches architecture-governed code
- Implementing a story with ADR dependencies
- Checking compliance before delivery

## Procedure

1. Read all ADRs:
   ```
   docs/architecture/adr-*.md
   ```

2. Read the platform map:
   ```
   docs/architecture/ai_stack_platform_map.md
   ```

3. Identify the proposed changes — either from staged git diff, a PR diff, or a description provided by the user.

4. Spawn a `feature-dev:code-architect` agent to cross-reference the changes against all ADRs:
   ```
   Agent(subagent_type="feature-dev:code-architect", prompt="Read all docs/architecture/adr-*.md files and docs/architecture/ai_stack_platform_map.md. Evaluate the following changes for ADR compliance. Flag any normative clause violations (must/must not/required/denied/always/never). Also check platform map anti-patterns. Changes: <description>. Return structured findings per ADR with verdict PASS/FAIL.")
   ```

5. Review the architect agent's findings and evaluate every normative clause against the changes. Normative language to flag:
   - `must` / `must not`
   - `required` / `required to`
   - `denied` / `not allowed` / `prohibited`
   - `always` / `never` (when used as rules)

6. Check platform map anti-patterns: do not build custom versions of model gateway, vector store, observability dashboards, workflow engine, agent orchestration runtime, prompt playground, secret manager, queue/cache primitives.

## Output Format

```
## ADR Compliance Report

**Changes reviewed:** [brief description]

### Verdict: PASS / FAIL

#### Violations (if FAIL)
- [ADR reference]: [specific normative clause] — [how the change conflicts]

#### Warnings (non-normative concerns)
- [optional: flag anything that drifts from ADR intent without explicit violation]

#### Notes
- [any ADRs where status is Proposed that may be relevant]
```

## Escalation

If violations are found, output the full report and wait for the human operator to decide whether to:
- Revise the proposed change
- Update the ADR with new rationale
- Accept with documented exception
