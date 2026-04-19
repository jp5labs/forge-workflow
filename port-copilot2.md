Now I have the complete picture. Let me break down every CLI usage and evaluate what stays, what goes, and what gets better.

---

# JP5 & Forge CLI Elimination Analysis

## The Core Question

The jp5 CLI and forge CLI exist because Claude Code skills can't easily:
1. Orchestrate multi-step shell workflows (approval friction per step)
2. Persist configuration (no native config system)
3. Manage Docker containers (operational tooling)
4. Scaffold files consistently (one-time setup)

Copilot CLI changes the equation on every one of these.

---

## JP5 CLI: Command-by-Command Verdict

### `jp5 deliver init` — **Eliminate**

**What it does:** Creates two template files:
```
tmp/issue-delivery/<N>/pr-body.md
tmp/issue-delivery/<N>/issue-comment.md
```

**Why it exists as CLI:** Avoids the Read-before-Write dance in Claude Code's Write tool and provides a consistent template.

**Copilot CLI replacement:** Two `create` (Write) tool calls inline in the skill. Copilot CLI's `create` tool doesn't require reading first.

```markdown
# In forge-start skill, Step 4 becomes:

create("tmp/issue-delivery/<N>/pr-body.md", """## Summary
<1-3 bullet points>

## Test plan
- [ ] ...
""")

create("tmp/issue-delivery/<N>/issue-comment.md", """## Delivery

**PR:** <replace-with-pr-link>
**Branch:** issue-<N>-<slug>

## Changes
<summary>
""")
```

**Value lost:** Zero. The CLI was wrapping two file creates.

---

### `jp5 deliver run` — **Eliminate, inline the logic**

**What it does (5 steps):**
1. `git commit -m "<message>"` (staged changes only)
2. `git push origin <branch>`
3. `gh pr create --title "<title>" --body-file <path>`
4. `gh issue comment <N> --body-file <path>`
5. Scope enforcement: blocks mixed policy/ops commits

**Why it exists as CLI:** Orchestrating 4 shell commands with approval friction per command is painful. The CLI bundles them into one approved command. It also enforces commit scope rules.

**Copilot CLI replacement:** The first four steps become direct tool calls:

```
# Step 1: git commit (bash — one approval at most)
bash("git commit -m 'feat: add retrieval caching'")

# Step 2: git push (bash)
bash("git push -u origin issue-153-retrieval-topology")

# Step 3: PR creation (GitHub MCP — no approval needed)
github-mcp-server-create-pull-request(
  owner: "jp5labs",
  repo: "forge-workflow",
  title: "feat: add retrieval caching",
  body: <read from tmp/issue-delivery/153/pr-body.md>,
  head: "issue-153-retrieval-topology",
  base: "main"
)

# Step 4: Issue comment (GitHub MCP — no approval needed)
github-mcp-server-create-issue-comment(
  owner: "jp5labs",
  repo: "forge-workflow",
  issue_number: 153,
  body: <read from tmp/issue-delivery/153/issue-comment.md>
)
```

Steps 3 and 4 are zero-friction GitHub MCP calls. Steps 1 and 2 are git Bash calls that would need approval once regardless.

**Scope enforcement:** The commit-scope rule (policy/governance and ops/resilience in separate commits) becomes inline skill logic in forge-deliver:

```markdown
# In forge-deliver skill, before committing:

Check staged files:
- If staged files include BOTH (AGENTS.md, CLAUDE.md, docs/) AND (scripts/, .claude/)
  → Error: "Policy and ops changes must land in separate commits. Stage explicitly."
- Unless --allow-mixed-scope-commit flag was provided
```

This is ~10 lines of skill instruction. The CLI wrapper was adding no logic beyond this check.

**The skip flags** (`--skip-commit`, `--skip-push`, `--skip-pr`, `--skip-comment`) become conditional steps in the skill — "if changes are already committed, skip step 1" etc. Skills already handle this kind of conditional logic.

**`--dry-run`** becomes a skill-level check: "If dry-run mode, describe what would happen without executing." Skills naturally support this.

**Value lost:** The single-command convenience of `jp5 deliver run`. But in Copilot CLI, the git commands need 1-2 Bash approvals and the GitHub operations need zero approvals. The total friction is lower than a single `jp5 deliver run` Bash approval in Claude Code.

---

### `jp5 deliver review` — **Eliminate**

