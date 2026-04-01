"""Tests for SQLite schema, database connection, and CRUD operations."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from neo.memory.db import get_connection, get_session, get_tables, init_schema
from neo.memory.models import (
    add_message,
    create_automation,
    create_project,
    disable_automation,
    get_actions_by_tool,
    get_active_projects,
    get_conversation,
    get_enabled_automations,
    get_enabled_skills,
    get_project,
    get_recent_actions,
    get_skill_by_task_type,
    get_stats,
    get_user_profile,
    log_action,
    update_automation_status,
    update_project,
    upsert_skill,
    upsert_user_profile,
)
from neo.memory.seed import seed_user_profile


@pytest.fixture
def db_path():
    """Provide a temporary database file path."""
    with tempfile.TemporaryDirectory() as d:
        yield os.path.join(d, "test.db")


@pytest.fixture
def conn(db_path):
    """Provide an initialized database connection."""
    init_schema(db_path)
    c = get_connection(db_path)
    yield c
    c.close()


# ============================================
# SCHEMA TESTS
# ============================================


class TestSchema:
    def test_schema_creates_all_tables(self, db_path):
        init_schema(db_path)
        tables = get_tables(db_path)
        expected = [
            "action_log", "automations", "conversations", "projects",
            "skills", "suggestions", "user_profile",
        ]
        assert sorted(tables) == expected

    def test_schema_is_idempotent(self, db_path):
        init_schema(db_path)
        init_schema(db_path)  # Run again — should not error
        tables = get_tables(db_path)
        assert len(tables) == 7

    def test_wal_mode_enabled(self, db_path):
        init_schema(db_path)
        c = get_connection(db_path)
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        c.close()

    def test_foreign_keys_enabled(self, db_path):
        init_schema(db_path)
        c = get_connection(db_path)
        fk = c.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
        c.close()


# ============================================
# SESSION CONTEXT MANAGER
# ============================================


class TestSession:
    def test_session_commits_on_success(self, db_path):
        init_schema(db_path)
        with get_session(db_path) as c:
            upsert_user_profile(c, name="Test")

        # Verify persisted after session closed
        c2 = get_connection(db_path)
        profile = get_user_profile(c2)
        assert profile["name"] == "Test"
        c2.close()

    def test_session_rollbacks_on_error(self, db_path):
        init_schema(db_path)
        try:
            with get_session(db_path) as c:
                upsert_user_profile(c, name="ShouldNotPersist")
                raise ValueError("Simulated error")
        except ValueError:
            pass

        c2 = get_connection(db_path)
        profile = get_user_profile(c2)
        assert profile is None
        c2.close()


# ============================================
# USER PROFILE CRUD
# ============================================


class TestUserProfile:
    def test_create_profile(self, conn):
        uid = upsert_user_profile(conn, name="Andre", role="Developer")
        conn.commit()
        assert uid == 1

    def test_get_profile(self, conn):
        upsert_user_profile(conn, name="Andre", role="Developer", preferences={"lang": "en"})
        conn.commit()
        profile = get_user_profile(conn)
        assert profile is not None
        assert profile["name"] == "Andre"
        assert profile["role"] == "Developer"
        prefs = json.loads(profile["preferences"])
        assert prefs["lang"] == "en"

    def test_update_profile(self, conn):
        upsert_user_profile(conn, name="Andre", role="Developer")
        conn.commit()
        upsert_user_profile(conn, name="Andre Updated", role="Senior Dev")
        conn.commit()
        profile = get_user_profile(conn)
        assert profile["name"] == "Andre Updated"
        assert profile["role"] == "Senior Dev"

    def test_get_empty_profile_returns_none(self, conn):
        profile = get_user_profile(conn)
        assert profile is None


# ============================================
# PROJECTS CRUD
# ============================================


class TestProjects:
    def test_create_project(self, conn):
        pid = create_project(conn, name="Neo", description="Personal agent")
        conn.commit()
        assert pid >= 1

    def test_get_project(self, conn):
        pid = create_project(conn, name="Neo", goals=["Ship v1.0"])
        conn.commit()
        project = get_project(conn, pid)
        assert project["name"] == "Neo"
        goals = json.loads(project["goals"])
        assert "Ship v1.0" in goals

    def test_get_active_projects(self, conn):
        create_project(conn, name="Active1")
        pid2 = create_project(conn, name="Inactive")
        update_project(conn, pid2, is_active=0)
        create_project(conn, name="Active2")
        conn.commit()
        active = get_active_projects(conn)
        names = [p["name"] for p in active]
        assert "Active1" in names
        assert "Active2" in names
        assert "Inactive" not in names

    def test_update_project(self, conn):
        pid = create_project(conn, name="Old Name")
        update_project(conn, pid, name="New Name", description="Updated")
        conn.commit()
        project = get_project(conn, pid)
        assert project["name"] == "New Name"
        assert project["description"] == "Updated"


# ============================================
# ACTION LOG CRUD
# ============================================


class TestActionLog:
    def test_log_action(self, conn):
        lid = log_action(
            conn,
            input_text="create a spreadsheet",
            tool_used="excel",
            model_used="claude",
            duration_ms=1200,
        )
        conn.commit()
        assert lid >= 1

    def test_get_recent_actions(self, conn):
        log_action(conn, input_text="cmd1", tool_used="excel")
        log_action(conn, input_text="cmd2", tool_used="obsidian")
        log_action(conn, input_text="cmd3", tool_used="excel")
        conn.commit()
        actions = get_recent_actions(conn, limit=10)
        assert len(actions) == 3

    def test_get_actions_by_tool(self, conn):
        log_action(conn, input_text="cmd1", tool_used="excel")
        log_action(conn, input_text="cmd2", tool_used="obsidian")
        log_action(conn, input_text="cmd3", tool_used="excel")
        conn.commit()
        excel_actions = get_actions_by_tool(conn, "excel")
        assert len(excel_actions) == 2


# ============================================
# SKILLS CRUD
# ============================================


class TestSkills:
    def test_upsert_skill_insert(self, conn):
        sid = upsert_skill(
            conn,
            name="Excel Spreadsheet",
            file_path="skills/public/skill_excel.md",
            skill_type="public",
            task_types=["create_spreadsheet", "edit_spreadsheet"],
        )
        conn.commit()
        assert sid >= 1

    def test_upsert_skill_update(self, conn):
        upsert_skill(conn, name="Test", file_path="old.md", skill_type="public")
        upsert_skill(conn, name="Test", file_path="new.md", skill_type="public")
        conn.commit()
        skills = get_enabled_skills(conn)
        assert len(skills) == 1
        assert skills[0]["file_path"] == "new.md"

    def test_get_skill_by_task_type(self, conn):
        upsert_skill(
            conn,
            name="Excel",
            file_path="excel.md",
            skill_type="public",
            task_types=["create_spreadsheet"],
        )
        upsert_skill(
            conn,
            name="Obsidian",
            file_path="obsidian.md",
            skill_type="public",
            task_types=["create_note"],
        )
        conn.commit()
        skill = get_skill_by_task_type(conn, "create_note")
        assert skill is not None
        assert skill["name"] == "Obsidian"

    def test_get_skill_by_task_type_not_found(self, conn):
        skill = get_skill_by_task_type(conn, "nonexistent")
        assert skill is None


# ============================================
# AUTOMATIONS CRUD
# ============================================


class TestAutomations:
    def test_create_automation(self, conn):
        aid = create_automation(
            conn,
            name="Weekly Report",
            trigger_type="schedule",
            command="create weekly report",
            trigger_config={"cron": "0 9 * * 1"},
        )
        conn.commit()
        assert aid >= 1

    def test_get_enabled_automations(self, conn):
        create_automation(conn, name="Auto1", trigger_type="schedule", command="cmd1")
        aid2 = create_automation(conn, name="Auto2", trigger_type="schedule", command="cmd2")
        disable_automation(conn, aid2)
        conn.commit()
        enabled = get_enabled_automations(conn)
        assert len(enabled) == 1
        assert enabled[0]["name"] == "Auto1"

    def test_update_automation_status(self, conn):
        aid = create_automation(conn, name="Test", trigger_type="schedule", command="cmd")
        update_automation_status(conn, aid, "success")
        conn.commit()
        autos = get_enabled_automations(conn)
        assert autos[0]["last_status"] == "success"

    def test_retry_increment(self, conn):
        aid = create_automation(conn, name="Retry", trigger_type="schedule", command="cmd")
        update_automation_status(conn, aid, "error", increment_retry=True)
        update_automation_status(conn, aid, "error", increment_retry=True)
        conn.commit()
        row = conn.execute("SELECT retry_count FROM automations WHERE id=?", (aid,)).fetchone()
        assert row["retry_count"] == 2


# ============================================
# CONVERSATIONS CRUD
# ============================================


class TestConversations:
    def test_add_and_get_messages(self, conn):
        add_message(conn, session_id="s1", role="user", content="Hello")
        add_message(conn, session_id="s1", role="assistant", content="Hi there!")
        conn.commit()
        msgs = get_conversation(conn, "s1")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_separate_sessions(self, conn):
        add_message(conn, session_id="s1", role="user", content="Session 1")
        add_message(conn, session_id="s2", role="user", content="Session 2")
        conn.commit()
        assert len(get_conversation(conn, "s1")) == 1
        assert len(get_conversation(conn, "s2")) == 1


# ============================================
# SEED DATA
# ============================================


class TestSeed:
    def test_seed_creates_profile(self, conn, monkeypatch):
        # Ensure seed uses defaults (not a local user_profile.json)
        monkeypatch.setattr("neo.memory.seed._SEED_PROFILE_PATH", Path("/nonexistent/profile.json"))
        result = seed_user_profile(conn)
        conn.commit()
        assert result is True
        profile = get_user_profile(conn)
        assert profile is not None
        assert profile["name"] == "User"  # default name

    def test_seed_does_not_overwrite(self, conn):
        upsert_user_profile(conn, name="Original")
        conn.commit()
        result = seed_user_profile(conn)
        assert result is False
        profile = get_user_profile(conn)
        assert profile["name"] == "Original"


# ============================================
# TELEMETRY STATS
# ============================================


class TestStats:
    def test_empty_stats(self, conn):
        stats = get_stats(conn, days=30)
        assert stats["total_requests"] == 0

    def test_stats_with_data(self, conn):
        log_action(conn, "test cmd 1", model_used="claude", routed_tier="CLAUDE", tokens_used=100, cost_brl=0.01)
        log_action(conn, "test cmd 2", model_used="gemini", routed_tier="GEMINI", tokens_used=50, tool_used="excel")
        log_action(conn, "test cmd 3", model_used="claude", routed_tier="CLAUDE", status="error")
        conn.commit()

        stats = get_stats(conn, days=30)
        assert stats["total_requests"] == 3
        assert stats["success_count"] == 2
        assert stats["error_count"] == 1
        assert stats["total_tokens"] == 150
        assert stats["total_cost"] == 0.01

        # Model breakdown
        assert len(stats["model_breakdown"]) == 2
        claude_entry = next(m for m in stats["model_breakdown"] if m["model_used"] == "claude")
        assert claude_entry["count"] == 2

        # Tool breakdown
        assert len(stats["tool_breakdown"]) == 1
        assert stats["tool_breakdown"][0]["tool_used"] == "excel"

        # Tier breakdown
        assert len(stats["tier_breakdown"]) == 2
