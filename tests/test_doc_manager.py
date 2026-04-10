"""Tests for forge_workflow.lib.doc_manager."""

from __future__ import annotations

import yaml

from forge_workflow.cli.doctor import _check_managed_docs
from forge_workflow.lib.bot_config import BotEntry, add_bot, remove_bot
from forge_workflow.lib.doc_manager import find_section, upsert_section
from forge_workflow.lib.doc_sections import (
    render_agents_bot_fleet,
    render_claude_remote_sessions,
    render_workflow_choreography,
)
from forge_workflow.lib.scaffold import scaffold_docs

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


class TestRenderClaudeBotIdentity:

    def test_renders_identity_section(self):
        from forge_workflow.lib.doc_sections import render_claude_bot_identity

        result = render_claude_bot_identity([])
        assert "Bot Identity" in result
        assert "append-system-prompt-file" in result
        assert "bots/{name}-identity.md" in result


class TestRenderAgentsModeTable:

    def test_renders_mode_table_with_bots(self):
        from forge_workflow.lib.doc_sections import render_agents_mode_table

        bots = [
            BotEntry(
                name="marcus",
                role="Architecture",
                github_account="marcus-vale",
                email="m@x.com",
            ),
        ]
        result = render_agents_mode_table(bots)
        assert "autonomous" in result
        assert "supervised" in result
        assert "forge bot launch marcus" in result

    def test_renders_mode_table_without_bots(self):
        from forge_workflow.lib.doc_sections import render_agents_mode_table

        result = render_agents_mode_table([])
        assert "forge bot launch <name>" in result


class TestRenderAgentsAutonomousDetail:

    def test_renders_autonomous_detail(self):
        from forge_workflow.lib.doc_sections import render_agents_autonomous_detail

        result = render_agents_autonomous_detail([])
        assert "### Autonomous Mode Detail" in result
        assert "--dangerously-skip-permissions" in result
        assert "CLAUDE_MODE" in result
        assert "CB_FAILURE_LIMIT" in result

    def test_describes_hook_categories(self):
        from forge_workflow.lib.doc_sections import render_agents_autonomous_detail

        result = render_agents_autonomous_detail([])
        assert "Circuit breaker" in result or "circuit breaker" in result
        assert "block_commit_to_main" in result
        assert "destructive_git_halt" in result
        assert "sequential_failure_breaker" in result
        assert "secret_detection" in result


class TestUpsertDocSections:

    def test_upserts_multiple_sections(self, tmp_path):
        from forge_workflow.lib.doc_manager import upsert_doc_sections

        md_file = tmp_path / "test.md"
        md_file.write_text("# Doc\n\nContent.\n")
        modified = upsert_doc_sections(
            md_file,
            {
                "section-a": "A content\n",
                "section-b": "B content\n",
            },
        )
        assert modified
        content = md_file.read_text()
        assert "<!-- forge:section-a:start -->" in content
        assert "A content" in content
        assert "<!-- forge:section-b:start -->" in content
        assert "B content" in content
        assert "Content." in content


# --- scaffold_docs tests ---



