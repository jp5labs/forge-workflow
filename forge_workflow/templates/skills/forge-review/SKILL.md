---
name: forge-review
description: Execute tiered PR reviews (Quick/Standard/Deep) with auto-detection. Quick = deterministic checks only. Standard = deterministic + code-review plugin. Deep = Standard + feature-dev security reviewer.
user-invocable: true
---

## Purpose

Conduct structured, tiered PR reviews using only pre-approved tools (`gh` CLI, Read, Write, Edit, Agent, Skill). Review depth scales with PR complexity — trivial changes get fast deterministic checks, complex changes get full multi-agent review.

## Trigger

Invoke this skill when:
- Asked to review a PR
- About to submit review feedback on a pull request
- Running architecture governance reviews

## Arguments

Parse the invocation arguments:

```
/forge-review <number>              # auto-detect tier
/forge-review <number> --quick      # force quick tier
/forge-review <number> --standard   # force standard tier
/forge-review <number> --deep       # force deep tier
```

Extract the PR number (required) and optional tier override flag. If no flag is provided, tier will be auto-detected in the Tier Detection section below.

**Note:** Resolve `{owner}/{repo}` from the working repository (the `gh api` path requires the full owner/repo slug -- obtain it via the local git remote or `forge config get repo.org`/`forge config get repo.name`).

## Step 1 — Gather PR Metadata

Gather PR metadata and file patches using pre-approved `gh` commands. This step is shared across all tiers.

### 1a: PR metadata

```bash
gh pr view <number> --json number,title,url,author,baseRefName,headRefName,additions,deletions,files,labels,reviewDecision
```

Record: `additions`, `deletions`, file list (names and paths), labels.

### 1b: File patches

```bash
gh api repos/{owner}/{repo}/pulls/<number>/files --paginate
```

### 1c: PR diff

```bash
gh pr diff <number>
```

### 1d: Query unresolved review threads

```bash
gh api graphql -f query="query(\$owner: String!, \$name: String!, \$number: Int!) { repository(owner: \$owner, name: \$name) { pullRequest(number: \$number) { reviewThreads(first: 100) { nodes { isResolved comments(first: 1) { nodes { body } } } } } } }" -F owner={owner} -F name={repo} -F number=<number>
```

Count unresolved threads. Threads starting with `[nit]`, `nit:`, `nitpick:`, or `[non-blocking]` are nitpick threads — they don't block approval. Record:
- `unresolved_blocking_count`: unresolved threads that are NOT nitpicks
- `unresolved_nitpick_count`: unresolved nitpick threads

These counts feed into Step 7a (review event logic).

### 1e: Resolve linked issue

Scan the PR body for issue link patterns (`Closes #N`, `Fixes #N`, `Resolves #N`). If found, record the linked issue number.

If no pattern is found in the body, also check:

```bash
gh pr view <number> --json closingIssuesReferences --jq '.closingIssuesReferences[].number'
```

Record: `linked_issue_number` (first match, or null if none found).

## Step 2 — Tier Detection

If a tier override flag was provided (`--quick`, `--standard`, `--deep`), use that tier. Otherwise, auto-detect from the PR metadata gathered in Step 1.

### Auto-detection rules

Evaluate in this order — DEEP first so human escalation labels are never silently overridden:

**DEEP** — if ANY of:
- Labels include any of: `security`, `architecture`, `track-platform`
- Any changed file matches: `docker/*`, `Dockerfile*`, `scripts/*.sh`, `ai-stack/**/*.py`, `*.tf`, `*.tfvars`
- `additions + deletions > 300`
- 10 or more files changed

**QUICK** — if ALL of:
- `additions + deletions <= 20`
- Every changed file matches one of: `*.md`, `*.yml`, `*.yaml`, `*.json`, `*.toml`, `*.txt`, `.claude/*`, `docs/*`, `.github/*`

**STANDARD** — everything else.

### Log the tier

Record the detected (or overridden) tier in `tmp/forge-review/<number>/brief.md` along with the PR metadata summary. Use the Write tool:

```markdown
# Review Brief — PR #<number>

**Title:** <title>
**Author:** <author>
**Tier:** <quick|standard|deep> (<auto-detected|manual override>)
**Files changed:** <count> (+<additions>, -<deletions>)

## Changed Files
<bulleted list of file paths>
```

## Step 3 — Spec Detection and Validation

Skip this step entirely if `linked_issue_number` is null (no linked issue found).

### 3a: Detect spec link

Fetch the linked issue body:

```bash
gh issue view <linked_issue_number> --json body
```

Scan the body for a line matching `Spec: <path>` (e.g. `Spec: docs/specs/2026-03-24-my-feature.md`).

If no spec link found → skip to Step 4. Log: "No spec link in linked issue — standard review."

### 3b: Read the spec

Read the spec file using the Read tool. If the file doesn't exist at the path, log a warning ("Spec file not found at `<path>`, skipping spec validation") and skip to Step 4.

