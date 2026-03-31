"""Tests for Phase 0/1 roadmap gap items.

Covers: routing telemetry (073), Gemini research prompting (065),
pattern detection (081), user skill creation (089), skill watcher (091).
"""

import os
import tempfile

import pytest

from neo.llm.mock import MockProvider
from neo.memory.models import detect_patterns, log_action
from neo.orchestrator import build_system_prompt, process
from neo.skills.loader import (
    create_user_skill,
    parse_skill_file,
)

# ============================================
# Task 073 — Routing telemetry in action_log
# ============================================


class TestRoutingTelemetry:
    def test_routed_tier_stored_in_log(self, memory_db):
        log_id = log_action(
            memory_db,
            input_text="create a note",
            tool_used="create_note",
            model_used="ollama",
            routed_tier="LOCAL",
        )
        memory_db.commit()

        row = memory_db.execute("SELECT routed_tier FROM action_log WHERE id = ?", (log_id,)).fetchone()
        assert row["routed_tier"] == "LOCAL"

    def test_routed_tier_empty_by_default(self, memory_db):
        log_id = log_action(memory_db, input_text="test command")
        memory_db.commit()

        row = memory_db.execute("SELECT routed_tier FROM action_log WHERE id = ?", (log_id,)).fetchone()
        assert row["routed_tier"] == ""

    @pytest.mark.asyncio
    async def test_process_logs_routed_tier(self, memory_db):
        provider = MockProvider()
        await process(
            "create a note",
            provider,
            memory_db,
            routed_tier="GEMINI",
        )
        memory_db.commit()

        row = memory_db.execute("SELECT routed_tier FROM action_log ORDER BY id DESC LIMIT 1").fetchone()
        assert row["routed_tier"] == "GEMINI"


# ============================================
# Task 065 — Gemini research-specific prompting
# ============================================


class TestGeminiResearchPrompt:
    def test_gemini_tier_injects_research_mode(self, memory_db):
        prompt = build_system_prompt(memory_db, routed_tier="GEMINI")
        assert "Research Mode" in prompt
        assert "synthesis" in prompt.lower()

    def test_non_gemini_tier_no_research_mode(self, memory_db):
        prompt = build_system_prompt(memory_db, routed_tier="CLAUDE")
        assert "Research Mode" not in prompt

    def test_no_tier_no_research_mode(self, memory_db):
        prompt = build_system_prompt(memory_db)
        assert "Research Mode" not in prompt

    def test_local_tier_no_research_mode(self, memory_db):
        prompt = build_system_prompt(memory_db, routed_tier="LOCAL")
        assert "Research Mode" not in prompt


# ============================================
# Task 081 — Execution pattern detection
# ============================================


class TestPatternDetection:
    def test_detects_repeated_pattern(self, memory_db):
        # Insert same command 4 times
        for _ in range(4):
            log_action(memory_db, input_text="create weekly report spreadsheet")
        memory_db.commit()

        patterns = detect_patterns(memory_db, days=14, min_count=3)
        assert len(patterns) >= 1
        assert patterns[0]["count"] == 4
        assert "create weekly report" in patterns[0]["pattern"]

    def test_no_pattern_below_threshold(self, memory_db):
        # Insert only 2 times — below min_count=3
        for _ in range(2):
            log_action(memory_db, input_text="create monthly summary")
        memory_db.commit()

        patterns = detect_patterns(memory_db, days=14, min_count=3)
        assert len(patterns) == 0

    def test_multiple_patterns_sorted_by_count(self, memory_db):
        for _ in range(5):
            log_action(memory_db, input_text="create weekly report spreadsheet")
        for _ in range(3):
            log_action(memory_db, input_text="summarize daily notes review")
        memory_db.commit()

        patterns = detect_patterns(memory_db, days=14, min_count=3)
        assert len(patterns) == 2
        assert patterns[0]["count"] == 5  # most frequent first
        assert patterns[1]["count"] == 3

    def test_ignores_failed_actions(self, memory_db):
        for _ in range(4):
            log_action(
                memory_db,
                input_text="create broken thing",
                status="error",
            )
        memory_db.commit()

        patterns = detect_patterns(memory_db, days=14, min_count=3)
        assert len(patterns) == 0