**What it does:** Posts an issue comment (no commit/push/PR).

**Copilot CLI replacement:** One GitHub MCP call:
```
github-mcp-server-create-issue-comment(owner, repo, issue_number, body)
```

**Value lost:** Zero. This was a one-liner wrapper.

---

### `jp5 pr cleanup` — **Eliminate, inline the logic**

**What it does (6 steps):**
1. `git checkout main`
2. `git pull --ff-only origin main`
3. `git branch -D <feature-branch>` (local delete)
4. `git push origin --delete <feature-branch>` (remote delete)
5. `gh issue comment <N> --body-file <path>` (optional)
6. Set project Status to Review via GraphQL (optional)

**Why it exists as CLI:** Worktree-aware logic (skips checkout when in worktree, rebases instead). Bundles 6 operations.

**Copilot CLI replacement:** The git operations are 4 Bash calls. The GitHub operations are MCP calls. The worktree detection is:

```markdown
# In forge-cleanup skill:

Detect worktree:
  bash("git rev-parse --git-dir") and bash("git rev-parse --git-common-dir")
  If they differ → in worktree, skip checkout, skip local branch delete

# Then:
bash("git checkout main")           # skip if worktree
bash("git pull --ff-only origin main")
bash("git branch -D <branch>")      # skip if worktree
bash("git push origin --delete <branch>")

# GitHub operations:
github-mcp-server-create-issue-comment(...)    # if --issue provided
github-mcp-server-graphql(...)                  # if --set-review
```

**Value lost:** The worktree-awareness logic, but it's ~5 lines of skill instruction and 2 git commands to detect.

---

### `jp5 ops issue-relations` — **Eliminate**

**What it does:** Sets "blocked-by" relationship between GitHub issues via GraphQL.

**Copilot CLI replacement:** One GitHub MCP GraphQL call:
```
github-mcp-server-graphql(
  query: "mutation { addSubIssue(input: { issueId: $parent, subIssueId: $child }) { ... } }",
  variables: { parent: "...", child: "..." }
)
```

**Value lost:** Zero. This was a GraphQL wrapper.

---

## Forge CLI: Command-by-Command Verdict

### `forge init` — **Replace with plugin installation + setup skill**

**What it does:** Scaffolds `.forge/config.yaml`, copies skill templates, Docker files, doc sections.

**In a Copilot CLI plugin world:**
- **Skills** come from the plugin itself — no scaffolding needed. `copilot plugin install` handles this.
- **Config** (`.forge/config.yaml`) can be auto-generated by a `/forge-init` skill that discovers repo identity via GitHub MCP and writes the file.
- **Docker** is out of scope (see bot management below).
- **Doc sections** (CLAUDE.md, AGENTS.md) don't apply — Copilot CLI uses different configuration mechanisms.

**Replacement:** A `forge-init` skill in the plugin that:
1. Calls `github-mcp-server-get-repository()` to discover org/repo
2. Writes minimal `.forge/config.yaml` with discovered identity
3. Done

**Value lost:** The scaffolding convenience, but plugin installation replaces 80% of it.

---

### `forge bot *` (add, list, remove, launch, stop, restart, attach, status, setup-guide) — **Eliminate entirely**

**What it does:** Manages a fleet of Claude Code agents running in Docker containers with Tailscale SSH.

**Why it doesn't apply:** This is specific to the "run Claude Code bots in Docker" deployment model. A Copilot CLI plugin runs inside Copilot CLI's own execution environment. There's no Docker container to manage, no tmux session to attach to, no Tailscale to configure.

If you want multi-bot orchestration on Copilot CLI, that's a different architecture — Copilot CLI agents are dispatched via `task`, not via Docker containers.

**Value lost:** The bot fleet management capability. But this capability is orthogonal to the delivery workflow — it's operational infrastructure, not a skill concern. If needed, it could be a separate ops tool.

---

### `forge config get/set` — **Simplify to file reads**

**What it does:** Reads/writes YAML config with dot-notation access.

**Copilot CLI replacement:** Skills read `.forge/config.yaml` directly via `view` tool. For the few config values skills actually need at runtime (repo org, repo name), there are two cleaner options:

1. **Discover at runtime:** `github-mcp-server-get-repository()` returns org/repo directly. No config file needed for this.
2. **store_memory:** Cache discovered values: `store_memory("forge.repo.org", "jp5labs")`. Persists across sessions.