class TestScaffoldDocs:

    def test_updates_existing_claude_md(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# My Project\n\nCustom content.\n")
        result = scaffold_docs(tmp_path, bots=[])
        assert result["claude_md"]
        content = claude_md.read_text()
        assert "<!-- forge:remote-sessions:start -->" in content
        assert "<!-- forge:workflow:start -->" in content
        assert "Custom content." in content

    def test_updates_existing_agents_md(self, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# Agents\n\nCustom rules.\n")
        result = scaffold_docs(tmp_path, bots=[])
        assert result["agents_md"]
        content = agents_md.read_text()
        assert "<!-- forge:bot-fleet:start -->" in content
        assert "<!-- forge:autonomous-detail:start -->" in content
        assert "<!-- forge:gate-policy:start -->" in content
        assert "Custom rules." in content

    def test_skips_missing_files(self, tmp_path):
        result = scaffold_docs(tmp_path, bots=[])
        assert not result["claude_md"]
        assert not result["agents_md"]

    def test_includes_bots_in_tables(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project\n")
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# Agents\n")
        bots = [
            BotEntry(
                name="marcus",
                role="Architecture",
                github_account="marcus-vale",
                email="m@x.com",
            ),
        ]
        scaffold_docs(tmp_path, bots=bots)
        assert "Marcus" in claude_md.read_text()
        assert "Marcus" in agents_md.read_text()


# --- bot add/remove doc update tests ---




class TestBotAddRemoveDocUpdates:

    def _setup_repo(self, tmp_path):
        """Create a minimal forge repo with CLAUDE.md and AGENTS.md."""
        forge_dir = tmp_path / ".forge"
        forge_dir.mkdir()
        config = {
            "forge": {"version": 1},
            "repo": {"org": "test", "name": "repo"},
            "bots": [],
        }
        with open(forge_dir / "config.yaml", "w") as f:
            yaml.dump(config, f)
        (tmp_path / "CLAUDE.md").write_text("# Project\n")
        (tmp_path / "AGENTS.md").write_text("# Agents\n")
        return tmp_path

    def test_bot_add_updates_docs(self, tmp_path):
        root = self._setup_repo(tmp_path)
        add_bot(
            root,
            name="marcus",
            role="Architecture",
            github_account="marcus-vale",
            email="m@x.com",
        )
        claude = (root / "CLAUDE.md").read_text()
        assert "Marcus" in claude
        assert "forge bot launch marcus" in claude

        agents = (root / "AGENTS.md").read_text()
        assert "Marcus" in agents
        assert "marcus-vale" in agents

    def test_bot_remove_updates_docs(self, tmp_path):
        root = self._setup_repo(tmp_path)
        add_bot(
            root,
            name="marcus",
            role="Architecture",
            github_account="marcus-vale",
            email="m@x.com",
        )
        remove_bot(root, "marcus")
        claude = (root / "CLAUDE.md").read_text()
        assert "Marcus" not in claude

        agents = (root / "AGENTS.md").read_text()
        assert "Marcus" not in agents


# --- doctor check tests ---



class TestDoctorManagedDocs:

    def test_passes_when_sections_present(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "# Project\n\n"
            "<!-- forge:remote-sessions:start -->\nsessions\n"
            "<!-- forge:remote-sessions:end -->\n"
            "<!-- forge:bot-identity:start -->\nidentity\n"
            "<!-- forge:bot-identity:end -->\n"
            "<!-- forge:workflow:start -->\ncontent\n"
            "<!-- forge:workflow:end -->\n"
        )
        issues = _check_managed_docs(tmp_path)
        assert len(issues) == 0

    def test_warns_when_claude_md_missing_sections(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project\n")
        issues = _check_managed_docs(tmp_path)
        assert any("CLAUDE.md" in i for i in issues)

    def test_skips_when_file_missing(self, tmp_path):
        issues = _check_managed_docs(tmp_path)
        assert len(issues) == 0

    def test_passes_when_agents_md_sections_present(self, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(
            "# Agents\n\n"
            "<!-- forge:bot-fleet:start -->\nfleet\n"
            "<!-- forge:bot-fleet:end -->\n"
            "<!-- forge:bot-identity:start -->\nidentity\n"
            "<!-- forge:bot-identity:end -->\n"
            "<!-- forge:mode:start -->\nmode\n"
            "<!-- forge:mode:end -->\n"
            "<!-- forge:autonomous-detail:start -->\ndetail\n"
            "<!-- forge:autonomous-detail:end -->\n"
            "<!-- forge:gate-policy:start -->\npolicy\n"
            "<!-- forge:gate-policy:end -->\n"
            "<!-- forge:workflow:start -->\nworkflow\n"
            "<!-- forge:workflow:end -->\n"
        )
        issues = _check_managed_docs(tmp_path)
        assert len(issues) == 0

    def test_warns_when_agents_md_missing_new_sections(self, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text(
            "# Agents\n\n"
            "<!-- forge:bot-fleet:start -->\nfleet\n"
            "<!-- forge:bot-fleet:end -->\n"
            "<!-- forge:bot-identity:start -->\nidentity\n"
            "<!-- forge:bot-identity:end -->\n"
            "<!-- forge:mode:start -->\nmode\n"
            "<!-- forge:mode:end -->\n"
            "<!-- forge:workflow:start -->\nworkflow\n"
            "<!-- forge:workflow:end -->\n"
        )
        issues = _check_managed_docs(tmp_path)
        assert any("autonomous-detail" in i for i in issues)
        assert any("gate-policy" in i for i in issues)


class TestRenderAgentsGatePolicy:

    def test_renders_gate_policy_table(self):
        from forge_workflow.lib.doc_sections import render_agents_gate_policy

        result = render_agents_gate_policy([])
        assert "### Autonomous Gate Policy" in result
        assert "forge-discover" in result
        assert "forge-assess" in result
        assert "forge-plan" in result
        assert "forge-shape" in result
        assert "forge-deliver" in result
        assert "forge-spec" in result
        assert "forge-start" in result
        assert "forge-cleanup" in result

    def test_renders_override_mechanisms(self):
        from forge_workflow.lib.doc_sections import render_agents_gate_policy

        result = render_agents_gate_policy([])
        assert "needs-human-gate" in result
        assert "halt" in result.lower()

    def test_renders_fail_safe_defaults(self):
        from forge_workflow.lib.doc_sections import render_agents_gate_policy

        result = render_agents_gate_policy([])
        assert "API error" in result or "API errors" in result
        assert "unset mode" in result or "unset" in result