Extract from the spec:
- Design decisions (from `## Design` / `## Decision` sections)
- Stated constraints (from `### Constraints` section)
- Scope boundaries (from the linked issue's acceptance criteria, already fetched)

### 3c: Spec-validation review

Using the spec content and the PR diff (from Step 1c), evaluate:

1. **Design conformance:** Does the implementation match the spec's design decisions? Flag divergences where the code takes a different approach than the spec prescribed.
2. **Constraint compliance:** Are the spec's stated constraints respected? Check each constraint from the spec against the implementation.
3. **Scope check:** Is the PR's scope within the linked issue's boundaries? Flag files or changes that appear outside the issue's acceptance criteria.

Produce findings with `source: spec-validation`. Severity is `blocking` for design divergence or constraint violations, `non-blocking` for scope concerns. Each finding records the same fields as deterministic findings: `source`, `severity`, `id`, `file_path`, `line_number`, `evidence`, `impact`, `suggested_fix`.

Finding IDs: `spec-design-divergence`, `spec-constraint-violation`, `spec-scope-creep`.

### 3d: Conditional analysis triggers

Check the spec file for analysis sections with substantive content (not empty, not "N/A", not "None"):

- If `### Constraints (from ADR check)` contains substantive content → invoke `/adr-check` via Skill tool with a summary of the PR's changes
- If `### Architecture Alignment (from arch review)` contains substantive content → invoke `/arch-review` via Skill tool with a summary of the PR's changes

These two can be dispatched in parallel if both are triggered.

Findings from `/adr-check` and `/arch-review` are recorded with `source: adr-check` and `source: arch-review` respectively, and join the finding pool.

### 3e: No-spec fallback

When no spec is detected (Step 3a found nothing), the entire Step 3 is skipped. Review behavior is completely unchanged — the remaining steps proceed exactly as before.

## Step 4 — Deterministic Checks

Run these checks in-context (no agent spawns). Shared across all tiers.

### 4a: missing-tests

If any runtime `.py` files under `ai-stack/rag-min/` were changed, check whether corresponding `tests/test_*.py` files were also changed. Flag each `.py` file without a matching test change.

Severity: `non-blocking`. ID: `missing-tests`.

### 4b: md-inline-code-balance

For each added line in `*.md` files, count backtick (`` ` ``) characters. Flag lines with an odd count (broken inline code).

Severity: `non-blocking`. ID: `md-backtick-balance`.

### 4c: referenced-path-exists

Scan added lines for inline code references that look like repo paths (e.g., `` `src/foo/bar.py` ``). Use Glob to verify each path exists. Flag paths that don't resolve.

Severity: `non-blocking`. ID: `broken-path-ref`.

Collect all findings. Each finding records: `source` (`deterministic`), `severity`, `id`, `file_path`, `line_number`, `evidence`, `impact`, `suggested_fix`.

## Step 5 — Tier-Specific Execution

Execute the review pipeline appropriate to the detected tier.

### Quick tier

No additional steps. Proceed directly to Step 6 (Post Inline Comments).

### Standard tier

Invoke the `code-review:code-review` skill:

```
Skill(skill="code-review:code-review", args="<number>")
```

This plugin runs its own multi-agent pipeline and **posts its own comment directly on the PR**. Do not re-post its findings.

If the `code-review:code-review` skill is unavailable, skip and note "code-review plugin unavailable" in the review draft.

Proceed to Step 6 (Post Inline Comments).

### Deep tier

Run the code-review plugin and feature-dev agent **in parallel** (single message with both tool calls) — they have no data dependencies.

#### 5a: Code-review plugin

Same as Standard tier — invoke `code-review:code-review`. Same unavailability handling.

#### 5b: Feature-dev code reviewer

Spawn one agent (concurrently with 5a):

```
Agent(subagent_type="feature-dev:code-reviewer", prompt="
Review PR #<number> for the the target repository.

Changed files:
<list from brief>

Read these files from the repository and review for:
- Security vulnerabilities (injection, auth bypass, secrets exposure, SSRF)
- Logic bugs and race conditions
- Shell scripting issues (unquoted variables, missing error handling)
- Docker best practices (layer caching, multi-stage builds, privilege escalation)
- Error handling gaps and silent failures

Report only HIGH-CONFIDENCE findings. For each finding, output a line in this exact format:
FINDING|<severity>|<file_path>|<line_number>|<short_id>|<evidence>|<impact>|<suggested_fix>

Where severity is 'blocking' or 'non-blocking'.
Use 0 for line_number if you cannot determine the exact line.
Do not use pipe characters within field values.

After all FINDING lines, provide a brief summary assessment.
")
```

Parse `FINDING|...|...|...|...|...|...|...` lines from the agent result. Each parsed finding records: `source` (`code-reviewer`), `severity`, `file_path`, `line_number`, `id`, `evidence`, `impact`, `suggested_fix`.

If the agent fails or times out, note in the review draft and continue.

Proceed to Step 6 (Post Inline Comments).

## Step 6 — Post Inline Comments

Post each finding (deterministic + spec-validation + agent) as an individual inline PR comment. The code-review plugin posts its own comment — do not re-post plugin findings.

For each finding with a valid `file_path` and `line_number > 0`:

```bash
gh pr comment <number> --body "**[<source>]** [<severity>] **<id>** — <evidence>

Impact: <impact>
Suggested fix: <suggested_fix>"
```

Source labels:
- `deterministic` — from in-context checks (all tiers)
- `spec-validation` — from spec conformance check (when spec exists)
- `adr-check` — from ADR compliance check (when spec has ADR constraints)
- `arch-review` — from architecture review (when spec has arch concerns)
- `code-reviewer` — from feature-dev:code-reviewer agent (deep tier only)

Findings where `line_number` is 0 or the file is not in the diff are **unanchorable** — collect these for inclusion in the formal review body instead.

Track the count of inline comments posted.

## Step 7 — Submit Formal Review

### 7a: Determine review event

- Any `blocking` finding from any source → `REQUEST_CHANGES`
- `unresolved_blocking_count > 0` from Step 1d (prior review threads still open) → `REQUEST_CHANGES`
- Only `non-blocking` findings or only unresolved nitpick threads → `COMMENT`
- No findings from any source AND no unresolved threads → `APPROVE`

### 7b: Write review draft

Write `tmp/forge-review/<number>/review-draft.md` using the Write tool:

```markdown
## Review: <APPROVE|COMMENT|REQUEST_CHANGES> (PR #<N>)

**Tier:** <quick|standard|deep> (<auto-detected|manual override>)
**Files changed:** <count> (+<additions>, -<deletions>)

### Findings

#### Deterministic
- [<severity>] **<id>** (`<file>:<line>`) — <evidence>
<or "None.">

#### Spec Validation
- [<severity>] **<id>** (`<file>:<line>`) — <evidence>
<or "No spec linked." or "Spec-aligned — no findings.">

#### ADR Check (spec-triggered)
- <findings>
<or "N/A — no ADR constraints in spec." or "N/A — no spec linked.">

#### Architecture Review (spec-triggered)
- <findings>
<or "N/A — no arch concerns in spec." or "N/A — no spec linked.">

#### Code-review plugin
Posted separately as PR comment (standard/deep only).

#### Code-reviewer (deep only)
- [<severity>] **<id>** (`<file>:<line>`) — <evidence>
<or "None." or "N/A — quick/standard tier">

### Unanchored Findings
<any findings that couldn't be mapped to a file:line in the diff, or "None.">

### Assessment
<1-2 sentence overall assessment>
```

The per-finding lines in the formal review body are essential for `/forge-respond` integration. forge-respond Step 3 parses the review body to extract individual findings as triage items. Each finding must include severity markers (`[blocking]`, `[non-blocking]`), finding IDs, and `file:line` references in backticks.

### 7c: Submit the review

```bash
gh pr review <number> --comment --body-file tmp/forge-review/<number>/review-draft.md
```

Or with `--approve` / `--request-changes` as appropriate.

**Self-authored PR handling:** If the PR author matches the active `gh` user (check with `gh auth status`), APPROVE and REQUEST_CHANGES require a different bot account:

```bash
gh auth switch -u <review-bot-account>
gh pr review <number> --approve --body-file tmp/forge-review/<number>/review-draft.md
gh auth switch -u <original-user>
```

If the bot account is unavailable, downgrade to `--comment`.

## Design Trade-offs

**`superpowers:code-reviewer` removed from all tiers.** This agent covered architecture alignment, DRY, separation of concerns, backward compatibility, and production readiness. Its coverage overlaps substantially with the code-review plugin (CLAUDE.md compliance, code quality) and feature-dev reviewer (error handling, testing). The trade-off: architecture and quality-of-design review is no longer automatic for non-spec PRs. For those PRs, use `/adr-check` or `/arch-review` explicitly. When a spec exists with ADR constraints or architecture alignment findings, Step 3 triggers these automatically.

## Review Considerations

- Full code review: architecture compliance, implementation correctness, code quality, security, anti-patterns, line-level findings
- Check implementation quality, script quality, and validation
- Verify scope and acceptance criteria alignment
- Use `/adr-check` skill for ADR compliance when changes touch architecture-governed code

## GitHub as the Review Record

Submitted PR reviews are the **permanent, session-independent record** of reviewer findings. Always submit a formal review via Step 7 — do not leave findings only in local draft files or chat.

When a review requests changes and the author implements fixes, post a follow-up review comment acknowledging what was addressed:

```bash
gh pr comment <number> --body "Fixed in commit <sha>: <explanation>"
```

## CLI Reference

The `jp5 pr` command group provides the same functionality: `jp5 pr review`, `jp5 pr submit`, and `jp5 pr cleanup`. Use `--dry-run` for testing.
