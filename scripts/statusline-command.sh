#!/usr/bin/env bash
# Forge statusline — renders context in the Claude Code status bar.
# Scaffolded by forge init. Customize freely.
#
# Input: JSON blob on stdin with session state (model, context, vim, etc.)
# Output: ANSI-colored status text (two lines)

input=$(cat)
cwd=$(echo "$input" | jq -r '.cwd')
user=$(whoami)
host=$(hostname -s)

# --- Line 1: user@host:/path [branch] ---

branch=""
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
    branch=$(git -C "$cwd" branch --show-current 2>/dev/null)
fi

if [[ -n "$branch" ]]; then
    printf '\033[01;32m%s@%s\033[00m:\033[01;34m%s\033[00m [\033[33m%s\033[00m]' "$user" "$host" "$cwd" "$branch"
else
    printf '\033[01;32m%s@%s\033[00m:\033[01;34m%s\033[00m' "$user" "$host" "$cwd"
fi

# --- Line 2: model | ctx | vim | session | worktree | agent | rate limits ---

parts=()

# Model display name
model=$(echo "$input" | jq -r '.model.display_name // empty')
[[ -n "$model" ]] && parts+=("\033[36m${model}\033[00m")

# Context usage percentage
ctx_used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
if [[ -n "$ctx_used" ]]; then
    ctx_int=$(printf '%.0f' "$ctx_used")
    if   (( ctx_int >= 80 )); then ctx_color='\033[31m'   # red — high pressure
    elif (( ctx_int >= 50 )); then ctx_color='\033[33m'   # yellow — moderate
    else                           ctx_color='\033[32m'   # green — comfortable
    fi
    parts+=("${ctx_color}ctx:${ctx_int}%\033[00m")
fi

# Vim mode — only present when vim mode is enabled
vim_mode=$(echo "$input" | jq -r '.vim.mode // empty')
if [[ -n "$vim_mode" ]]; then
    case "$vim_mode" in
        NORMAL) vim_color='\033[32m' ;;
        INSERT) vim_color='\033[33m' ;;
        *)      vim_color='\033[35m' ;;
    esac
    parts+=("${vim_color}vim:${vim_mode}\033[00m")
fi

# Session name — only when explicitly set via /rename
session_name=$(echo "$input" | jq -r '.session_name // empty')
[[ -n "$session_name" ]] && parts+=("\033[37msession:${session_name}\033[00m")

# Worktree info — only present in --worktree sessions
wt_name=$(echo "$input" | jq -r '.worktree.name // empty')
wt_branch=$(echo "$input" | jq -r '.worktree.branch // empty')
if [[ -n "$wt_name" ]]; then
    wt_label="wt:${wt_name}"
    [[ -n "$wt_branch" ]] && wt_label="${wt_label}(${wt_branch})"
    parts+=("\033[35m${wt_label}\033[00m")
fi

# Agent name — only present when started with --agent flag
agent_name=$(echo "$input" | jq -r '.agent.name // empty')
[[ -n "$agent_name" ]] && parts+=("\033[35magent:${agent_name}\033[00m")

# Rate limits — Claude.ai subscription burn rates (absent for API keys)
five_pct=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
week_pct=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
rate_str=""
if [[ -n "$five_pct" && "$five_pct" =~ ^[0-9.]+$ ]]; then
    five_int=$(printf '%.0f' "$five_pct")
    rate_str="5h:${five_int}%"
fi
if [[ -n "$week_pct" && "$week_pct" =~ ^[0-9.]+$ ]]; then
    week_int=$(printf '%.0f' "$week_pct")
    [[ -n "$rate_str" ]] && rate_str="${rate_str} "
    rate_str="${rate_str}7d:${week_int}%"
fi
[[ -n "$rate_str" ]] && parts+=("\033[33m${rate_str}\033[00m")

# Render line 2 only when there is something to show
if (( ${#parts[@]} > 0 )); then
    printf '\n'
    first=1
    for part in "${parts[@]}"; do
        [[ $first -eq 0 ]] && printf ' \033[90m|\033[00m '
        printf '%b' "$part"
        first=0
    done
fi
