#!/usr/bin/env python3
"""PreToolUse hook: block compound shell commands and guide agents to safer patterns.

Fires on every Bash tool call. Detects for-loops, long && chains, and
pipe-to-tool patterns that should use built-in Claude Code tools or
parallel Bash calls instead.

Exits 2 (blocking) with guidance when a compound pattern is detected.
Exits 0 (pass-through) for single commands and pre-approved compounds.
"""

import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Pre-approved compound patterns (allowlist -- these pass through)
# ---------------------------------------------------------------------------
# These match the safe compounds already in settings.json allow list.
# The hook checks these BEFORE blocking so we don't interfere with
# patterns the operator has explicitly approved.

APPROVED_COMPOUNDS = [
    # export + git commit chains (identity setup)
    re.compile(r"^\s*export\s+.*&&\s*export\s+.*&&\s*git\s+commit"),
    re.compile(r"^\s*export\s+.*&&\s*export\s+.*&&\s*export\s+.*&&\s*git\s+commit"),
    re.compile(r"^\s*export\s+.*&&\s*git\s+commit"),
    # git compound patterns
    re.compile(r"^\s*git\s+add\s+.*&&\s*git\s+(commit|diff|stash)"),
    re.compile(r"^\s*git\s+fetch\s+.*&&\s*git\s+(pull|checkout)"),
    re.compile(r"^\s*git\s+checkout\s+.*&&\s*git\s+(pull|merge)"),
    re.compile(r"^\s*git\s+stash\s+.*&&\s*git\s+(checkout|pull)"),
]


# ---------------------------------------------------------------------------
# Mode awareness
# ---------------------------------------------------------------------------
# In autonomous mode, skip ergonomic checks (pipes, stderr suppression,
# redirects, long chains). Safety checks (for-loops, subshell substitution)
# always run regardless of mode.


def _is_autonomous():
    """Check if running in autonomous mode."""
    return os.environ.get("CLAUDE_MODE", "supervised") == "autonomous"


def should_check_pipes():
    """Whether to check pipe-to-tool patterns."""
    return not _is_autonomous()


def should_check_stderr_suppression():
    """Whether to check 2>/dev/null patterns."""
    return not _is_autonomous()


def should_check_long_chains():
    """Whether to check long && chain patterns."""
    return not _is_autonomous()


def should_check_redirects():
    """Whether to check redirect anti-patterns."""
    return not _is_autonomous()


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

def detect_for_loop(cmd: str) -> bool:
    """Detect shell for-loops: for ... do ... done or for (( ... )).

    Distinguishes shell for-loops from Python for-loops by requiring
    shell-specific tokens: `; do`, `; done`, or `do\n`.
    """
    # Shell for-in with do/done
    if re.search(r"\bfor\s+\w+\s+in\s+.*;\s*do\b", cmd, re.DOTALL):
        return True
    # Shell for-in with do on next line
    if re.search(r"\bfor\s+\w+\s+in\s+.*\n\s*do\b", cmd, re.DOTALL):
        return True
    # C-style for (( ... ))
    if re.search(r"\bfor\s*\(\(", cmd):
        return True
    return False


def detect_long_chain(cmd: str) -> int:
    """Count && segments. Returns segment count (3+ is suspicious)."""
    # Naive split -- doesn't handle && inside quotes, but good enough
    # for the patterns agents generate.
    segments = re.split(r"\s*&&\s*", cmd)
    return len(segments)


def detect_subshell_substitution(cmd: str) -> bool:
    """Detect $() command substitution and backticks.

    These are opaque to the permission matcher -- it can't predict what
    the expansion will produce, so they always trigger re-approval.
    """
    # $(...) -- but not $() with nothing inside (unlikely but safe)
    if re.search(r"\$\([^)]+\)", cmd):
        return True
    # $(<file) -- file content substitution
    if re.search(r"\$\(<", cmd):
        return True
    # Backtick substitution
    if re.search(r"`[^`]+`", cmd):
        return True
    return False


def detect_stderr_suppression(cmd: str) -> bool:
    """Detect 2>/dev/null and similar stderr suppression patterns.

    These indicate the agent is working around errors in shell instead
    of using dedicated tools (Read, Glob) that handle missing files
    gracefully.
    """
    return bool(re.search(r"2>\s*/dev/null", cmd))


