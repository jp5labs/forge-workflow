---
name: forge-respond
description: Structured code review response with triage, approval gate, and execution. Fetches unresolved PR review threads, triages into Fix Now / Defer / Ignore, presents for human approval, then executes approved actions.
user-invocable: true
---

## Purpose

Provide a structured, human-in-the-loop process for responding to all review comments on a PR. Fetches unresolved review threads, triages each into an action (Fix Now, Defer, Ignore), presents the triage for human approval with override support, then executes the approved plan — fixing code, creating follow-up issues, posting replies, and resolving threads.

## Trigger

Invoke this skill when:
- A PR has received review comments that need responses
- After `/forge-review` has posted findings and you need to act on them
- When asked to respond to, address, or handle PR review feedback

## Arguments

```
/forge-respond <pr-number>
```

One required argument: the PR number. If omitted, detect the current branch's PR via `gh pr view --json number --jq .number`. Working directory for all artifacts: `tmp/forge-respond/<pr-number>/`.

## Phase 1 — Collect & Triage

### Step 1: Gather PR metadata

```bash
gh pr view <N> --json number,title,url,author,headRefName,baseRefName
```

Note the PR author login — needed to filter out self-comments.

**Note:** Resolve `{owner}/{repo}` from the working repository (the `gh api` path requires the full owner/repo slug -- obtain it via the local git remote or `forge config get repo.org`/`forge config get repo.name`).

### Step 2: Fetch unresolved review threads

```bash
gh api graphql -f query='
  query($owner: String!, $name: String!, $number: Int!) {
    repository(owner: $owner, name: $name) {
      pullRequest(number: $number) {
        reviewThreads(first: 100) {
          nodes {
            id
            isResolved
            path
            line
            comments(first: 20) {
              nodes {
                id
                databaseId
                url
                body
                author { login }
                createdAt
              }
            }
          }
        }
      }
    }
  }
' -F owner={owner} -F name={repo} -F number=<N>
```

Filter to unresolved threads only (`isResolved: false`). For each thread, extract:
- `thread_id`: the thread's `id` (used for `resolveReviewThread` mutation)
- `path`: file path the comment is on
- `line`: line number
- `reviewer`: `author.login` of the first comment (skip comments by the PR author)
- `body`: full comment text of the first non-author comment
- `comment_url`: the `url` field
- `comment_db_id`: the `databaseId` field (used for reply API)

### Step 3: Fetch formal review submissions

```bash
gh api repos/{owner}/{repo}/pulls/<N>/reviews --paginate
```

Formal reviews (submitted via `gh pr review`) contain a `body` field that may list multiple findings — especially from `/forge-review` which posts a structured review with categorized findings. Parse the review body to extract individual findings as separate triage items. Look for:
- Bulleted lists of findings with severity markers (`[blocking]`, `[non-blocking]`)
- Finding IDs (e.g., `**hardcoded-identity**`, `**no-pagination**`)
- File:line references in backticks

Each distinct finding becomes its own triage item, even if they all come from a single review submission. Skip reviews authored by the PR author.

### Step 4: Fetch PR-level comments

```bash
gh pr view <N> --json comments
```

Include comments from users other than the PR author that contain actionable review feedback. Skip bot comments, automated summaries, and delivery workflow comments. Like formal reviews, a single comment may contain multiple distinct findings (e.g., from the code-review plugin) — parse each finding as a separate triage item.

### Step 5: Triage each item

For each unresolved item, categorize using these heuristics as guidelines (apply judgment — context matters):

| Signal | Action |
|--------|--------|
| Blocking language ("must", "needs to", "this will break") | Fix Now |
| Question or request for explanation | Fix Now (reply needed) |
| Bug report with reproduction steps | Fix Now |
| Out-of-scope concern, architectural suggestion, future work | Defer |
| "nit", "minor", "optional", "consider" | Ignore |

### Step 6: Write checkpoint files

Write `tmp/forge-respond/<N>/threads.json` using the Write tool:

```json
[
  {
    "id": 1,
    "thread_id": "PRT_abc123",
    "path": "src/api.ts",
    "line": 42,
    "reviewer": "marcus",
    "body": "Full comment text...",
    "comment_url": "https://github.com/OWNER/REPO/pull/100#discussion_r123",
    "comment_db_id": 123456,
    "summary": "Missing null check on response",
    "action": "fix_now",
    "rationale": "Blocking: reviewer says 'must fix'"
  }
]
```

Write `tmp/forge-respond/<N>/triage.md` using the Write tool:

```markdown
## Review Triage — PR #<N>

| # | Action   | File:Line           | Reviewer | Summary                          | Rationale                |
|---|----------|---------------------|----------|----------------------------------|--------------------------|
| 1 | Fix Now  | src/api.ts:42       | marcus   | Missing null check on response   | Blocking: "must fix"     |
| 2 | Defer    | src/auth.ts:110     | steph    | Auth flow should support PKCE    | Out of scope for this PR |
| 3 | Ignore   | src/util.ts:7       | marcus   | Prefer const over let            | Nit, no functional diff  |
```

Present the triage table to the user in the conversation output.

## Phase 2 — Human Approval Gate

After presenting the triage table, prompt the user:

