---
name: token-hygiene
description: Evaluate session token usage and produce a graded cost-reduction report with actionable recommendations
user-invocable: true
---

## Purpose

Analyze session token efficiency and produce a graded report with cost-reduction recommendations. Uses a deterministic Python analyzer for metrics computation and adds contextual judgment for recommendations.

## Trigger

Run this skill when:
- User invokes `/token-hygiene` directly
- At the end of `/forge-cleanup` when `tmp/usage-log.jsonl` exists (optional, user opts in)
- User asks about session cost, token usage, or efficiency

## Data Sources

1. **Transcript JSONL** — per-call token counts, cache rates, tool calls, stop reasons (current session)
2. **`tmp/usage-log.jsonl`** — rolling session history with cost, tokens, model, bot per session
3. **`.claude/model-costs.csv`** — per-model pricing for cost estimation

## Procedure

### Step 1 — Discover transcript path

Check for transcript data in this order:
1. If `CLAUDE_TRANSCRIPT_PATH` environment variable is set, use that
2. Look for the most recently modified `transcript.jsonl` in `tmp/session-telemetry/*/` — the SessionEnd hook copies the raw transcript here automatically
3. If no transcript is discoverable, proceed in trends-only mode

### Step 2 — Run the analyzer

Run the Python analyzer to compute deterministic metrics:

```bash
python scripts/token-hygiene.py --transcript <path> --usage-log tmp/usage-log.jsonl --model-costs .claude/model-costs.csv
```

If no transcript path was found, omit `--transcript` to run in trends-only mode:

```bash
python scripts/token-hygiene.py --usage-log tmp/usage-log.jsonl --model-costs .claude/model-costs.csv
```

The script outputs structured JSON to stdout. Read and parse this output.

### Step 3 — Generate the card-based report

Transform the analyzer JSON into a stacked card report. Follow this format exactly:

**Header:**
```
## Token Hygiene Report
Session cost: ~$X.XX | Tokens: X.XM | Grade: X
Mode: full analysis / trends only
```

**Passing dimensions (A grade) — collapse into one line:**
```
Passing: Model Routing (A) | Stop Reasons (A) | ...
```

**Dimensions needing attention (B grade or worse) — one card each:**

```
### N. [Dimension Name]
**Grade:** X — [label from analyzer]
**Metric:** [metric_display from analyzer]
**Impact:** ~$X.XX in potential savings
**Recommendation:** [Contextual recommendation — see guidance below]
**How to apply:** [Specific action with copy-paste snippet if applicable]
```

**Recommendation guidance per dimension:**

- **Cache efficiency:** "Batch related file reads by feature area. Group tool calls that read from the same subsystem together instead of interleaving with unrelated operations."
- **Model routing:** "Add `model: haiku` to Explore subagent frontmatter, or pass `model=\"haiku\"` in Agent() calls for research tasks." Include the exact snippet:
  ```
  Agent(subagent_type="Explore", model="haiku", prompt="...")
  ```
- **Subagent overhead:** "Batch multiple search queries into a single Explore agent prompt instead of spawning separate agents for each query."
- **Tool efficiency:** List each flagged pattern with its alternative. E.g.: "Use `Read(file_path, offset=X, limit=Y)` instead of full-file reads. Use the `Grep` tool instead of `Bash(grep ...)`."
- **Context bloat:** "Context is growing faster than expected. Consider spawning implementation as a subagent to preserve main session context. Use `tmp/` files to pass state across phases."
- **Stop reasons:** "Output was truncated N times at max_tokens. This wastes compute on truncated + retried output. Break complex responses into smaller steps."
- **Session fragmentation:** "N clusters of short sessions (<5 min) detected. Each restart pays a cache cold-start penalty. Combine related tasks into fewer, longer sessions."
- **Cost trajectory:** "7-day average is $X.XX/session, up N% from prior week. [Include per-bot breakdown from trends data.]"

**Historical trends section (when trends data exists):**

```
### Cost Trend (last 7 days)
Sessions: N | Total: $X.XX | Avg: $X.XX/session
Highest: $X.XX (session XXXX..., Xmin, X.XM tokens)
Lowest: $X.XX (session XXXX..., Xmin)

Bot breakdown:
- botname: N sessions, $X.XX (avg $X.XX)
```

**Summary footer:**
```
### Summary
Total potential savings: ~$X.XX (X% of session cost)
Top actions:
1. [Most impactful recommendation from top_recommendations] (~$X.XX)
2. [Second] (~$X.XX)
3. [Third] (~$X.XX)
```

### Step 4 — Write the report artifact

Write the rendered report to `tmp/session-telemetry/token-hygiene-report.md` using the Write tool.

### Step 5 — Present to user

Display the full report in the console. The card format is already narrow-screen compatible for Discord and terminal.
