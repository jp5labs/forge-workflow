"""Tests for forge_workflow.lib.doc_manager."""

from __future__ import annotations

from forge_workflow.lib.doc_manager import find_section, upsert_section

SAMPLE_DOC = """# My Doc

Some intro text.

<!-- forge:bot-fleet:start -->
Old fleet content
<!-- forge:bot-fleet:end -->

Some outro text.
"""


class TestFindSection:
    """Tests for finding marker-bounded sections."""

    def test_finds_existing_section(self):
        result = find_section(SAMPLE_DOC, "bot-fleet")
        assert result is not None
        assert result == "Old fleet content\n"

    def test_returns_none_for_missing_section(self):
        result = find_section(SAMPLE_DOC, "nonexistent")
        assert result is None

    def test_finds_section_in_empty_markers(self):
        doc = "<!-- forge:empty:start -->\n<!-- forge:empty:end -->\n"
        result = find_section(doc, "empty")
        assert result == ""


class TestUpsertSection:
    """Tests for inserting or updating marker-bounded sections."""

    def test_replaces_existing_section(self):
        result = upsert_section(SAMPLE_DOC, "bot-fleet", "New fleet content\n")
        assert "New fleet content" in result
        assert "Old fleet content" not in result
        assert "Some intro text." in result
        assert "Some outro text." in result

    def test_appends_section_when_markers_absent(self):
        doc = "# My Doc\n\nSome content.\n"
        result = upsert_section(doc, "bot-fleet", "Fleet table\n")
        assert "<!-- forge:bot-fleet:start -->" in result
        assert "Fleet table" in result
        assert "<!-- forge:bot-fleet:end -->" in result
        assert "Some content." in result

    def test_preserves_surrounding_content(self):
        result = upsert_section(SAMPLE_DOC, "bot-fleet", "Updated\n")
        lines = result.strip().split("\n")
        assert lines[0] == "# My Doc"
        assert "Some intro text." in result
        assert "Some outro text." in result

    def test_idempotent_on_same_content(self):
        result1 = upsert_section(SAMPLE_DOC, "bot-fleet", "Same\n")
        result2 = upsert_section(result1, "bot-fleet", "Same\n")
        assert result1 == result2

    def test_handles_multiple_sections(self):
        doc = (
            "<!-- forge:section-a:start -->\nA\n"
            "<!-- forge:section-a:end -->\n\n"
            "Middle\n\n"
            "<!-- forge:section-b:start -->\nB\n"
            "<!-- forge:section-b:end -->\n"
        )
        result = upsert_section(doc, "section-a", "A-updated\n")
        assert "A-updated" in result
        assert "B" in result
        assert "Middle" in result


# --- Section renderer tests ---

from forge_workflow.lib.doc_sections import (
    render_agents_bot_fleet,
    render_claude_remote_sessions,
    render_workflow_choreography,
)

from forge_workflow.lib.bot_config import BotEntry


class TestRenderClaudeRemoteSessions:

    def test_renders_table_with_bots(self):
        bots = [
            BotEntry(
                name="marcus",
                role="Architecture",
                github_account="marcus-vale",
                email="m@x.com",
            ),
            BotEntry(
                name="alex",
                role="Implementation",
                github_account="alexnova-dev",
                email="a@x.com",
            ),
        ]
        result = render_claude_remote_sessions(bots)
        assert "| Marcus |" in result
        assert "forge bot launch marcus" in result
        assert "claude-marcus" in result
        assert "| Generic |" in result

    def test_renders_empty_table_without_bots(self):
        result = render_claude_remote_sessions([])
        assert "| Generic |" in result
        assert "forge bot launch" in result


class TestRenderWorkflowChoreography:

    def test_renders_workflow_modes(self):
        result = render_workflow_choreography()
        assert "full" in result
        assert "standard" in result
        assert "quick" in result
        assert "ship" in result

    def test_renders_skill_reference_table(self):
        result = render_workflow_choreography()
        assert "forge-deliver" in result
        assert "forge-plan" in result
        assert "forge-discover" in result


class TestRenderAgentsBotFleet:

    def test_renders_fleet_table(self):
        bots = [
            BotEntry(
                name="marcus",
                role="Architecture",
                github_account="marcus-vale",
                email="m@x.com",
            ),
        ]
        result = render_agents_bot_fleet(bots)
        assert "| Marcus |" in result
        assert "claude-marcus" in result
        assert "marcus-vale" in result
        assert "Architecture" in result