```
Review the triage above. You can:
- Approve as-is: "approve" or "lgtm"
- Override items: "1 defer", "3 fix now"
- Add notes: "2 note: make this a bug not a story"
- Multiple overrides: "1 defer, 3 fix now, 2 note: track as bug"
```

**Hard gate:** Do NOT proceed to Phase 3 until the user explicitly approves. No code changes, no replies, no thread resolutions.

### Processing overrides

Parse the user's response:
- `<id> fix now` / `<id> fix_now` — change item's action to `fix_now`
- `<id> defer` — change item's action to `defer`
- `<id> ignore` — change item's action to `ignore`
- `<id> note: <text>` — attach a note to the item (used for defer issue title or fix context)
- `approve` / `lgtm` — accept triage as-is

Apply overrides to the triage data and write `tmp/forge-respond/<N>/decisions.json` using the Write tool:

```json
[
  {
    "id": 1,
    "action": "fix_now",
    "thread_id": "PRT_abc123",
    "path": "src/api.ts",
    "line": 42,
    "reviewer": "marcus",
    "summary": "Missing null check on response",
    "body": "Full comment text...",
    "comment_url": "https://github.com/OWNER/REPO/pull/100#discussion_r123",
    "comment_db_id": 123456,
    "note": null
  }
]
```

If the user changes any items, re-present the updated table for confirmation before proceeding.

## Phase 3 — Execute Approved Actions

Read `tmp/forge-respond/<N>/decisions.json` and process each item by its action. Track results for the Phase 4 summary.

### Fix Now items

Process all Fix Now items first, then batch into a single commit.

1. For each Fix Now item:
   - Read the file at the path indicated
   - Implement the change described in the reviewer's comment
   - Use the Edit tool for modifications
2. After all fixes are implemented, commit and push:
   ```bash
   git add <changed-files> && git commit -m "fix: address review feedback on #<N>"
   ```
   Note: Do not hardcode git identity. Each bot container has pre-configured git config — rely on that.
   ```bash
   git push origin <branch>
   ```
3. For each fixed item, reply to the review thread:
   ```bash
   gh api --method POST repos/{owner}/{repo}/pulls/<N>/comments/<comment_db_id>/replies -f body="Fixed in <sha>. <brief description of change>"
   ```
4. Resolve each thread:
   ```bash
   gh api graphql -f query='mutation($threadId: ID!) { resolveReviewThread(input: { threadId: $threadId }) { thread { id isResolved } } }' -f threadId="<thread_id>"
   ```

Record: item id, commit SHA, and success/failure status.

### Defer items

For each Defer item:

1. Create a follow-up issue:
   ```bash
   gh issue create --title "<summary or user note>" --body "Follow-up from PR #<N> review.

   **Original comment:** <comment_url>
   **Reviewer:** @<reviewer>
   **Context:** <body>

   ---
   Created automatically by /forge-respond." --label "agent-suggestion"
   ```
2. Reply to the review thread:
   ```bash
   gh api --method POST repos/{owner}/{repo}/pulls/<N>/comments/<comment_db_id>/replies -f body="Tracked in #<issue-number> — <issue title>"
   ```
3. Resolve the thread:
   ```bash
   gh api graphql -f query='mutation($threadId: ID!) { resolveReviewThread(input: { threadId: $threadId }) { thread { id isResolved } } }' -f threadId="<thread_id>"
   ```

Record: item id, created issue number, and success/failure status.

### Ignore items

For each Ignore item:

1. Reply with a respectful explanation:
   ```bash
   gh api --method POST repos/{owner}/{repo}/pulls/<N>/comments/<comment_db_id>/replies -f body="<respectful explanation — e.g. 'Acknowledging the suggestion. Keeping current approach because <reason>. Happy to discuss further.'>"
   ```
2. Do **not** resolve the thread — leave it open for the reviewer to accept or push back.

Record: item id and success/failure status.

### PR-level comments (no thread)

PR-level comments (from Step 3) have no `thread_id` or `comment_db_id` — they cannot be replied to inline or resolved. For these items:

- **Fix Now:** Implement the fix. The commit itself serves as the response.
- **Defer:** Create the follow-up issue. Post a new PR comment referencing the original comment and the new issue.
- **Ignore:** Post a new PR comment referencing the original and explaining the decision.

Use `gh pr comment <N> -f body="..."` for PR-level replies since there is no thread to reply to.

### Error handling

If any reply or resolution fails, log the error (item id, action, error message) and continue with the remaining items. All failures are reported in the Phase 4 summary.

## Phase 4 — Summary

After all actions are executed, write a summary to `tmp/forge-respond/<N>/summary.md` using the Write tool:

```markdown
## Review Response Summary

**Fixed (<count>):**
- Item <id> -- `<path>:<line>` -- <summary> -- fixed in <sha>

**Deferred (<count>):**
- Item <id> -- `<path>:<line>` -- <summary> -- tracked in #<issue-number>

**Declined (<count>):**
- Item <id> -- `<path>:<line>` -- <summary> -- see thread reply

**Errors (<count>):**
- Item <id> -- <action> failed: <error message>
```

Post the summary as a PR comment:

```bash
gh pr comment <N> --body-file tmp/forge-respond/<N>/summary.md
```

This is the final step. No issue comment is posted — this is a response cycle within an existing PR, not a delivery event.
