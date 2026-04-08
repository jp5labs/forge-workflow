---
name: forge-shape
description: Shape GitHub issues with clear scope, acceptance criteria, and milestone structure. Supports --from-spec mode to decompose approved specs into vertical-slice issue sets.
user-invocable: true
---

## Purpose

Shape and refine GitHub issues into well-scoped, actionable work items with clear acceptance criteria. Handles issue creation, backlog structuring, milestone organization, scope clarification, and spec-to-issue decomposition.

## Trigger

Invoke this skill when:
- Creating new GitHub issues
- Refining existing issues that lack clear scope or acceptance criteria
- Structuring milestones or organizing backlog
- Splitting or merging issues
- Clarifying scope and dependencies
- Decomposing an approved spec into GitHub issues (`--from-spec`)

## Arguments

```
/forge-shape                        # interactive — create or refine issues
/forge-shape --from-spec <path>     # decompose a spec file into issues
```

## Procedure

### Mode: `--from-spec <path>` (spec decomposition)

Use this mode when an approved spec file exists and needs to be decomposed into trackable GitHub issues.

#### Step 1 — Read and validate the spec

1. Read the spec file at `<path>`.
2. Validate it has the required sections: Problem, Decision, Design (at minimum).
3. Check `Status:` field — must be `Approved` or `Draft` (warn if Draft, halt if `Implemented`).
4. Extract the `Milestone:` field from the spec frontmatter — this will be assigned to all created issues.
5. If the spec already has a `Spec Issue: #<number>`, warn the user that issues may already exist and confirm before proceeding.

#### Step 2 — Identify vertical slices

Parse the spec's Design section (Architecture, Components, Data Flow subsections) and identify natural work boundaries. Each slice must be:

- **Vertical:** Includes its own testing — not a horizontal layer like "add tests" or "write docs"
- **Independent where possible:** Can be implemented and shipped without waiting for other slices (unless a true dependency exists)
- **Testable:** Has clear, specific acceptance criteria derivable from the spec

