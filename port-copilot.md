Now I have the complete picture: the forge-* skills, the superpowers skills underneath, the infrastructure layer (hooks, config, CLI, Docker, state management), and the Copilot CLI's capabilities. Let me design the architecture.

---

# Forge-on-Copilot-CLI: Architecture Design

## The Three Layers to Migrate

```
┌─────────────────────────────────────────────┐
│  Layer 3: Infrastructure                     │
│  Hooks, config, Docker, state, CLI           │
├─────────────────────────────────────────────┤
│  Layer 2: Forge Skills                       │
│  forge-discover, forge-spec, forge-plan...   │
├─────────────────────────────────────────────┤
│  Layer 1: Superpowers                        │
│  brainstorming, writing-plans, SDD, TDD...   │
└─────────────────────────────────────────────┘
```

Layer 1 (superpowers) already works on Copilot CLI — first-party support, tool mapping included. No work needed.

Layer 2 (forge skills) needs adaptation — tool names, subagent dispatch patterns, and GitHub integration approach change.

Layer 3 (infrastructure) needs the most rework — hooks, settings generation, state management, and Docker all have Copilot CLI-native equivalents that are cleaner than direct ports.

---

## 1. Plugin Structure

Package forge as a **single Copilot CLI plugin** that depends on superpowers:

```
forge-workflow-copilot/
├── plugin.json                    # Plugin manifest
├── package.json                   # Version, dependencies
│
├── skills/                        # All forge-* skills (auto-discovered)
│   ├── forge-discover/SKILL.md
│   ├── forge-spec/SKILL.md
│   ├── forge-shape/SKILL.md
│   ├── forge-assess/SKILL.md
│   ├── forge-plan/SKILL.md
│   ├── forge-start/SKILL.md
│   ├── forge-deliver/SKILL.md
│   ├── forge-review/SKILL.md
│   ├── forge-respond/SKILL.md
│   ├── forge-cleanup/SKILL.md
│   ├── forge-resume/SKILL.md
│   ├── adr-check/SKILL.md
│   ├── arch-review/SKILL.md
│   ├── impact-analysis/SKILL.md
│   ├── dependency-graph/SKILL.md
│   ├── scenario-compare/SKILL.md
│   ├── approval-hygiene/SKILL.md
│   └── token-hygiene/SKILL.md
│
├── agents/                        # Named agents (auto-discovered)
│   ├── code-architect.md          # feature-dev:code-architect equivalent
│   ├── code-reviewer.md           # feature-dev:code-reviewer equivalent
│   └── code-explorer.md           # feature-dev:code-explorer equivalent
│
├── hooks/                         # Copilot CLI hook definitions
│   ├── hooks.json
│   └── scripts/
│       ├── safety/                # Direct ports (language-agnostic)
│       │   ├── block-commit-to-main.py
│       │   ├── destructive-git-halt.py
│       │   ├── dangerous-command-halt.py
│       │   ├── secret-detection.py
│       │   ├── secret-file-scanner.py
│       │   └── sequential-failure-breaker.py
│       └── automation/            # Adapted for Copilot patterns
│           ├── post-assessment-to-issue.py
│           └── session-telemetry.py
│
├── references/
│   └── claude-to-copilot.md       # Forge-specific tool mapping additions
│
└── config/
    └── schema.yaml                # .forge/config.yaml schema
```

**`plugin.json` manifest:**

```json
{
  "name": "forge",
  "version": "1.0.0",
  "description": "Structured delivery workflow with safety gates",
  "dependencies": ["superpowers"],
  "skills_dir": "skills",
  "agents_dir": "agents",
  "hooks": "hooks/hooks.json"
}
```

The `"dependencies": ["superpowers"]` declaration is the key — it tells Copilot CLI that superpowers must be installed, making `skill("superpowers:brainstorming")` and `skill("superpowers:writing-plans")` available to forge skills.

---

## 2. The Five Copilot-Native Improvements

These are places where Copilot CLI's native features replace Claude Code workarounds with cleaner solutions:

### 2a. GitHub MCP Tools Replace `gh` CLI

This is the single biggest improvement. Today, forge-* skills run `gh` commands via `Bash`, which:
- Requires shell approval prompts (or allowlist entries) for every `gh` call
- Parses JSON output with `--jq` or in-context (fragile)
- Triggers compound-command-interceptor on pipes
- Can't do GraphQL without multi-line string escapes that fight shell guards