def detect_redirect_antipatterns(cmd: str) -> str | None:
    """Detect redirect anti-patterns that should use built-in tools instead.

    1. `cmd > file && cat file` -- redirect then read back is pointless
    2. `cmd > /tmp/...` -- agent should capture Bash output directly
    """
    # Pattern 1: redirect + cat/read back -- e.g. `gh pr diff 414 > /tmp/x && cat /tmp/x`
    m = re.search(r">\s*(/\S+)\s*&&\s*cat\s+\1", cmd)
    if m:
        return (
            "Redirect-then-cat detected (`cmd > file && cat file`). "
            "Run the command directly and capture the output in-context. "
            "The Bash tool returns stdout -- no need to redirect to a file and read it back."
        )

    # Pattern 2: redirect + cat with different targets but same intent
    m = re.search(r">\s*/\S+\s*&&\s*cat\s+/\S+", cmd)
    if m:
        return (
            "Redirect-then-cat detected. "
            "Run the command directly and capture the output in-context. "
            "The Bash tool returns stdout -- no need to redirect to a file and read it back."
        )

    # Pattern 3: simple redirect to /tmp/ -- agent should capture output directly
    # Only flag single commands (no &&), to avoid blocking legitimate multi-step scripts
    if "&&" not in cmd and re.search(r">\s*/tmp/", cmd):
        return (
            "Unnecessary redirect to /tmp/ detected. "
            "The Bash tool captures stdout directly -- run the command without "
            "the redirect and use the output in-context. If the output is too "
            "large, use the Read tool on the Bash output file instead."
        )

    return None


def detect_pipe_to_tool(cmd: str) -> str | None:
    """Detect pipes to tools that have built-in equivalents."""
    pipe_patterns = [
        (r"\|\s*grep\b", "grep", "Use the Grep tool instead of piping to grep."),
        (r"\|\s*jq\b", "jq", "Process JSON in-context instead of piping to jq."),
        (r"\|\s*head\b", "head", "Use the Read tool with offset/limit instead of piping to head."),
        (r"\|\s*tail\b", "tail", "Use the Read tool with offset/limit instead of piping to tail."),
        (r"\|\s*awk\b", "awk", "Use the Grep tool or process data in-context instead of piping to awk."),
        (r"\|\s*sed\b", "sed", "Use the Edit tool instead of piping to sed."),
        (r"\|\s*wc\b", "wc", "Use the Grep tool with count output mode instead of piping to wc."),
    ]
    for pattern, tool, guidance in pipe_patterns:
        if re.search(pattern, cmd):
            return guidance
    return None


def is_approved_compound(cmd: str) -> bool:
    """Check if the command matches a pre-approved compound pattern."""
    for pattern in APPROVED_COMPOUNDS:
        if pattern.search(cmd):
            return True
    return False


# ---------------------------------------------------------------------------
# Guidance messages
# ---------------------------------------------------------------------------

FOR_LOOP_GUIDANCE = """\
[HOOK] For-loop compound command blocked.

For-loops around CLI commands create wildcard-bypass risk and are not \
allowed. Use one of these safer alternatives:

1. **Parallel Bash tool calls** -- make multiple independent Bash calls \
in a single message, one per item. Claude Code runs them concurrently.
2. **Bulk CLI command** -- use `jp5 ops issue-relations --map-file` or \
similar bulk subcommands that accept a file of inputs.
3. **Sequential Bash calls** -- if order matters, make separate Bash \
calls and let the results chain naturally.

Example: instead of `for i in 1 2 3; do gh issue view $i; done`, \
make three parallel Bash calls: `gh issue view 1`, `gh issue view 2`, \
`gh issue view 3`."""

LONG_CHAIN_GUIDANCE = """\
[HOOK] Long compound command blocked (3+ chained commands).

Chaining many commands with && creates wildcard-bypass risk. Break \
this into separate Bash tool calls:

1. **Independent commands** -- run them as parallel Bash calls in a \
single message.
2. **Dependent commands** -- run them as sequential Bash calls, using \
the result of each to inform the next.
3. **Variable + command** -- if you need a variable from one command \
in the next, capture it in the first call's output and reference it \
in the second call."""