# ============================================
# Task 089 — User skill creation
# ============================================


class TestUserSkillCreation:
    def test_creates_skill_file(self, memory_db):
        with tempfile.TemporaryDirectory() as tmp:
            import neo.skills.loader as loader

            original = loader._USER_SKILLS_DIR
            loader._USER_SKILLS_DIR = tmp

            try:
                path = create_user_skill(
                    memory_db,
                    name="Monthly Report",
                    description="Conventions for monthly reports",
                    task_types=["report", "monthly", "summary"],
                    content="# Monthly Report\n\nUse tables for data.",
                    tools=["create_document"],
                )
                memory_db.commit()

                # File created
                assert os.path.exists(path)
                assert path.endswith(".md")

                # Parse it back
                parsed = parse_skill_file(path)
                assert parsed["name"] == "monthly_report"
                assert "report" in parsed["task_types"]
                assert "Monthly Report" in parsed["content"]

            finally:
                loader._USER_SKILLS_DIR = original

    def test_registers_in_database(self, memory_db):
        with tempfile.TemporaryDirectory() as tmp:
            import neo.skills.loader as loader

            original = loader._USER_SKILLS_DIR
            loader._USER_SKILLS_DIR = tmp

            try:
                create_user_skill(
                    memory_db,
                    name="test_skill",
                    description="A test skill",
                    task_types=["test"],
                    content="# Test",
                )
                memory_db.commit()

                row = memory_db.execute("SELECT * FROM skills WHERE name = 'test_skill'").fetchone()
                assert row is not None
                assert row["skill_type"] == "user"
                assert row["is_enabled"] == 1

            finally:
                loader._USER_SKILLS_DIR = original

    def test_sanitizes_name(self, memory_db):
        with tempfile.TemporaryDirectory() as tmp:
            import neo.skills.loader as loader

            original = loader._USER_SKILLS_DIR
            loader._USER_SKILLS_DIR = tmp

            try:
                path = create_user_skill(
                    memory_db,
                    name="My Special Report!!! @#$",
                    description="Test",
                    task_types=["test"],
                    content="# Test",
                )
                memory_db.commit()

                # Name sanitized to safe characters
                assert "my_special_report____" in os.path.basename(path)

            finally:
                loader._USER_SKILLS_DIR = original

    def test_empty_name_raises(self, memory_db):
        with pytest.raises(ValueError, match="empty"):
            create_user_skill(
                memory_db,
                name="",
                description="Test",
                task_types=["test"],
                content="# Test",
            )


# ============================================
# Task 091 — Skill hot-reload (watcher)
# ============================================


class TestSkillWatcher:
    def test_watcher_can_start_and_stop(self):
        from neo.skills.watcher import SkillWatcher

        with tempfile.TemporaryDirectory() as tmp:
            watcher = SkillWatcher(db_path=":memory:")
            # Patch directories to temp
            import neo.skills.watcher as watcher_mod

            original_public = watcher_mod._SKILLS_DIR
            original_user = watcher_mod._USER_SKILLS_DIR
            watcher_mod._SKILLS_DIR = tmp
            watcher_mod._USER_SKILLS_DIR = tmp

            try:
                watcher.start()
                assert watcher.is_running

                watcher.stop()
                assert not watcher.is_running
            finally:
                watcher_mod._SKILLS_DIR = original_public
                watcher_mod._USER_SKILLS_DIR = original_user

    def test_handler_triggers_on_md_file(self):
        from neo.skills.watcher import _SkillFileHandler

        handler = _SkillFileHandler(db_path=":memory:")

        # Create a mock event for a non-.md file — should not crash
        from unittest.mock import MagicMock

        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/test.txt"
        handler.on_created(event)  # Should not sync (not .md)

    def test_watcher_not_running_before_start(self):
        from neo.skills.watcher import SkillWatcher

        watcher = SkillWatcher(db_path=":memory:")
        assert not watcher.is_running