The config file is still useful as a **declarative declaration of intent** (bot fleet, project board settings), but skills don't need to call a CLI to read it — they just `view(".forge/config.yaml")` and parse inline.

**Value lost:** The `forge config get "repo.org"` convenience. But `view` + inline parsing is equally simple and eliminates a CLI dependency.

---

### `forge config discover-project` — **Replace with a skill**

**What it does:** Interactively discovers GitHub Projects V2, fetches field/option IDs, writes project_board config.

**Copilot CLI replacement:** A `/forge-setup-project` skill that:
1. Calls `github-mcp-server-graphql()` to list org projects
2. Presents options to user
3. Calls `github-mcp-server-graphql()` to fetch field/option IDs
4. Writes the project_board section to `.forge/config.yaml`

This is actually cleaner as a skill because the interactive Q&A is what skills do well, and the GraphQL calls are zero-friction via MCP.

---

### `forge doctor` — **Replace with a skill**

**What it does:** Validates config, GitHub auth, Docker, bot files, doc sections.

**Copilot CLI replacement:** A `/forge-doctor` skill that:
1. `view(".forge/config.yaml")` — check exists and has required fields
2. `github-mcp-server-get-authenticated-user()` — check GitHub auth
3. Check plugin dependencies (superpowers installed?)

Docker and bot-file checks are irrelevant in the plugin model.

---

### `forge update-skills` — **Eliminate**

**What it does:** Syncs skill templates from upstream package using hash-based change detection.

**Copilot CLI replacement:** `copilot plugin update forge`. Plugin updates deliver new skill versions. Hash tracking is unnecessary — the plugin manager handles versioning.

**Value lost:** The ability to customize individual skills while tracking upstream. But in a plugin model, customization happens via forking the plugin or overlaying with repo-level skills, not by editing plugin-owned files.

---

### `forge self-update` — **Eliminate**

**What it does:** `pip install` latest forge-workflow package.

**Copilot CLI replacement:** `copilot plugin update forge`.

---

## Summary: What Gets Eliminated

| CLI Command | Verdict | Replacement |
|---|---|---|
| `jp5 deliver init` | **Eliminate** | Two `create` calls inline in forge-start skill |
| `jp5 deliver run` | **Eliminate** | 2 git Bash calls + 2 GitHub MCP calls + inline scope check |
| `jp5 deliver review` | **Eliminate** | 1 GitHub MCP call |
| `jp5 pr cleanup` | **Eliminate** | 4 git Bash calls + 1-2 GitHub MCP calls + worktree detection |
| `jp5 ops issue-relations` | **Eliminate** | 1 GitHub MCP GraphQL call |
| `forge init` | **Replace** | `/forge-init` setup skill |
| `forge bot *` (8 commands) | **Eliminate** | Not applicable to plugin deployment model |
| `forge config get/set` | **Simplify** | `view` + inline parsing, or `store_memory` |
| `forge config discover-project` | **Replace** | `/forge-setup-project` skill |
| `forge doctor` | **Replace** | `/forge-doctor` skill |
| `forge update-skills` | **Eliminate** | Plugin update mechanism |
| `forge self-update` | **Eliminate** | Plugin update mechanism |

**Total:** 18 CLI commands eliminated. Zero external CLI dependencies remain. The plugin is self-contained.

---

## What the Simplified Plugin Looks Like

### Before (Claude Code + jp5 + forge)

```
Dependencies:
  - forge-workflow (Python package, pip install)
  - jp5 CLI (Python package, pip install)  
  - superpowers plugin (Claude Code plugin)
  - gh CLI (GitHub CLI, brew install)
  - Docker (for bot fleet)
  - Tailscale (for bot SSH)
  - ruff (Python linter)
  - tmux (inside containers)

Config files:
  - .forge/config.yaml
  - .forge/config.local.yaml
  - .forge/skill-hashes.json
  - .claude/settings.local.json (generated)
  - bots/<name>-identity.md (per bot)
  - bots/<name>.env (per bot)

State files:
  - tmp/.session-issue
  - tmp/.plan-issue
  - tmp/issue-delivery/<N>/*
  - tmp/forge-review/<N>/*
  - tmp/forge-respond/<N>/*
  - tmp/circuit-breaker-state/*
  - tmp/session-telemetry/*
  - tmp/usage-log.jsonl
  - /tmp/forge-approval-log.jsonl
```

