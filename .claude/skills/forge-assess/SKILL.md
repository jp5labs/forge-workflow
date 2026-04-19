---
name: forge-assess
description: Run mandatory pre-implementation assessment before coding any story or issue. Produces fit check, key risks, alternatives, recommendation, and value rating per AGENTS.md Story Collaboration Rules. Always run this before writing any implementation code.
---

## Purpose

Before any story implementation, produce a structured evaluation to confirm the story is ready to plan and implement. This is a lightweight gate — not a planning session. Run this before `/forge-plan`.

## Trigger

Run this skill when:
- Starting work on any GitHub issue
- About to implement a feature or change
- Asked to "implement" or "build" anything story-scoped
- User references an issue number without a plan already in place

## Spec Detection

Before running the assessment, check whether the issue has a linked spec:

1. Fetch the issue body: `gh issue view <number> --json body`
2. Scan the body for a line matching `Spec: <path>` (e.g. `Spec: docs/specs/2026-03-24-my-feature.md`)
3. If found: read the spec file using the `Read` tool
4. If the spec file doesn't exist at the path: log a warning ("Spec file not found at `<path>`, falling back to full assessment") and proceed with the full assessment template below

**When a `Spec:` link IS found and the file is readable**, use the [Spec Conformance Template](#spec-conformance-template) instead of the full assessment template.

**When NO `Spec:` link is found**, use the full [Assessment Template](#assessment-template) below (unchanged behavior).

---

## Spec Conformance Template

When a spec exists, produce this lighter conformance check (~2K tokens) instead of the full assessment:

---

## Spec Conformance Check: [Issue Title / #Number]

**Spec:** [path to spec file]

### Conformance
Does this issue align with the spec's design?

- [ ] Issue scope matches spec's decomposition for this work item
- [ ] Approach follows spec's architecture decisions
- [ ] No new information invalidates spec assumptions

**Verdict:** [SPEC-ALIGNED / DRIFT DETECTED — explain what diverged]

### Spec Risks — Still Valid?
Review risks identified in the spec. Confirm they still apply or note changes.

- Risk 1: [from spec] — Still valid? [yes/no — explain if changed]

### Recommendation
[PROCEED / ESCALATE (drift detected)]

Rationale: [1-2 sentences]

---

After completing the conformance check, follow the same [Posting Assessment to Issue](#posting-assessment-to-issue-automated) and [Human Approval](#human-approval--required) steps as the full assessment.

---

## Assessment Template

Produce the following assessment. Fill every section — do not skip.

---

## Pre-Implementation Assessment: [Issue Title / #Number]

### Fit Check
Does this story make technical sense? Is scope clear and bounded?

- [ ] Goal is unambiguous
- [ ] Non-goals are clear or inferrable
- [ ] Acceptance criteria are measurable
- [ ] Milestone is assigned
- [ ] Dependencies are identified

**Verdict:** [CLEAR / UNCLEAR — explain if unclear]

### Key Risks / Regressions
What could break or regress? What's the blast radius?

- Risk 1: [description] — Severity: [low/med/high]
- Risk 2: [description] — Severity: [low/med/high]

### Better Alternatives
Is there a stronger or simpler approach? Apply the native-first rule:
platform capability > thin adapter > bespoke implementation

- Alternative A: [description] — Trade-off: [pros/cons]
- Alternative B: [description] — Trade-off: [pros/cons]
- **Recommended approach:** [which option and why]

### Recommendation
[PROCEED / REVISE / DEFER]

Rationale: [1-3 sentences]

### Value Rating
[Low / Medium / High]

Justification: [1 sentence]

---

## Posting Assessment to Issue (Automated)

When an issue number is present, write the completed assessment to:

```
tmp/issue-delivery/<number>/assessment.md
```

Use the `Write` tool. A PostToolUse hook (`post-assessment-to-issue.py`) automatically detects this file path and posts the assessment as a comment on the linked GitHub issue.

- Post happens automatically when the file is written — no manual router call needed
- Write the file **before** presenting the assessment for approval — maximizes recovery value if the session drops
- If posting fails, the hook logs the error but does not block the approval flow
- If no issue number is available, skip the Write step entirely (the hook will not fire)
- Subsequent revised assessments: write to the same path — each Write triggers a new issue comment, preserving decision history

## Approval Gate

After the assessment is posted to the issue, evaluate whether to wait for human approval or auto-proceed.

### Autonomous gate check

1. **Label override:** If working on a GitHub issue, check for the `needs-human-gate` label:
   ```bash
   gh issue view <number> --json labels
   ```
   If the label is present, or the check fails (API error), go to [Human Approval](#human-approval) (supervised behavior).

2. **Mode check:** Check `CLAUDE_MODE` via `printenv CLAUDE_MODE`.
   - If not `autonomous` (supervised, unset, or unrecognized): go to [Human Approval](#human-approval).
   - If `autonomous`: evaluate guardrails below.

3. **Guardrail evaluation:** All of the following must be true to auto-proceed:
   - Fit-check verdict is **CLEAR** (not UNCLEAR)
   - Recommendation is **PROCEED** (not REVISE or DEFER)
   - No risks rated **HIGH**
   - No ADR-governed boundary overlap flagged
   - Spec conformance verdict is **SPEC-ALIGNED** (not DRIFT DETECTED), if applicable

   **All green:** Auto-proceed. Post to issue: "Assessment auto-approved (autonomous mode — all guardrails green). Proceeding to `/forge-plan`."
   Then run `/forge-plan <number>` immediately.

   **Any guardrail fires:** Halt. Post to issue: "Assessment requires human review — [specific guardrail(s) that fired]." Then wait for human approval.

   **Ambiguous evaluation** (cannot cleanly determine verdict/risk levels from the assessment output): Halt and wait for human approval.

### Human Approval

Wait for explicit human approval. Do not proceed with planning until the human has reviewed and approved the assessment.

**Escalation guardrails** that require human review:

- Fit-check verdict is **UNCLEAR**
- Any risk rated **high**
- Story touches ADR-governed boundaries
- Assessment recommends **REVISE** or **DEFER**
- Spec conformance check verdict is **DRIFT DETECTED**

When any of these guardrails are present, surface them clearly to the human and wait for explicit approval or direction to revise.

## Waiting for Approval

**Do not write any implementation code until this assessment is approved (by human or autonomous gate).**

If approved (human or auto), run `/forge-plan <number>` to enter the full planning session.

If the human asks to revise, update the assessment, re-post to the issue, and re-present for approval.

## Subagent tool discipline

When spawning system agents (Explore, Plan, general-purpose) during assessment, include the subagent prompt preamble from CLAUDE.md's "Subagent prompt preamble" section in the `prompt` parameter to ensure tool-discipline rules are followed.