Copilot CLI has **native GitHub MCP tools** (`github-mcp-server-*`) that provide direct API access as structured tool calls — no shell, no parsing, no approvals.

**Before (Claude Code):**
```bash
# Requires Bash approval, shell escaping, jq parsing
gh issue view 153 --json title,body,comments,labels,milestone
gh api graphql -f query='mutation($threadId: ID!) { resolveReviewThread(input: { threadId: $threadId }) { thread { id isResolved } } }' -f threadId="PRT_abc123"
```

**After (Copilot CLI):**
```
# Direct structured tool call — no shell, no approval, typed response
github-mcp-server-get-issue(owner: "jp5labs", repo: "forge-workflow", issue_number: 153)
github-mcp-server-graphql(query: "mutation($threadId: ID!) { ... }", variables: { threadId: "PRT_abc123" })
```

**Impact on forge-* skills:**

| Skill | `gh` calls replaced | Benefit |
|---|---|---|
| forge-assess | `gh issue view`, `gh issue comment` | No shell approval for assessment posting |
| forge-plan | `gh issue view`, `gh issue comment`, `gh pr list` | Plan posting becomes a tool call |
| forge-start | `gh issue view`, `gh issue edit --add-assignee` | Branch setup needs zero Bash approvals for GitHub ops |
| forge-review | `gh pr view`, `gh api repos/.../pulls/.../files`, `gh pr diff`, `gh api graphql` (review threads), `gh pr review`, `gh pr comment` | The most gh-heavy skill — 7+ distinct `gh` invocations become native tool calls |
| forge-respond | `gh api graphql` (threads), `gh api --method POST` (replies), `gh issue create` (defer) | GraphQL mutations without shell escaping nightmares |
| forge-shape | `gh issue create`, `gh api graphql` (issue type, project) | Issue creation with project field setting becomes clean |
| forge-cleanup | `gh issue comment` (telemetry) | Telemetry posting without shell |
| forge-resume | `gh issue view`, `gh pr list`, `gh api` (timeline) | Context reconstruction is pure reads — all tool calls |
| forge-deliver | `jp5 deliver run` (which internally calls gh) | jp5 CLI still uses gh internally, but direct GitHub ops in skills don't |

**Not all `gh` usage moves to MCP.** The `jp5 deliver run` CLI wraps `gh` internally — that stays as Bash. But every *direct* `gh` call in skill logic becomes a GitHub MCP tool call, eliminating the approval-logger noise and compound-command friction.

### 2b. `store_memory` Replaces File-Based State Anchors

Today, forge uses temp files as session anchors:
- `tmp/.session-issue` — Current issue number for telemetry
- `tmp/.plan-issue` — Issue number for plan posting hook

These exist because Claude Code has no persistent memory. Copilot CLI does.

**Before (Claude Code):**
```python
# In forge-start skill:
# "Write the issue number to tmp/.session-issue"
# Read tmp/.session-issue first (may not exist — that's fine)
# Write the issue number using the Write tool
```

**After (Copilot CLI):**
```
store_memory(key: "forge.current_issue", value: "153")
store_memory(key: "forge.current_branch", value: "issue-153-retrieval-topology")
store_memory(key: "forge.delivery_mode", value: "standard")
```

**Impact:** Eliminates the Read-before-Write dance, the "may not exist" comments, the hook scripts that read these anchor files. Memory persists across sessions automatically, which also improves `forge-resume` — instead of reconstructing context from GitHub artifacts, check memory first.

**What stays as files:** `tmp/issue-delivery/<N>/` artifacts (assessment.md, implementation-plan.md, pr-body.md) stay as files because they're consumed by `jp5 deliver run` CLI and the content is too large for key-value memory.

### 2c. `report_intent` for Pipeline Status

Forge workflows are long. Today, the user sees tool call output scrolling by with no high-level status. Copilot CLI's `report_intent` updates a status line in the UI.

**Forge skills add status updates at each phase transition:**