### After (Copilot CLI plugin only)

```
Dependencies:
  - forge plugin (Copilot CLI plugin, one install)
  - superpowers plugin (Copilot CLI plugin, declared dependency)
  - That's it.

Config files:
  - .forge/config.yaml (minimal: org, repo, project_board)

State:
  - store_memory for session anchors (current issue, branch, mode)
  - tmp/issue-delivery/<N>/* for delivery artifacts (consumed by skills, not CLIs)
  - tmp/forge-review/<N>/* for review artifacts
  - tmp/forge-respond/<N>/* for response artifacts
  - tmp/circuit-breaker-state/* for safety state
```

### The Delivery Flow Comparison

**Before (Claude Code):**
```
forge-deliver skill
  → Bash("jp5 deliver init --issue 153")      # Needs approval
    → jp5 Python → creates 2 files
  → [implementation happens]
  → Bash("git add <files>")                     # Needs approval
  → Bash("jp5 deliver run --issue 153 ...")     # Needs approval
    → jp5 Python → git commit                   # Internal
    → jp5 Python → git push                     # Internal
    → jp5 Python → gh pr create                 # Internal → gh CLI → GitHub API
    → jp5 Python → gh issue comment             # Internal → gh CLI → GitHub API
```

**After (Copilot CLI):**
```
forge-deliver skill
  → create("tmp/issue-delivery/153/pr-body.md", ...)    # No approval (create tool)
  → create("tmp/issue-delivery/153/issue-comment.md", ...)
  → [implementation happens]
  → bash("git add <files>")                               # Approval once
  → bash("git commit -m 'feat: ...'")                     # Approval once  
  → bash("git push -u origin issue-153-...")               # Approval once
  → github-mcp-server-create-pull-request(...)             # No approval (MCP)
  → github-mcp-server-create-issue-comment(...)            # No approval (MCP)
  → store_memory("forge.last_pr", "44")                    # No approval
  → report_intent("Delivered: PR #44 for issue #153")      # No approval
```

The git operations (add, commit, push) still need Bash approvals — those are intentionally gated because they're mutations. But the GitHub operations and file operations are frictionless. The total approval count drops from 3 CLI-wrapper approvals to 3 granular git approvals, and you gain transparency — each step is visible in the tool call stream instead of hidden inside a CLI.

---

## The One Thing That's Actually Lost

The **commit scope enforcement** logic in `jp5 deliver run` is the only non-trivial piece of logic in the CLI layer. It inspects staged files and blocks commits that mix policy (AGENTS.md, CLAUDE.md, docs/) with ops (scripts/, .claude/) changes.

In the plugin model, this becomes either:

1. **Inline skill logic** — The forge-deliver skill checks `bash("git diff --cached --name-only")` and evaluates the file list before committing. ~10 lines of skill instruction.

2. **A pre-commit hook** — A Python hook in `pre_tool_use(bash)` that intercepts `git commit` commands, checks staged files, and blocks mixed-scope commits. This is arguably cleaner because it enforces the rule regardless of which skill or manual action triggers the commit.

Option 2 is the Copilot-native approach — it moves the enforcement from a CLI wrapper to a safety hook, which is where policy enforcement belongs.

---

## Net Assessment

| Question | Answer |
|---|---|
| Does jp5 CLI add value on Copilot CLI? | **No.** Every jp5 command decomposes into git Bash calls + GitHub MCP calls that are equally or less friction in Copilot CLI. |
| Does forge CLI add value on Copilot CLI? | **No.** Plugin installation replaces init/update-skills/self-update. Bot management is orthogonal. Config is simpler. Doctor becomes a skill. |
| What's the total dependency reduction? | 2 Python CLI packages + gh CLI + Docker + Tailscale + tmux + ruff → **zero external dependencies** |
| What logic must be preserved? | Commit scope enforcement (~10 lines), worktree detection (~5 lines), delivery template content. All inline in skills or hooks. |
| Is anything harder without the CLIs? | No. GitHub MCP makes the GitHub operations *easier*. `store_memory` makes state management *easier*. `report_intent` adds visibility that didn't exist. |

The CLIs were solving Claude Code's approval friction problem. Copilot CLI doesn't have that problem for GitHub operations, so the CLIs become overhead rather than enablers.