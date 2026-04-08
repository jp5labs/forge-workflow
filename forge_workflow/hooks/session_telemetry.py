#!/usr/bin/env python3
"""SessionEnd hook: capture session telemetry from transcript and post to issue.

Fires on every SessionEnd event. Parses the JSONL transcript at
``transcript_path`` to extract exact token counts, tool call counts,
skills invoked, agents spawned, and wall time. Posts a formatted
telemetry comment to the linked GitHub issue.

Also copies the raw transcript into tmp/session-telemetry/<session-id>/
so that mid-session tools like /token-hygiene can analyze it later.

Exits 0 always (best-effort) -- posting failure must not block session
shutdown.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from forge_workflow.config import repo_slug

REPO = repo_slug()

# Transcript retention limits
TRANSCRIPT_MAX_AGE_DAYS = 7
TRANSCRIPT_MAX_COUNT = 10

# Tools whose inputs contain file paths
FILE_PATH_TOOLS = {"Read", "Write", "Edit", "Glob"}


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

def parse_transcript(transcript_path: str) -> dict:
    """Parse a JSONL transcript and aggregate telemetry fields."""
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "api_calls": 0,
        "tool_calls": 0,
    }
    models: set[str] = set()
    skills: Counter = Counter()
    agents: Counter = Counter()
    tool_breakdown: Counter = Counter()
    web_domains: Counter = Counter()
    files_touched: set[str] = set()
    git_ops: Counter = Counter()
    stop_reasons: Counter = Counter()
    per_model_tokens: dict[str, dict[str, int]] = {}
    tool_errors: int = 0
    tool_successes: int = 0
    user_turns: int = 0
    first_ts: str | None = None
    last_ts: str | None = None

    try:
        with open(transcript_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                # Track timestamps for wall time
                ts = obj.get("timestamp")
                if ts:
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts

                record_type = obj.get("type", "")

                # --- User turns ---
                if record_type == "user":
                    # Count user messages that contain actual text (not tool_result)
                    msg = obj.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, str) and content.strip():
                        user_turns += 1
                    elif isinstance(content, list):
                        has_text = any(
                            isinstance(b, dict) and b.get("type") == "text"
                            for b in content
                        )
                        has_tool_result = any(
                            isinstance(b, dict) and b.get("type") == "tool_result"
                            for b in content
                        )
                        if has_text and not has_tool_result:
                            user_turns += 1
                    continue

                # --- Tool results (for success/failure tracking) ---
                if record_type == "tool_result":
                    is_error = obj.get("is_error", False)
                    return_code = obj.get("returnCode", 0)
                    if is_error or (isinstance(return_code, int) and return_code != 0):
                        tool_errors += 1
                    else:
                        tool_successes += 1
                    continue

                if record_type != "assistant":
                    # Check for tool_result in content blocks of other record types
                    msg = obj.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") == "tool_result":
                                is_error = block.get("is_error", False)
                                rc = block.get("returnCode", 0)
                                if is_error or (isinstance(rc, int) and rc != 0):
                                    tool_errors += 1
                                else:
                                    tool_successes += 1
                    continue

                # --- Assistant records ---
                totals["api_calls"] += 1
                msg = obj.get("message", {})

                # Token usage
                usage = msg.get("usage", {})
                totals["input_tokens"] += usage.get("input_tokens", 0)
                totals["output_tokens"] += usage.get("output_tokens", 0)
                totals["cache_creation_input_tokens"] += usage.get(
                    "cache_creation_input_tokens", 0
                )
                totals["cache_read_input_tokens"] += usage.get(
                    "cache_read_input_tokens", 0
                )

                # Model and per-model token tracking
                model = msg.get("model", "")
                if model:
                    models.add(model)
                    if model not in per_model_tokens:
                        per_model_tokens[model] = {
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                        }
                    per_model_tokens[model]["input_tokens"] += usage.get("input_tokens", 0)
                    per_model_tokens[model]["output_tokens"] += usage.get("output_tokens", 0)
                    per_model_tokens[model]["cache_creation_input_tokens"] += usage.get(
                        "cache_creation_input_tokens", 0
                    )
                    per_model_tokens[model]["cache_read_input_tokens"] += usage.get(
                        "cache_read_input_tokens", 0
                    )

                # Stop reason
                stop_reason = msg.get("stop_reason", "")
                if stop_reason:
                    stop_reasons[stop_reason] += 1

                # Content blocks -- tool calls, skills, agents, files, web, git
                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue

                    totals["tool_calls"] += 1
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    if not isinstance(tool_input, dict):
                        tool_input = {}

                    # Tool breakdown
                    if tool_name:
                        tool_breakdown[tool_name] += 1

                    # Skills (with counts, including anthropic-skills:*)
                    if tool_name == "Skill":
                        skill_name = tool_input.get("skill", "")
                        if skill_name:
                            skills[skill_name] += 1

                    # Agents
                    elif tool_name == "Agent":
                        agent_type = tool_input.get("subagent_type", "")
                        if agent_type:
                            agents[agent_type] += 1

                    # Web calls -- extract domains
                    elif tool_name == "WebFetch":
                        url = tool_input.get("url", "")
                        if url:
                            try:
                                domain = urlparse(url).netloc
                                if domain:
                                    web_domains[domain] += 1
                            except Exception:
                                pass
                    elif tool_name == "WebSearch":
                        web_domains["web search"] += 1

                    # Files touched
                    if tool_name in FILE_PATH_TOOLS:
                        for key in ("file_path", "path", "pattern"):
                            val = tool_input.get(key, "")
                            if val and isinstance(val, str) and not val.startswith("**"):
                                files_touched.add(val)

                    # Git operations
                    if tool_name == "Bash":
                        cmd = tool_input.get("command", "")
                        if isinstance(cmd, str) and cmd.strip().startswith("git "):
                            parts = cmd.strip().split()
                            if len(parts) >= 2:
                                git_ops[parts[1]] += 1

    except OSError:
        pass

    return {
        **totals,
        "models": sorted(models),
        "skills": skills,
        "agents": agents,
        "tool_breakdown": tool_breakdown,
        "web_domains": web_domains,
        "files_touched": files_touched,
        "git_ops": git_ops,
        "stop_reasons": stop_reasons,
        "per_model_tokens": per_model_tokens,
        "tool_errors": tool_errors,
        "tool_successes": tool_successes,
        "user_turns": user_turns,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


# ---------------------------------------------------------------------------
# Subagent transcript parsing
# ---------------------------------------------------------------------------

def parse_subagent_transcripts(transcript_path: str) -> dict:
    """Sum token usage from subagent transcript files."""
    result = {"input_tokens": 0, "output_tokens": 0, "agent_count": 0}
    try:
        # Transcript lives at <project-dir>/<session-id>.jsonl
        # Subagents live in <project-dir>/<session-id>/subagents/
        transcript_file = Path(transcript_path)
        session_dir = transcript_file.parent / transcript_file.stem
        subagents_dir = session_dir / "subagents"
        if not subagents_dir.is_dir():
            return result
        agent_files = sorted(subagents_dir.glob("agent-*.jsonl"))
        result["agent_count"] = len(agent_files)
        for agent_file in agent_files:
            try:
                with open(agent_file, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if obj.get("type") != "assistant":
                            continue
                        usage = obj.get("message", {}).get("usage", {})
                        result["input_tokens"] += usage.get("input_tokens", 0)
                        result["output_tokens"] += usage.get("output_tokens", 0)
            except OSError:
                continue
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

def _match_rate(model: str, rates: dict) -> dict | None:
    """Find the best matching rate entry for a model ID."""
    if model in rates:
        return rates[model]
    for rate_model, rate_data in rates.items():
        if model.startswith(rate_model) or rate_model.startswith(model):
            return rate_data
    return None


def compute_cost(models: list[str], token_data: dict, per_model_tokens: dict, cwd: str) -> str:
    """Estimate session cost from model-costs.csv.

    ``per_model_tokens`` maps model_id -> {input_tokens, output_tokens,
    cache_creation_input_tokens, cache_read_input_tokens}.  When multiple
    models are used in a session, costs are computed per-model for accuracy.
    Falls back to aggregate tokens with the first matched rate when
    per-model data is unavailable.
    """
    csv_path = Path(cwd) / ".claude" / "model-costs.csv"
    if not csv_path.is_file():
        return "_Not available -- `.claude/model-costs.csv` not found_"

    try:
        rates: dict[str, dict[str, float]] = {}
        with open(csv_path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                model_id = row.get("model_id", "").strip()
                if model_id:
                    rates[model_id] = {
                        "input": float(row.get("input_per_mtok", 0)),
                        "output": float(row.get("output_per_mtok", 0)),
                        "cache_read": float(row.get("cache_read_per_mtok", 0)),
                        "cache_write": float(row.get("cache_write_per_mtok", 0)),
                    }

        if not rates:
            return "_Not available -- empty model-costs.csv_"

        # Per-model cost when breakdown is available
        if per_model_tokens and len(models) > 1:
            total_cost = 0.0
            unmatched = []
            for model_id, toks in per_model_tokens.items():
                rate = _match_rate(model_id, rates)
                if rate:
                    total_cost += (
                        toks.get("input_tokens", 0) * rate["input"]
                        + toks.get("output_tokens", 0) * rate["output"]
                        + toks.get("cache_read_input_tokens", 0) * rate["cache_read"]
                        + toks.get("cache_creation_input_tokens", 0) * rate["cache_write"]
                    ) / 1_000_000
                else:
                    unmatched.append(model_id)
            caveat = ""
            if unmatched:
                caveat = f" -- {', '.join(unmatched)} not in CSV, excluded"
            return f"~${total_cost:.2f} (multi-model{caveat})"

        # Single model or no per-model breakdown -- use aggregate tokens
        matched_rate = None
        for model in models:
            matched_rate = _match_rate(model, rates)
            if matched_rate:
                break

        if not matched_rate:
            return "_Not available -- model not found in model-costs.csv_"

        cost = (
            token_data["input_tokens"] * matched_rate["input"]
            + token_data["output_tokens"] * matched_rate["output"]
            + token_data["cache_read_input_tokens"] * matched_rate["cache_read"]
            + token_data["cache_creation_input_tokens"] * matched_rate["cache_write"]
        ) / 1_000_000

        return f"~${cost:.2f} (based on model-costs.csv rates)"

    except Exception:
        return "_Not available -- error reading model-costs.csv_"


# ---------------------------------------------------------------------------
# Wall time
# ---------------------------------------------------------------------------

def compute_wall_time(first_ts: str | None, last_ts: str | None) -> str:
    """Return human-readable wall time from ISO timestamps."""
    if not first_ts or not last_ts:
        return "unknown"
    try:
        t0 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        delta = t1 - t0
        total_secs = int(delta.total_seconds())
        if total_secs < 0:
            return "unknown"
        minutes, seconds = divmod(total_secs, 60)
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
    except (ValueError, TypeError):
        return "unknown"


# ---------------------------------------------------------------------------
# Issue resolution
# ---------------------------------------------------------------------------

def find_issue_number(cwd: str) -> str | None:
    """Find the current session issue number from anchor files."""
    for filename in (".session-issue", ".plan-issue"):
        path = os.path.join(cwd, "tmp", filename)
        try:
            num = Path(path).read_text(encoding="utf-8").strip()
            if num.isdigit():
                return num
        except OSError:
            continue
    return None


# ---------------------------------------------------------------------------
# Comment formatting
# ---------------------------------------------------------------------------

def fmt(n: int) -> str:
    """Format an integer with thousands separators."""
    return f"{n:,}"


def format_counter_line(counter: Counter) -> str:
    """Format a Counter as 'name xN, name xM (T total)'."""
    if not counter:
        return "none"
    parts = [f"{name} \u00d7{count}" for name, count in counter.most_common()]
    total = sum(counter.values())
    return ", ".join(parts) + f" ({fmt(total)} total)"


def format_comment(session_id: str, data: dict, subagent_data: dict, cwd: str) -> str:
    """Build the telemetry markdown comment."""
    model = ", ".join(data["models"]) if data["models"] else "unknown"
    wall = compute_wall_time(data["first_ts"], data["last_ts"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_tokens = (
        data["input_tokens"]
        + data["output_tokens"]
        + data["cache_creation_input_tokens"]
        + data["cache_read_input_tokens"]
    )

    # Input tokens line
    input_parts = [fmt(data["input_tokens"])]
    if data["cache_read_input_tokens"]:
        input_parts.append(f"+ {fmt(data['cache_read_input_tokens'])} cache read")
    if data["cache_creation_input_tokens"]:
        input_parts.append(f"+ {fmt(data['cache_creation_input_tokens'])} cache write")
    input_line = " (".join(input_parts[:1])
    if len(input_parts) > 1:
        input_line += " (" + ", ".join(input_parts[1:]) + ")"

    # Tool breakdown line
    tool_breakdown_line = format_counter_line(data["tool_breakdown"])

    # Skills line (with counts)
    skills_counter: Counter = data["skills"]
    if skills_counter:
        skill_parts = [f"{k} \u00d7{v}" for k, v in skills_counter.most_common()]
        total_calls = sum(skills_counter.values())
        unique_count = len(skills_counter)
        skills_line = ", ".join(skill_parts) + f" ({fmt(total_calls)} calls, {unique_count} unique)"
    else:
        skills_line = "none"

    # Agents line
    agents_counter: Counter = data["agents"]
    if agents_counter:
        agent_parts = [f"{k} \u00d7{v}" for k, v in agents_counter.most_common()]
        agents_total = sum(agents_counter.values())
        agents_line = ", ".join(agent_parts) + f" ({agents_total} total)"
    else:
        agents_line = "none (0 total)"

    # Cost estimate
    cost_line = compute_cost(data["models"], data, data.get("per_model_tokens", {}), cwd)

    # Cache hit rate
    cache_total = (
        data["input_tokens"]
        + data["cache_read_input_tokens"]
        + data["cache_creation_input_tokens"]
    )
    if cache_total > 0:
        cache_rate = (data["cache_read_input_tokens"] / cache_total) * 100
        cache_line = f"{cache_rate:.1f}%"
    else:
        cache_line = "N/A"

    # Tool success/failure rate
    total_results = data["tool_successes"] + data["tool_errors"]
    if total_results > 0:
        success_pct = (data["tool_successes"] / total_results) * 100
        success_line = f"{data['tool_successes']}/{total_results} ({success_pct:.1f}%)"
        if data["tool_errors"] > 0:
            success_line += f" \u2014 {data['tool_errors']} errors"
    else:
        success_line = "N/A"

    # Web calls line
    web_domains: Counter = data["web_domains"]
    if web_domains:
        web_line = format_counter_line(web_domains)
    else:
        web_line = "none"

    # Files touched
    files_count = len(data["files_touched"])
    files_line = f"{files_count} unique files" if files_count > 0 else "none"

    # User turns
    user_turns_line = fmt(data["user_turns"])

    # Git operations
    git_ops: Counter = data["git_ops"]
    if git_ops:
        git_line = format_counter_line(git_ops)
    else:
        git_line = "none"

    # Subagent tokens
    if subagent_data["agent_count"] > 0:
        subagent_line = (
            f"{fmt(subagent_data['input_tokens'])} input + "
            f"{fmt(subagent_data['output_tokens'])} output "
            f"(across {subagent_data['agent_count']} agents)"
        )
    else:
        subagent_line = "none"

    # Stop reasons
    stop_reasons: Counter = data["stop_reasons"]
    if stop_reasons:
        stop_parts = [f"{reason} \u00d7{count}" for reason, count in stop_reasons.most_common()]
        stop_line = ", ".join(stop_parts)
        if "max_tokens" in stop_reasons:
            stop_line += " \u26a0\ufe0f"
    else:
        stop_line = "N/A"

    lines = [
        "## Session Telemetry (auto-captured)",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Model | {model} |",
        f"| Session ID | `{session_id}` |",
        f"| Session date | {today} |",
        f"| Wall time | {wall} |",
        f"| API calls | {fmt(data['api_calls'])} |",
        f"| Input tokens | {input_line} |",
        f"| Output tokens | {fmt(data['output_tokens'])} |",
        f"| Total tokens | {fmt(total_tokens)} |",
        f"| Tool calls | {tool_breakdown_line} |",
        f"| Skills invoked | {skills_line} |",
        f"| Agents spawned | {agents_line} |",
        f"| Cost (USD est.) | {cost_line} |",
        f"| Cache hit rate | {cache_line} |",
        f"| Tool success rate | {success_line} |",
        f"| Web calls | {web_line} |",
        f"| Files touched | {files_line} |",
        f"| User turns | {user_turns_line} |",
        f"| Git operations | {git_line} |",
        f"| Subagent tokens | {subagent_line} |",
        f"| Stop reasons | {stop_line} |",
        "",
        "_Captured automatically by SessionEnd hook from transcript data._",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------

def _find_existing_telemetry_comment(
    issue_num: str, session_id: str, cwd: str,
) -> str | None:
    """Return the comment ID if a telemetry comment for this session already exists."""
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/issues/{issue_num}/comments",
         "--paginate", "-q",
         f'.[] | select(.body | contains("Session ID | `{session_id}`")) | .id'],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode == 0:
        comment_id = result.stdout.strip().split("\n")[0]
        if comment_id and comment_id.isdigit():
            return comment_id
    return None


def _update_comment(comment_id: str, body_file: str, cwd: str) -> bool:
    """Update an existing comment in-place."""
    body = Path(body_file).read_text(encoding="utf-8")
    result = subprocess.run(
        ["gh", "api", "-X", "PATCH", f"repos/{REPO}/issues/comments/{comment_id}",
         "-f", f"body={body}"],
        capture_output=True, text=True, cwd=cwd,
    )
    return result.returncode == 0


def post_comment(issue_num: str, session_id: str, body_file: str, cwd: str) -> None:
    """Post or update a telemetry comment on the GitHub issue."""
    # Check for existing comment to avoid duplicates
    existing_id = _find_existing_telemetry_comment(issue_num, session_id, cwd)
    if existing_id:
        if _update_comment(existing_id, body_file, cwd):
            print(f"[HOOK] Telemetry updated (comment {existing_id}) on issue #{issue_num}.")
        else:
            print(f"[HOOK] Failed to update comment {existing_id}, posting new.", file=sys.stderr)
            _post_new_comment(issue_num, body_file, cwd)
        return

    _post_new_comment(issue_num, body_file, cwd)


def _post_new_comment(issue_num: str, body_file: str, cwd: str) -> None:
    """Post a new comment to the GitHub issue."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "comment",
            issue_num,
            "--repo",
            REPO,
            "--body-file",
            body_file,
        ],
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    if result.returncode == 0:
        print(f"[HOOK] Telemetry posted to issue #{issue_num}.")
    else:
        snippet = (result.stderr or "").strip()[:200]
        print(
            f"[HOOK] Failed to post telemetry to issue #{issue_num} "
            f"(rc={result.returncode}). {snippet}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Usage log
# ---------------------------------------------------------------------------

def _append_usage_log(session_id: str, telemetry: dict, cwd: str) -> None:
    """Append a one-line JSON record to tmp/usage-log.jsonl for rolling cost tracking."""
    try:
        total_tokens = (
            telemetry["input_tokens"]
            + telemetry["output_tokens"]
            + telemetry["cache_creation_input_tokens"]
            + telemetry["cache_read_input_tokens"]
        )
        wall = compute_wall_time(telemetry["first_ts"], telemetry["last_ts"])
        # Parse wall time to minutes
        wall_min = 0
        if "m" in wall:
            parts = wall.replace("s", "").split("m")
            wall_min = int(parts[0].strip())

        model = ", ".join(telemetry["models"]) if telemetry["models"] else "unknown"
        cost_str = compute_cost(
            telemetry["models"], telemetry,
            telemetry.get("per_model_tokens", {}), cwd,
        )
        # Extract numeric cost from "~$X.XX (...)" format
        cost_usd = 0.0
        if cost_str.startswith("~$"):
            try:
                cost_usd = float(cost_str.split("(")[0].replace("~$", "").strip())
            except (ValueError, IndexError):
                pass

        bot_name = os.environ.get("CLAUDE_BOT_NAME", "host")
        record = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cost_usd": cost_usd,
            "tokens": total_tokens,
            "wall_min": wall_min,
            "model": model,
            "bot": bot_name,
            "api_calls": telemetry["api_calls"],
            "tool_calls": telemetry["tool_calls"],
        }

        log_path = Path(cwd) / "tmp" / "usage-log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        print(f"[HOOK] Usage record appended to {log_path}")
    except Exception:
        pass  # Best-effort -- don't block session shutdown