```
report_intent("forge-spec: Phase 1 — Brainstorming design for retrieval-caching")
report_intent("forge-spec: Phase 2 — Running ADR + arch analysis (3 agents)")
report_intent("forge-spec: Phase 3 — Spec review")
report_intent("forge-plan: Assembling context from issue #153, assessment, spec")
report_intent("forge-plan: Writing implementation plan (5 tasks)")
report_intent("forge-start: Syncing main, creating issue-153-retrieval-topology")
report_intent("forge-deliver: Committing + pushing + opening PR")
```

This is a pure addition — no Claude Code equivalent needs replacing. Add one `report_intent` call at the start of each skill step.

### 2d. `sql` with `todos` Table for Pipeline Tracking

Today, forge skills use `TaskCreate`/`TaskUpdate` (deferred tools in Claude Code) for progress tracking. Copilot CLI's `sql` tool with the built-in `todos` table is more powerful — it supports queries, filtering, and persists across the session.

**Before (Claude Code):**
```
TaskCreate(description="Run assessment", status="in_progress")
TaskUpdate(id=1, status="completed")
```

**After (Copilot CLI):**
```sql
INSERT INTO todos (title, status, context) VALUES ('forge-assess: Pre-impl assessment', 'in_progress', '{"issue": 153, "skill": "forge-assess"}');
UPDATE todos SET status = 'completed' WHERE title LIKE 'forge-assess%';
-- Query pipeline state:
SELECT title, status FROM todos WHERE context LIKE '%"issue": 153%' ORDER BY id;
```

**Advantage:** The `sql` approach lets you query pipeline state ("what's the status of issue 153's delivery?") which is useful for `forge-resume`.

### 2e. Async Shell for Long Operations

Some forge operations take minutes (Docker builds, full test suites, `jp5 deliver run`). Today these block the session. Copilot CLI's async shell lets them run in the background.

**Before (Claude Code):**
```bash
# Blocks until complete — agent can't do anything else
jp5 deliver run --issue 153 --commit-message "feat: add caching" --pr-title "feat: add caching"
```

**After (Copilot CLI):**
```bash
# Start in background
bash(command="jp5 deliver run --issue 153 ...", async=true, session_id="deliver-153")
# Check progress
read_bash(session_id="deliver-153")
# Continue other work while delivery runs
```

**Useful for:** `forge-deliver` (commit + push + PR + comment), `forge-cleanup` (branch deletion + telemetry), and any test suite execution during `forge-review`.

---

## 3. Agent Registry

Claude Code's forge-* skills dispatch agents from the `feature-dev` plugin (`feature-dev:code-architect`, `feature-dev:code-reviewer`, `feature-dev:code-explorer`). In Copilot CLI, you register these as named agents in the forge plugin's `agents/` directory — Copilot auto-discovers them.

**`agents/code-architect.md`:**
```markdown
# Code Architect

You are an architecture evaluation agent. Your job is to analyze proposed changes
against canonical architecture documents, ADRs, platform maps, and topology rules.

## Capabilities
- Read architecture docs and ADRs
- Evaluate changes for compliance with normative clauses
- Check native-first rule compliance
- Assess topology placement
- Produce structured verdicts (APPROVED/CONCERNS/BLOCKED)

## Tool Discipline
- Use `view` for file reading (not `bash` with cat/head/tail)
- Use `grep` for content search (not `bash` with grep/rg)
- Use `glob` for file search (not `bash` with find/ls)
- Use `edit` for file modification (not `bash` with sed/awk)
- Use GitHub MCP tools for all GitHub operations (not `bash` with gh)
```

**`agents/code-reviewer.md`:**
```markdown
# Code Reviewer

You are a security-focused code review agent. Your job is to review code changes
for bugs, logic errors, security vulnerabilities, and adherence to project conventions.

## Focus Areas
- Security vulnerabilities (injection, auth bypass, secrets exposure, SSRF)
- Logic bugs and race conditions
- Shell scripting issues (unquoted variables, missing error handling)
- Docker best practices (layer caching, multi-stage builds, privilege escalation)
- Error handling gaps and silent failures

## Output Format
Report only HIGH-CONFIDENCE findings. For each finding:
FINDING|<severity>|<file_path>|<line_number>|<short_id>|<evidence>|<impact>|<suggested_fix>

Where severity is 'blocking' or 'non-blocking'.
```

