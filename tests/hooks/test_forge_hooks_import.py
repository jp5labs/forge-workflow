"""Smoke tests: verify all forge_workflow.hooks.* modules are importable.

These tests ensure the `python -m forge_workflow.hooks.<name>` invocation
path works — a syntax or import error in any module would surface here
rather than at runtime in autonomous mode.
"""

import importlib
import subprocess
import sys

import pytest

# Every hook module that must be importable
HOOK_MODULES = [
    "forge_workflow.hooks.approval_logger",
    "forge_workflow.hooks.block_commit_to_main",
    "forge_workflow.hooks.circuit_breaker_init",
    "forge_workflow.hooks.compound_command_interceptor",
    "forge_workflow.hooks.dangerous_command_halt",
    "forge_workflow.hooks.destructive_git_halt",
    "forge_workflow.hooks.file_protection",
    "forge_workflow.hooks.post_assessment_to_issue",
    "forge_workflow.hooks.post_plan_to_issue",
    "forge_workflow.hooks.ruff_fix",
    "forge_workflow.hooks.secret_detection",
    "forge_workflow.hooks.secret_file_scanner",
    "forge_workflow.hooks.sequential_failure_breaker",
    "forge_workflow.hooks.session_telemetry",
    "forge_workflow.hooks.shell_expansion_guard",
]


@pytest.mark.parametrize("module_name", HOOK_MODULES)
def test_hook_module_importable(module_name):
    """Each hook module can be imported without error."""
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "main"), f"{module_name} missing main() entry point"


@pytest.mark.parametrize("module_name", HOOK_MODULES)
def test_hook_module_runnable(module_name):
    """Each hook module can be invoked via python -m with empty stdin."""
    result = subprocess.run(
        [sys.executable, "-m", module_name],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Hooks should exit 0 on empty/no input (graceful no-op)
    assert result.returncode == 0, (
        f"{module_name} exited {result.returncode}\n"
        f"stderr: {result.stderr[:500]}"
    )


def test_secret_detection_import_fallback():
    """secret_detection has a fallback if secret_file_scanner can't be imported."""
    # The import fallback is a no-op function — verify it exists
    from forge_workflow.hooks.secret_detection import escalate_secret_detection
    assert callable(escalate_secret_detection)
