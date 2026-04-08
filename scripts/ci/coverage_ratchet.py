"""Coverage ratchet gate — fail if coverage decreases from baseline.

Supports two modes:
  1. Global threshold: overall branch coverage must not drop below baseline.
  2. Per-module floors: individual modules can have minimum coverage requirements.

PRs labeled ``code-port`` are allowed to temporarily step down the global
threshold.  The new (lower) coverage becomes the baseline on merge, and a
warning is emitted reminding the team to file a follow-up issue.

Usage:
    python scripts/ci/coverage_ratchet.py [options]

Exit codes:
    0  All gates pass
    1  Coverage gate failed
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# Allow coverage to fluctuate slightly across CI environments without failing.
GRACE_PCT = 1.5


def _get_pr_labels() -> list[str]:
    """Retrieve PR labels from the GitHub event payload or environment."""
    # In CI, GITHUB_EVENT_PATH points to the event JSON
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if event_path and Path(event_path).exists():
        try:
            with open(event_path) as f:
                event = json.load(f)
            pr = event.get("pull_request", {})
            return [lbl["name"] for lbl in pr.get("labels", [])]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # Fallback: use gh CLI if available
    pr_number = os.environ.get("PR_NUMBER", "")
    if pr_number:
        try:
            result = subprocess.run(
                ["gh", "pr", "view", pr_number, "--json", "labels", "-q", ".labels[].name"],
                capture_output=True, text=True, check=False,
            )
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        except FileNotFoundError:
            pass

    return []


def _check_module_floors(
    coverage_data: dict,
    baseline_data: dict,
) -> list[str]:
    """Check per-module coverage floors.

    Returns a list of failure messages (empty = all passed).
    """
    floors = baseline_data.get("module_floors", {})
    if not floors:
        return []

    files = coverage_data.get("files", {})
    failures: list[str] = []

    for module_path, min_pct in floors.items():
        # Match files that start with the module path
        matching_stmts = 0
        matching_covered = 0
        matching_branches = 0
        matching_branches_covered = 0

        for file_path, file_data in files.items():
            if file_path.startswith(module_path):
                summary = file_data.get("summary", {})
                matching_stmts += summary.get("num_statements", 0)
                matching_covered += summary.get("covered_lines", 0)
                matching_branches += summary.get("num_branches", 0)
                matching_branches_covered += summary.get("covered_branches", 0)

        if matching_stmts == 0:
            # Module not found in coverage data — skip (may be new/empty)
            continue

        total = matching_stmts + matching_branches
        covered = matching_covered + matching_branches_covered
        pct = round((covered / total) * 100, 1) if total > 0 else 0.0

        if pct < min_pct - GRACE_PCT:
            failures.append(
                f"  {module_path}: {pct}% < {min_pct}% floor"
            )
        else:
            print(f"  {module_path}: {pct}% (floor: {min_pct}%) — OK")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Coverage ratchet gate")
    parser.add_argument(
        "--coverage-json",
        default="tmp/coverage.json",
        help="Path to pytest-cov JSON output (default: tmp/coverage.json)",
    )
    parser.add_argument(
        "--baseline",
        default=".coverage-baseline.json",
        help="Path to baseline file (default: .coverage-baseline.json)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update baseline to current coverage (run on main after merge)",
    )
    args = parser.parse_args()

    # Read current coverage
    coverage_path = Path(args.coverage_json)
    if not coverage_path.exists():
        print(f"ERROR: Coverage report not found: {coverage_path}", file=sys.stderr)
        return 1

    try:
        with coverage_path.open() as f:
            coverage_data = json.load(f)
        current = coverage_data["totals"]["percent_covered"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"ERROR: Failed to parse coverage report {coverage_path}: {e}", file=sys.stderr)
        return 1
    current = round(current, 1)

    # Read baseline
    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        print(f"WARNING: No baseline file found at {baseline_path}. Creating with current coverage.")
        _write_baseline(baseline_path, current)
        print(f"Coverage: {current}% (baseline created)")
        return 0

    try:
        with baseline_path.open() as f:
            baseline_data = json.load(f)
        threshold = baseline_data["threshold"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"ERROR: Failed to parse baseline {baseline_path}: {e}", file=sys.stderr)
        return 1

    # --- Per-module floor checks ---
    print("--- Per-module coverage floors ---")
    module_failures = _check_module_floors(coverage_data, baseline_data)
    if module_failures:
        print("FAIL: Module coverage floors not met:", file=sys.stderr)
        for msg in module_failures:
            print(msg, file=sys.stderr)
        return 1
    if not baseline_data.get("module_floors"):
        print("  (none configured)")
    print()

    # --- Global threshold check ---
    print(f"Coverage: {current}% (baseline: {threshold}%)")

    if current < threshold - GRACE_PCT:
        delta = round(threshold - current, 1)

        # On main (push event), allow step-down — the PR already passed the
        # gate with the code-port label.  The update-baseline job will
        # record the new (lower) threshold.
        is_main_push = os.environ.get("GITHUB_REF") == "refs/heads/main"
        if is_main_push or args.update:
            print(
                f"WARNING: Coverage decreased by {delta}% "
                f"({current}% < {threshold}% baseline).",
            )
            print(
                "Running with --update on main — stepping down baseline.",
            )
            _write_baseline(baseline_path, current, baseline_data)
            print(f"Baseline updated to {current}%.")
            return 0

        # Check for code-port label on PR
        labels = _get_pr_labels()
        is_code_port = "code-port" in labels

        if is_code_port:
            print(
                f"WARNING: Coverage decreased by {delta}% "
                f"({current}% < {threshold}% baseline).",
            )
            print(
                "PR has 'code-port' label — step-down allowed. "
                "File a follow-up issue to restore coverage.",
            )
            print(
                f"New baseline will be {current}% after merge.",
            )
            # Pass — the update-baseline job will lower the threshold on merge
            return 0

        print(
            f"FAIL: Coverage decreased by {delta}% "
            f"({current}% < {threshold}% baseline).",
            file=sys.stderr,
        )
        print(
            "Add tests to restore coverage, or add the 'code-port' label "
            "to allow a temporary step-down.",
            file=sys.stderr,
        )
        return 1

    if current > threshold:
        delta = round(current - threshold, 1)
        print(f"Coverage increased by {delta}% — nice work.")

    if args.update and current >= threshold:
        _write_baseline(baseline_path, current, baseline_data)
        print(f"Baseline updated to {current}%.")

    return 0


def _write_baseline(
    path: Path,
    threshold: float,
    existing: dict | None = None,
) -> None:
    """Write the baseline file, preserving module_floors if present."""
    from datetime import date

    data: dict = {
        "threshold": threshold,
        "updated": str(date.today()),
        "note": (
            "Branch coverage for jp5_cli/ and forge_workflow/. Global threshold must not decrease "
            "unless PR has the 'code-port' label. Per-module floors are enforced "
            "independently. Safety-critical hooks have elevated floors to prevent regression."
        ),
    }

    # Preserve module_floors from existing baseline
    if existing and "module_floors" in existing:
        data["module_floors"] = existing["module_floors"]

    path.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