**`agents/code-explorer.md`:**
```markdown
# Code Explorer

You are a codebase exploration agent. Your job is to deeply analyze existing features
by tracing execution paths, mapping architecture layers, understanding patterns and
abstractions, and documenting dependencies.

## Approach
- Map file structure and responsibilities
- Trace data flow through components
- Identify patterns, conventions, and abstractions
- Document integration points and dependencies
- Report file paths, key abstractions, and integration points

## Tool Discipline
- Use `view` for file reading
- Use `grep` for content search
- Use `glob` for file search
```

**Dispatch in skills changes from:**
```
Agent(subagent_type="feature-dev:code-architect", prompt="...")
```

**To:**
```
task(agent_type="forge:code-architect", description="ADR compliance check", message="...")
```

Copilot CLI auto-discovers `forge:code-architect` from the plugin's `agents/` directory. No manual prompt-file reading needed (unlike the Codex workaround).

---

## 4. Skill Adaptation Pattern

Each forge-* skill needs these systematic changes. Here's the translation table that applies to every skill:

### Universal Substitutions

| Claude Code Pattern | Copilot CLI Pattern | Notes |
|---|---|---|
| `gh issue view <N> --json ...` | `github-mcp-server-get-issue(...)` | Structured response, no parsing |
| `gh issue comment <N> --body-file <path>` | `github-mcp-server-create-issue-comment(...)` | Read file content, pass as `body` |
| `gh issue create --title ... --body-file ...` | `github-mcp-server-create-issue(...)` | Structured creation |
| `gh pr view <N> --json ...` | `github-mcp-server-get-pull-request(...)` | Direct PR metadata |
| `gh pr diff <N>` | `github-mcp-server-get-pull-request-diff(...)` | Clean diff without shell |
| `gh pr review <N> --comment --body-file ...` | `github-mcp-server-create-pull-request-review(...)` | No self-authored-PR workaround needed if using bot account |
| `gh api graphql -f query='...'` | `github-mcp-server-graphql(query: "...", variables: {...})` | No shell escaping for GraphQL |
| `gh api repos/.../pulls/.../files` | `github-mcp-server-list-pull-request-files(...)` | Paginated automatically |
| `Agent(subagent_type="feature-dev:X")` | `task(agent_type="forge:X")` | Named agent from plugin registry |
| `Agent(model="sonnet", ...)` | `task(model="sonnet", ...)` | Model routing preserved |
| `Agent(subagent_type="Explore")` | `task(agent_type="explore")` | Built-in agent type |
| `Skill(skill="superpowers:brainstorming")` | `skill("superpowers:brainstorming")` | Same invocation |
| `Skill(skill="forge-start")` | `skill("forge:forge-start")` | Namespaced to forge plugin |
| `Read(file_path)` | `view(file_path)` | Direct mapping |
| `Write(file_path, content)` | `create(file_path, content)` | Direct mapping |
| `Edit(file_path, old, new)` | `edit(file_path, old, new)` | Direct mapping |
| `Bash(command)` | `bash(command)` | Same |
| `printenv CLAUDE_MODE` | `printenv FORGE_MODE` | Rename env var for portability |
| `TaskCreate(...)` | `sql("INSERT INTO todos ...")` | Richer querying |
| File write to `tmp/.session-issue` | `store_memory(key: "forge.current_issue", value: "...")` | Persistent across sessions |
| File write to `tmp/.plan-issue` | `store_memory(key: "forge.plan_issue", value: "...")` | No hook file needed |

### Skill-Specific Adaptation Notes

**forge-discover** — Minimal changes. One Explore agent dispatch changes from `Agent(subagent_type="Explore")` to `task(agent_type="explore")`. The `gh issue list --search` call becomes a GitHub MCP search call.

**forge-spec** — The brainstorming invocation (`Skill(skill="superpowers:brainstorming")`) becomes `skill("superpowers:brainstorming")`. The 2-5 parallel analysis agents change from `Agent(subagent_type="feature-dev:code-architect")` to `task(agent_type="forge:code-architect")`. The spec reviewer dispatch changes similarly. Add `report_intent` at each phase transition.

**forge-shape** — The heaviest `gh` user for issue creation. All `gh issue create`, `gh api graphql` (issue type mutation, project field setting) become GitHub MCP tool calls. The `--from-spec` mode's issue creation loop becomes dramatically cleaner — no temp file writes for issue bodies, no `--body-file` pattern.

