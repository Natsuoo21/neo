"""Tests for neo.automations.suggestions — Proactive intelligence."""

import sqlite3
import tempfile

import pytest

from neo.automations.suggestions import generate_suggestions, get_pending_suggestions
from neo.memory.db import get_session, init_schema
from neo.memory.models import (
    accept_suggestion,
    create_suggestion,
    dismiss_suggestion,
    get_active_suggestions,
    get_suggestion,
    has_recent_suggestion,
    log_action,
)

# ---------------------------------------------------------------------------
# Model-level CRUD tests
# ---------------------------------------------------------------------------


class TestSuggestionCRUD:
    def test_create_and_get(self, memory_db: sqlite3.Connection):
        sid = create_suggestion(memory_db, "create excel", "Automate it?", count=5, sample_input="create excel report")
        suggestion = get_suggestion(memory_db, sid)
        assert suggestion is not None
        assert suggestion["pattern"] == "create excel"
        assert suggestion["message"] == "Automate it?"
        assert suggestion["count"] == 5
        assert suggestion["dismissed"] == 0
        assert suggestion["accepted"] == 0

    def test_get_active_suggestions(self, memory_db: sqlite3.Connection):
        create_suggestion(memory_db, "pattern1", "msg1")
        create_suggestion(memory_db, "pattern2", "msg2")
        sid3 = create_suggestion(memory_db, "pattern3", "msg3")
        dismiss_suggestion(memory_db, sid3)

        active = get_active_suggestions(memory_db)
        assert len(active) == 2
        assert all(s["dismissed"] == 0 for s in active)

    def test_dismiss_suggestion(self, memory_db: sqlite3.Connection):
        sid = create_suggestion(memory_db, "pattern", "msg")
        result = dismiss_suggestion(memory_db, sid)
        assert result is True

        suggestion = get_suggestion(memory_db, sid)
        assert suggestion["dismissed"] == 1

    def test_dismiss_nonexistent(self, memory_db: sqlite3.Connection):
        result = dismiss_suggestion(memory_db, 999)
        assert result is False

    def test_accept_suggestion(self, memory_db: sqlite3.Connection):
        sid = create_suggestion(memory_db, "pattern", "msg", sample_input="do the thing")
        result = accept_suggestion(memory_db, sid)
        assert result is not None
        assert result["accepted"] == 1

    def test_accept_nonexistent(self, memory_db: sqlite3.Connection):
        result = accept_suggestion(memory_db, 999)
        assert result is None

    def test_has_recent_suggestion_true(self, memory_db: sqlite3.Connection):
        create_suggestion(memory_db, "pattern", "msg")
        assert has_recent_suggestion(memory_db, hours=24) is True

    def test_has_recent_suggestion_false(self, memory_db: sqlite3.Connection):
        assert has_recent_suggestion(memory_db, hours=24) is False


# ---------------------------------------------------------------------------
# generate_suggestions() engine
# ---------------------------------------------------------------------------


class TestGenerateSuggestions:
    @pytest.fixture
    def db_path(self) -> str:
        """Provide a temp DB path for generate_suggestions."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        path = tmp.name
        tmp.close()
        init_schema(path)
        return path

    def test_no_patterns_no_suggestions(self, db_path: str):
        result = generate_suggestions(db_path)
        assert result == []

    def test_generates_suggestion_from_pattern(self, db_path: str):
        # Create enough actions to form a pattern (min_count=4)
        with get_session(db_path) as conn:
            for _ in range(5):
                log_action(conn, input_text="create excel report", status="success")

        result = generate_suggestions(db_path)
        assert len(result) == 1
        assert "create excel" in result[0]["pattern"]
        assert result[0]["count"] >= 4

    def test_throttled_after_first_suggestion(self, db_path: str):
        with get_session(db_path) as conn:
            for _ in range(5):
                log_action(conn, input_text="create excel report", status="success")

        # First call generates a suggestion
        result1 = generate_suggestions(db_path)
        assert len(result1) == 1

        # Second call is throttled
        result2 = generate_suggestions(db_path)
        assert result2 == []

    def test_skips_dismissed_patterns(self, db_path: str):
        with get_session(db_path) as conn:
            for _ in range(5):
                log_action(conn, input_text="create excel report", status="success")

            # Create and dismiss a suggestion for this pattern
            sid = create_suggestion(conn, "create excel", "msg")
            dismiss_suggestion(conn, sid)

        result = generate_suggestions(db_path)
        assert result == []

    def test_broadcasts_suggestion(self, db_path: str):
        with get_session(db_path) as conn:
            for _ in range(5):
                log_action(conn, input_text="create excel report", status="success")

        events = []
        result = generate_suggestions(db_path, broadcast_fn=lambda e: events.append(e))
        assert len(result) == 1
        assert len(events) == 1
        assert events[0]["type"] == "suggestion"

    def test_get_pending(self, db_path: str):
        with get_session(db_path) as conn:
            create_suggestion(conn, "pattern1", "msg1")
            sid2 = create_suggestion(conn, "pattern2", "msg2")
            dismiss_suggestion(conn, sid2)

        pending = get_pending_suggestions(db_path)
        assert len(pending) == 1
        assert pending[0]["pattern"] == "pattern1"