Decomposition heuristics:
- Independent components → separate issues
- Sequential dependencies → ordered issues with blocks/blocked-by relationships
- A single component with multiple concerns → one issue (don't over-split)
- Verification section items → distribute into the relevant slice's AC, not a separate issue

Present the proposed decomposition to the user before creating anything:
```
Proposed decomposition of <spec title>:

  1. <Slice title> — <one-line summary>
     AC: <bullet list>
     Depends on: (none | slice N)

  2. <Slice title> — <one-line summary>
     AC: <bullet list>
     Depends on: (none | slice N)

  ...

Milestone: <milestone from spec>
```

#### Autonomous gate check (--from-spec mode only)

Before waiting for user approval, evaluate the gate bypass:

1. **Label override:** If a spec issue number is known, check for the `needs-human-gate` label:
   ```bash
   gh issue view <spec-issue-number> --json labels
   ```
   If the label is present, or the check fails (API error), wait for user approval (supervised behavior).

2. **Mode check:** Check `CLAUDE_MODE` via `printenv CLAUDE_MODE`.
   - If `autonomous` **and** this is `--from-spec` mode: auto-approve the decomposition and proceed to issue creation. Post a brief note: "Decomposition auto-approved (autonomous mode, spec-backed)."
   - If `autonomous` but **not** `--from-spec` (interactive shaping): wait for user approval — interactive shaping requires human judgment about what to build.
   - If `supervised`, unset, or unrecognized: wait for user approval.

#### Step 3 — Create the spec issue (parent)

1. Write the spec issue body to a temp file using the `Write` tool:
   ```markdown
   ## Spec

   This issue tracks implementation of the **<spec title>** spec.

   **Spec file:** `<path>`

   ## Sub-Issues

   Created by `/forge-shape --from-spec`. See linked sub-issues below.

   ## Acceptance Criteria

   - [ ] All sub-issues completed and merged
   - [ ] Spec file updated with `Status: Implemented`
   ```

2. Create the issue:
   ```bash
   gh issue create --title "Spec: <spec title>" --label <track-label> --milestone "<milestone>" --body-file tmp/spec-issue-body.md
   ```

3. Set the issue type to `Spec` via GraphQL (the `gh issue create` CLI doesn't support `--type` yet). Resolve `{owner}/{repo}` from the working repository (the `gh api` path requires the full owner/repo slug -- obtain it via the local git remote or `forge config get repo.org`/`forge config get repo.name`).
   First, get the issue node ID from the issue number:
   ```bash
   gh api graphql -f query='{ repository(owner: "{owner}", name: "{repo}") { issue(number: <N>) { id } } }'
   ```
   Process the JSON response in-context to extract the `id` value (do not pipe to `jq` or use `${}` — both violate CLAUDE.md shell rules). Then use the extracted ID as a literal in the mutation:
   ```bash
   gh api graphql -f query='mutation { updateIssue(input: { id: "<issue-node-id>", issueTypeId: "IT_kwDOD9YC8c4B6y-u" }) { issue { id } } }'
   ```

4. Add to project #4 and set Track/Lane fields (same GraphQL procedure as standard issue creation — see project field IDs below).

5. Capture the spec issue number for sub-issue creation.

#### Step 4 — Create sub-issues

For each vertical slice approved in Step 2:

1. Write the sub-issue body to a temp file using the `Write` tool:
   ```markdown
   ## Context

   Part of Spec: <spec title> (spec issue #<spec-issue-number>)
   Spec: <path>

   ## What

   <description of this slice>

   ## Acceptance Criteria

   - [ ] <criterion 1>
   - [ ] <criterion 2>
   ...

   ## Scope

   **In:** <what this issue covers>
   **Out:** <what's explicitly excluded — handled by other slices>
   ```

2. Create the issue:
   ```bash
   gh issue create --title "<slice title>" --label <type-label> --label <track-label> --milestone "<milestone>" --body-file tmp/sub-issue-body.md
   ```

3. Add to project #4 and set Track/Lane fields.

4. Record the created issue number for dependency wiring.

#### Step 5 — Wire dependencies

For each sub-issue that depends on another sub-issue (identified in Step 2):

```bash
jp5 ops issue-relations --action set --issue <downstream> --blocked-by <upstream>
```

Also wire each sub-issue as a child of the spec issue if the repo supports sub-issues, or note the parent-child relationship in the spec issue body by editing it to list all sub-issue numbers.

#### Step 6 — Update the spec file

Add the `Spec Issue:` field to the spec file's frontmatter using the `Edit` tool:

```markdown
**Spec Issue:** #<spec-issue-number>
```

Also update the spec's `Status:` from `Approved` to `In Progress` if it was `Approved`.

#### Step 7 — Summary

Print a summary of all created issues:

```
Spec decomposition complete:

  Spec Issue: #<number> — Spec: <title>
  Sub-Issues:
    #<n1> — <title> (no dependencies)
    #<n2> — <title> (blocked by #<n1>)
    #<n3> — <title> (no dependencies)

  Milestone: <milestone>
  Spec file updated: <path>
```

---

### Mode: Standard (no flags) — create or refine issues

#### For new issues
1. Gather context from the user about what needs to be done and why.
2. Check existing open issues for overlap (`gh issue list`).
3. Draft the issue with:
   - Clear title (action-oriented, concise)
   - Problem/context section
   - Acceptance criteria (testable, specific)
   - Scope boundaries (what's in, what's explicitly out)
   - Dependencies (link to blocking/blocked-by issues if applicable)
4. Create the issue via `gh issue create --body-file`.
5. If project board is enabled (`forge config get project_board.enabled`), add to project and set fields:
   - Read project ID and field IDs from `.forge/config.yaml` (`project_board.project_id`, `project_board.fields.*`, `project_board.options.*`)
   - Add to project via GraphQL `addProjectV2ItemById`
   - Set Track and Lane fields via `updateProjectV2ItemFieldValue` using config-resolved IDs
   - If project board not enabled, skip this step silently
6. Set dependency relationships if needed via `jp5 ops issue-relations`.

#### For refining existing issues
1. Read the issue: `gh issue view <number> --json body,comments,labels,milestone`.
2. Identify gaps: missing acceptance criteria, vague scope, unlabeled, no milestone.
3. Propose specific improvements.
4. Update the issue after user approval.

#### For backlog/milestone work
1. List issues in the target milestone or label group.
2. Assess: scope clarity, dependency completeness, ordering.
3. Propose restructuring with rationale.

## Issue Quality Standards

Every shaped issue should have:
- **Title:** Action verb + specific noun (e.g., "Add retry logic to embedding service")
- **Acceptance criteria:** 2-5 testable items
- **Scope:** What's in and what's explicitly out
- **Labels:** At minimum, a type label
- **Dependencies:** Native GitHub relationships, not text links

## Authority

This skill may:
- Create and refine GitHub issues
- Restructure backlog items
- Organize milestones
- Clarify scope and acceptance criteria
- Split or merge issues
- Coordinate across architecture and engineering concerns
- Decompose specs into issue sets (with user approval at each gate)

This skill does not:
- Dictate architecture decisions (escalate to `/arch-review`)
- Implement code
- Close issues without verifying delivery outcomes

## Follow-on Issue Hygiene

Before creating agent-suggested issues, review open issues for overlap. If overlap exists, link existing issue(s) instead of creating a duplicate.