# ---------------------------------------------------------------------------
# Transcript retention
# ---------------------------------------------------------------------------

def _prune_old_transcripts(telemetry_dir: Path) -> None:
    """Remove old transcript copies to prevent unbounded disk growth.

    Two passes:
    1. Delete transcript.jsonl files older than TRANSCRIPT_MAX_AGE_DAYS.
    2. If more than TRANSCRIPT_MAX_COUNT transcript.jsonl files remain,
       delete the oldest until only TRANSCRIPT_MAX_COUNT remain.

    Only deletes transcript.jsonl -- telemetry-comment.md is small and
    kept for historical reference.
    """
    try:
        transcript_files = sorted(
            telemetry_dir.glob("*/transcript.jsonl"),
            key=lambda p: p.stat().st_mtime,
        )
    except OSError:
        return

    now = datetime.now(timezone.utc).timestamp()
    max_age_secs = TRANSCRIPT_MAX_AGE_DAYS * 86400
    kept: list[Path] = []

    # Pass 1: age-based pruning
    for tf in transcript_files:
        try:
            age = now - tf.stat().st_mtime
            if age > max_age_secs:
                tf.unlink()
                print(f"[HOOK] Pruned old transcript: {tf.parent.name} ({age / 86400:.0f}d old)")
            else:
                kept.append(tf)
        except OSError:
            kept.append(tf)

    # Pass 2: count-based cap
    if len(kept) > TRANSCRIPT_MAX_COUNT:
        to_remove = kept[: len(kept) - TRANSCRIPT_MAX_COUNT]
        for tf in to_remove:
            try:
                tf.unlink()
                print(f"[HOOK] Pruned excess transcript: {tf.parent.name}")
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    session_id = data.get("session_id", "unknown")
    transcript_path = data.get("transcript_path", "")
    cwd = data.get("cwd", os.getcwd())

    if not transcript_path or not os.path.isfile(transcript_path):
        print("[HOOK] No transcript file found, skipping telemetry.", file=sys.stderr)
        return

    # Parse transcript
    telemetry = parse_transcript(transcript_path)

    # Skip if transcript was empty (no API calls made)
    if telemetry["api_calls"] == 0:
        print("[HOOK] Empty transcript (no API calls), skipping.", file=sys.stderr)
        return

    # Parse subagent transcripts
    subagent_data = parse_subagent_transcripts(transcript_path)

    # Format comment
    comment = format_comment(session_id, telemetry, subagent_data, cwd)

    # Write to file
    out_dir = Path(cwd) / "tmp" / "session-telemetry" / session_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "telemetry-comment.md"
    out_file.write_text(comment, encoding="utf-8")
    print(f"[HOOK] Telemetry written to {out_file}")

    # Copy raw transcript for later analysis by /token-hygiene
    try:
        transcript_copy = out_dir / "transcript.jsonl"
        shutil.copy2(transcript_path, transcript_copy)
        print(f"[HOOK] Transcript copied to {transcript_copy}")
    except OSError as exc:
        print(f"[HOOK] Failed to copy transcript: {exc}", file=sys.stderr)

    # Prune old transcripts to prevent unbounded disk growth
    _prune_old_transcripts(Path(cwd) / "tmp" / "session-telemetry")

    # Append to usage log for rolling cost tracking
    _append_usage_log(session_id, telemetry, cwd)

    # Find issue and post
    issue_num = find_issue_number(cwd)
    if not issue_num:
        print("[HOOK] No session issue found, skipping post.", file=sys.stderr)
        return

    post_comment(issue_num, session_id, str(out_file), cwd)


try:
    main()
except Exception:
    import traceback
    traceback.print_exc(file=sys.stderr)