SUBSHELL_GUIDANCE = """\
[HOOK] Command substitution $() or backticks blocked.

The permission matcher cannot predict what $() or backtick \
expansions will produce, so they always trigger re-approval. \
Use direct values instead:

1. **File content in CLI args** -- use the CLI's native file flags \
(e.g., `gh pr edit <N> --body-file <path>` instead of \
`gh api -f body="$(<file)"`).
2. **Command output as input** -- use the Read tool to get file \
content, then construct the command with literal values.
3. **Variable capture** -- run the producing command in a separate \
Bash call, read the output, then use it in the next call.

Common replacements:
- `gh api -f body="$(<file)"` -> `gh pr edit <N> --body-file <path>`
- `gh api ... $(gh api ...)` -> two sequential Bash calls
- `echo "$(date)"` -> `date` (direct command)"""


STDERR_SUPPRESSION_GUIDANCE = """\
[HOOK] Stderr suppression (2>/dev/null) blocked.

Suppressing stderr means the command might fail and you're hiding it. \
Use dedicated tools that handle missing files and errors gracefully:

1. **Check if a file exists** -- use `Read` (returns a clean error) \
or `Glob` (returns empty list).
2. **Check if a process/path exists** -- use `Glob` for paths, or \
run the command without 2>/dev/null and handle the error in-context.
3. **Suppress expected noise** -- if the command is noisy but correct, \
the noise is still useful for debugging. Don't suppress it.

Common replacements:
- `ls -la /path 2>/dev/null` -> `Read(/path)` or `Glob(/path)`
- `cat file 2>/dev/null` -> `Read(file)`
- `command 2>/dev/null` -> run without suppression, handle errors"""


def pipe_guidance(tool_hint: str) -> str:
    return f"""\
[HOOK] Pipe to shell tool blocked.

{tool_hint}

Claude Code provides dedicated tools (Grep, Read, Edit, Glob) that \
are faster, safer, and produce better-structured output than shell \
pipes. Use them instead of piping command output to shell tools."""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command or not command.strip():
        return

    cmd = command.strip()

    # Pass through pre-approved compounds
    if is_approved_compound(cmd):
        return

    # Check 0: stderr suppression (2>/dev/null) -- ergonomic, skipped in autonomous
    if should_check_stderr_suppression() and detect_stderr_suppression(cmd):
        result = {
            "decision": "block",
            "reason": STDERR_SUPPRESSION_GUIDANCE,
        }
        print(json.dumps(result))
        sys.exit(2)

    # Check 1: for-loops -- ALWAYS checked (safety, not ergonomics)
    if detect_for_loop(cmd):
        result = {
            "decision": "block",
            "reason": FOR_LOOP_GUIDANCE,
        }
        print(json.dumps(result))
        sys.exit(2)

    # Check 2: pipe to shell tool -- ergonomic, skipped in autonomous
    if should_check_pipes():
        pipe_hint = detect_pipe_to_tool(cmd)
        if pipe_hint:
            result = {
                "decision": "block",
                "reason": pipe_guidance(pipe_hint),
            }
            print(json.dumps(result))
            sys.exit(2)

    # Check 3: redirect anti-patterns -- ergonomic, skipped in autonomous
    if should_check_redirects():
        redirect_hint = detect_redirect_antipatterns(cmd)
        if redirect_hint:
            result = {
                "decision": "block",
                "reason": f"[HOOK] {redirect_hint}",
            }
            print(json.dumps(result))
            sys.exit(2)

    # Check 4: subshell substitution $() or backticks -- ALWAYS checked (safety)
    if detect_subshell_substitution(cmd):
        result = {
            "decision": "block",
            "reason": SUBSHELL_GUIDANCE,
        }
        print(json.dumps(result))
        sys.exit(2)

    # Check 5: long && chains (3+ segments) -- ergonomic, skipped in autonomous
    if should_check_long_chains() and detect_long_chain(cmd) >= 3:
        result = {
            "decision": "block",
            "reason": LONG_CHAIN_GUIDANCE,
        }
        print(json.dumps(result))
        sys.exit(2)


try:
    main()
except Exception:
    # Best-effort -- never block session on hook failure
    pass