**forge-assess** — The assessment posting hook (`post-assessment-to-issue.py`) currently fires when `tmp/issue-delivery/<N>/assessment.md` is written. In Copilot CLI, two options:
1. Keep the file-write + hook pattern (works, just port the hook)
2. **Cleaner:** Post directly from the skill via `github-mcp-server-create-issue-comment(body: assessment_content)`. This eliminates the hook entirely — the skill does the posting itself, which is more transparent.

**forge-plan** — The context assembly phase (Phase 1) reads issue, assessment, spec, and dispatches an explorer. All `gh` calls become MCP calls. The `writing-plans` invocation stays the same. The plan posting (Phase 3) either uses a hook or posts directly via MCP. The execution handoff (Phase 4) invokes `skill("superpowers:subagent-driven-development")` — unchanged.

**forge-start** — Mostly `git` commands (Bash) plus `gh issue edit --add-assignee @me` (→ MCP) and `jp5 deliver init` (Bash). Replace `tmp/.session-issue` write with `store_memory`. Add `report_intent("forge-start: Creating branch issue-153-...")`.

**forge-deliver** — The `jp5 deliver run` command stays as Bash (it's a CLI tool). But consider using async shell for the delivery since it involves commit + push + PR + comment and can take 30+ seconds. Mode detection changes from `printenv CLAUDE_MODE` to `printenv FORGE_MODE`.

**forge-review** — The most complex adaptation. This skill makes 7+ distinct `gh` calls and dispatches multiple agents. All `gh pr view`, `gh api repos/.../pulls/.../files`, `gh pr diff`, `gh api graphql` (review threads), `gh pr review`, `gh pr comment` become MCP tool calls. The tier detection, deterministic checks, and spec validation stay in-context. The `code-review:code-review` plugin invocation becomes `skill("code-review:code-review")` (if that plugin is installed on Copilot CLI — if not, the forge:code-reviewer agent covers it). The deep-tier `Agent(subagent_type="feature-dev:code-reviewer")` becomes `task(agent_type="forge:code-reviewer")`.

**forge-respond** — The GraphQL thread fetching, reply posting, and thread resolution become MCP calls. The triage table, approval gate, and execution logic stay the same. Deferred issue creation becomes `github-mcp-server-create-issue(...)`. This skill benefits enormously from MCP — today it has the most complex GraphQL mutations that fight shell escaping.

**forge-cleanup** — `jp5 pr cleanup` stays as Bash. Telemetry posting becomes an MCP call. `store_memory` clears the forge session state. Approval hygiene reads `/tmp/forge-approval-log.jsonl` — this concept changes in Copilot CLI (see hooks section).

**forge-resume** — The biggest winner. Today it reconstructs context from GitHub artifacts via `gh` calls. In Copilot CLI: check `store_memory` first for cached context, then fall back to MCP calls for fresh data. The status summary and next-action suggestion stay the same.

---

## 5. Hook Migration

The 13 Claude Code hooks fall into three categories for Copilot CLI:

### Category A: Direct Port (Safety Hooks)

These hooks enforce safety invariants and port directly to Copilot CLI's hook system. The Python scripts are language-agnostic — they read tool input from stdin, return allow/block JSON on stdout. The only change is the hook registration format.

| Hook | Claude Code Event | Copilot CLI Event | Changes |
|---|---|---|---|
| block-commit-to-main | PreToolUse(Bash) | pre_tool_use(bash) | Format only |
| destructive-git-halt | PreToolUse(Bash) | pre_tool_use(bash) | Format only |
| dangerous-command-halt | PreToolUse(Bash) | pre_tool_use(bash) | Format only |
| secret-detection | UserPromptSubmit | user_prompt_submit | Format only |
| secret-file-scanner | PreToolUse(Edit\|Write) | pre_tool_use(edit\|create) | Tool name mapping |
| sequential-failure-breaker | PostToolUse(Bash) | post_tool_use(bash) | Format only |
| file-protection | PreToolUse(Edit\|Write) | pre_tool_use(edit\|create) | Tool name mapping |

### Category B: Eliminate (Replaced by Native Features)

| Hook | Why It Exists | Copilot CLI Replacement |
|---|---|---|
| shell-expansion-guard | Blocks `${}` which triggers Claude Code approval | Copilot CLI doesn't have this approval quirk — **delete** |
| compound-command-interceptor | Blocks pipes/chains that fight Claude Code approvals | Copilot CLI's `bash` is more permissive — **simplify to safety-only checks** (keep for-loop blocking, drop ergonomic guidance) |
| post-assessment-to-issue | Fires on Write to auto-post assessment | **Eliminate** — skill posts directly via GitHub MCP |
| post-plan-to-issue | Fires on ExitPlanMode to auto-post plan | **Eliminate** — no ExitPlanMode in Copilot CLI; skill posts directly via MCP |
| approval-logger | Logs permission prompts for approval-hygiene | Copilot CLI's permission model differs — **evaluate whether needed** |
| ruff-fix | Auto-runs ruff on Python writes | Port if wanted, but consider making it a CI step instead |

### Category C: Adapt (Changed Behavior)

| Hook | Adaptation |
|---|---|
| circuit-breaker-init | SessionStart → session_start. Same logic: wipe state files. |
| session-telemetry | SessionEnd → session_end. **Major improvement:** Copilot CLI may expose session token counts directly via internal APIs or session metadata, eliminating the transcript-parsing Python script. If not, port the parser but read Copilot CLI's transcript format instead of Claude Code's. |

**Copilot CLI `hooks.json`:**

```json
{
  "hooks": {
    "session_start": [
      { "command": "python hooks/scripts/safety/circuit-breaker-init.py" }
    ],
    "user_prompt_submit": [
      { "command": "python hooks/scripts/safety/secret-detection.py" }
    ],
    "pre_tool_use": {
      "bash": [
        { "command": "python hooks/scripts/safety/block-commit-to-main.py" },
        { "command": "python hooks/scripts/safety/destructive-git-halt.py" },
        { "command": "python hooks/scripts/safety/dangerous-command-halt.py" }
      ],
      "edit|create": [
        { "command": "python hooks/scripts/safety/secret-file-scanner.py" },
        { "command": "python hooks/scripts/safety/file-protection.py" }
      ]
    },
    "post_tool_use": {
      "bash": [
        { "command": "python hooks/scripts/safety/sequential-failure-breaker.py" }
      ]
    },
    "session_end": [
      { "command": "python hooks/scripts/automation/session-telemetry.py" }
    ]
  }
}
```

**Net result:** 13 hooks → 9 hooks (4 eliminated by native features).

---

## 6. What Stays the Same

Not everything changes. These components port directly:

- **`.forge/config.yaml`** — Repo identity, bot fleet, project board config. Language-agnostic YAML. Unchanged.
- **`forge` CLI** — `forge init`, `forge bot`, `forge config`, `forge doctor`. Python CLI tool. Unchanged except settings generator targets Copilot CLI format.
- **`jp5 deliver`** — The delivery CLI is a Bash command. Works identically.
- **`jp5 pr cleanup`** — Same.
- **`jp5 ops issue-relations`** — Same.
- **`tmp/issue-delivery/<N>/`** artifacts — Assessment, plan, PR body files. Consumed by `jp5 deliver run`. Unchanged.
- **`tmp/forge-review/<N>/`** artifacts — Review brief, draft. Written by skill, consumed by skill. Unchanged.
- **`tmp/forge-respond/<N>/`** artifacts — Threads, decisions, summary. Unchanged.
- **`docs/specs/`** — Spec files. Unchanged.
- **`docs/architecture/adr-*.md`** — ADRs. Unchanged.
- **Circuit breaker state files** — `tmp/circuit-breaker-state/`. Unchanged.
- **All git operations** — `git fetch`, `git checkout`, `git pull`, `git push`, etc. All Bash. Unchanged.
- **Test execution** — All Bash commands. Unchanged.
- **Superpowers skills** — All 14 skills work on Copilot CLI already. No forge changes needed for the underlying superpowers layer.

---

## 7. The Cleanest Resulting Architecture

After migration, the forge-on-Copilot-CLI architecture has these properties:

### Before (Claude Code)

```
Skill → Bash("gh api graphql ...") → Shell approval → gh CLI → GitHub API
Skill → Write("tmp/.session-issue") → Hook reads file → Bash("gh issue comment") → Shell approval → gh CLI → GitHub API  
Skill → Agent(subagent_type="feature-dev:code-architect") → Claude Code resolves from plugin registry
Skill → printenv CLAUDE_MODE → File read for mode awareness
```

### After (Copilot CLI)

```
Skill → github-mcp-server-graphql(...) → GitHub API        (direct, no shell, no approval)
Skill → github-mcp-server-create-issue-comment(...)         (inline, no hook, no file)
Skill → task(agent_type="forge:code-architect")              (auto-discovered from plugin)
Skill → store_memory("forge.current_issue", "153")           (persistent, queryable)
Skill → report_intent("forge-plan: Writing implementation plan")  (UI status)
```

### Token Impact Changes

| Category | Claude Code | Copilot CLI | Reason |
|---|---|---|---|
| GitHub operations | High (Bash + gh + parsing) | Lower | MCP tool calls return structured data — no shell overhead, no JSON parsing in context |
| State management | Medium (Read + Write dance) | Lower | `store_memory` is one call vs Read-then-Write |
| Approval friction | High (approval-logger captures 20-50 re-approvals) | Lower | GitHub MCP calls need no shell approval; eliminated hooks reduce total hook execution |
| Hook overhead | 13 hooks × evaluation per event | 9 hooks | 4 hooks eliminated, remaining hooks are safety-only (fast) |
| Agent dispatch | Same | Same | `task` maps 1:1 to `Task` |
| Superpowers skills | Same | Same | Identical Markdown, tool mapping handled by superpowers |

### Migration Effort Estimate

| Component | Effort | Risk |
|---|---|---|
| Plugin packaging (plugin.json, agents/, structure) | Small | Low — well-documented format |
| Skill adaptation (tool name substitution) | Medium | Low — systematic find-and-replace with judgment calls on GitHub MCP vs `gh` |
| Agent prompt templates (3 files) | Small | Low — extract from existing feature-dev prompts |
| Hook migration (9 hooks) | Medium | Medium — need to verify Copilot CLI hook input/output format matches |
| Hook elimination (4 hooks) | Small | Low — remove code, add inline MCP calls to skills |
| Settings generator adaptation | Medium | Medium — different settings format |
| Docker image adaptation | Medium | Medium — swap Claude Code install for Copilot CLI install, update entrypoint |
| Testing the full pipeline | Large | High — integration testing across 11 skills + hooks |

### What You Gain

1. **Zero-friction GitHub operations** — No more shell approvals for `gh`, no compound-command-interceptor fighting GraphQL mutations, no `--jq` parsing. Every GitHub interaction is a typed tool call with structured responses.

2. **Persistent state** — `store_memory` means `forge-resume` can check memory before reconstructing from GitHub. Sessions that crash don't lose their issue anchor.

3. **Pipeline visibility** — `report_intent` gives the user a clear status line showing where they are in the forge pipeline without scrolling through tool output.

4. **Fewer hooks** — 13 → 9. The eliminated hooks (assessment posting, plan posting, shell-expansion-guard, compound-command ergonomics) were workarounds for Claude Code limitations that don't exist in Copilot CLI.

5. **Cleaner agent dispatch** — Named agents auto-discovered from the plugin's `agents/` directory. No feature-dev plugin dependency — forge ships its own agent prompts.

6. **Async operations** — Long-running `jp5 deliver run` and test suites can run in background while the agent continues other work.

### What You Lose

1. **`EnterPlanMode` / `ExitPlanMode`** — Copilot CLI has no equivalent. The `forge-plan --lite` mode that uses native plan mode can't be ported directly. Full mode (which uses `writing-plans` skill) works fine. **Mitigation:** Drop `--lite` mode or implement it as a skill-only workflow without platform plan mode.

2. **Post-plan-to-issue hook automation** — The hook that auto-posted plans on `ExitPlanMode` has no trigger event. **Mitigation:** The skill posts the plan directly via MCP — actually cleaner and more transparent.

3. **Approval hygiene analysis** — If Copilot CLI's permission model is different (fewer re-approvals due to MCP), the approval-hygiene skill may have less data to analyze. **Mitigation:** May become unnecessary if MCP eliminates most approval friction.

4. **Ecosystem maturity** — Claude Code's plugin ecosystem is where forge was born and tested. Copilot CLI is newer. Edge cases may surface. **Mitigation:** Thorough integration testing of the full pipeline.