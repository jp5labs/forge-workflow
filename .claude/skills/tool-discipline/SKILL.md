# Tool Discipline Rules

This skill defines project-specific conventions for how agents use tools. All agents in this repo must follow these rules. This does not restrict tool access — agents retain full tool availability. The rules govern *how* tools are used to avoid approval prompts and follow project conventions.

## Shell command discipline

- **Common compound patterns are pre-approved** in the allow-list (e.g., `git add && git commit`, `export && git commit`, `git fetch && git pull`) — arbitrary combinations of individually-allowed commands do not automatically pass
- **Run independent commands as separate Bash tool calls** when they don't need to be sequenced
- **Never prefix commands with `cd`** — the working directory is already set correctly
- Compound commands that mix allowed and non-allowed commands will still trigger approval prompts

## Shell variable expansion — prohibited

- **Never use `${}`** in Bash tool commands — Claude Code's platform flags `${}` as a shell injection risk and prompts for approval, even in `bypassPermissions` mode. This stalls unattended sessions.
- **Read env vars** with `printenv VAR_NAME` instead of `echo "${VAR}"`
- **Default values** — run `printenv VAR_NAME`, check the output in-context, and use the value (or your default) in the next command
- **String interpolation** — capture values from prior Bash calls, then construct commands with literal values

## Inline Python execution — prohibited

- **Never use `python -c` or `python3 -c`** — denied in project settings
- For JSON parsing, data extraction, or computation: process data in-context
- For data transformation: use dedicated tools (Grep, Read) or write a script file

## File operations — use dedicated tools

- **Use `Write` tool** for file creation and overwrite — never `cat > file`, `cat >> file`, or heredocs (`cat << 'EOF'`)
- **Use `Read` tool** for reading files — never `cat`, `head`, `tail`
- **Use `Edit` tool** for modifying files — never `sed`, `awk`
- **Use `Glob` tool** for finding files — never `find`, `ls`
- **Use `Grep` tool** for searching content — never `grep`, `rg`
- The `Write` tool creates parent directories automatically — never run `mkdir` before writing
- The `Write` tool requires a prior `Read` of the target file in the same conversation; for files that may not exist yet, issue a `Read` first (the error is expected), then `Write`

## GitHub mutations

- **Direct `gh` mutation commands** and **MCP GitHub tools** are allowed for all GitHub operations (create, update, merge, comment, etc.)
- **Prefer MCP GitHub tools** for read-only queries (`list_issues`, `search_issues`, `get_issue`, `get_pull_request`, `list_pull_requests`, `get_file_contents`) — they avoid shell approval entirely
- For PR/issue descriptions and comments, prefer `--body-file <path>` over inline `--body` when using `gh` CLI
- **Never pipe `gh api` output to `jq`** — process JSON output in-context instead

## Commit identity

- **Use `export` env vars** to set commit identity — not `git -c user.name=...`
- `git -c` doesn't match `Bash(git commit*)` and triggers prompts

```bash
export GIT_AUTHOR_NAME="Your Name" GIT_AUTHOR_EMAIL="you@example.com"
export GIT_COMMITTER_NAME="Your Name" GIT_COMMITTER_EMAIL="you@example.com"
git commit -F tmp/commit-msg.txt
```

## Directory creation

- **Never run `mkdir`** before delivery scripts — they create their own output directories automatically
- **Use the `Write` tool** instead of `mkdir -p` + shell redirection — `Write` creates parent directories automatically

## Branch naming

- Branches must follow `issue-<N>-<slug>` format (e.g., `issue-153-retrieval-topology`)

## Commit discipline

- **Never commit directly to main** — all changes must go through a PR with review
- A `PreToolUse` hook (`block-commit-to-main.py`) enforces this automatically
- **Separate policy/governance changes from ops/resilience changes** as distinct commits for clearer review and rollback

## Delivery scripts

- **Always invoke skills** (`/forge-deliver`, `/forge-cleanup`) rather than calling underlying scripts directly
- Skills ensure all side effects (telemetry, comments) are captured

## Secrets

- **Never edit `.env` files**
- Secrets include `QDRANT_API_KEY`, `LITELLM_MASTER_KEY`, `LITELLM_FAST_MASTER_KEY`
- **Strip `\r`/`\n`** from env values when consuming in Python (Windows line-ending risk)

## Python subprocess rule

- **Use `sys.executable`** not `python`/`python3` in subprocess calls within orchestrator scripts
- Shell-level hook commands (in `.claude/settings.json`) use `python` — not `python3`
- The `sys.executable` rule applies only to in-process subprocess calls, not to hook command strings

## SDK drift

- For `qdrant-client`: `search` vs `query_points` API drift is a known issue
- **Pin versions** or implement compatibility fallbacks for known API drift
