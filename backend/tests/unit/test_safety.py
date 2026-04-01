"""Tests for neo.automations.safety — 5 safety rules."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from neo.automations.safety import (
    DESTRUCTIVE_ACTIONS,
    check_api_key_available,
    get_pending_confirmations,
    handle_failure,
    is_destructive,
    is_globally_paused,
    log_after_execution,
    log_before_execution,
    request_confirmation,
    resolve_confirmation,
    set_global_pause,
)


# ---------------------------------------------------------------------------
# Rule 1 — Destructive detection
# ---------------------------------------------------------------------------


class TestIsDestructive:
    def test_direct_destructive_actions(self):
        for action in DESTRUCTIVE_ACTIONS:
            assert is_destructive(action) is True

    def test_case_insensitive(self):
        assert is_destructive("DELETE") is True
        assert is_destructive("Send_Email") is True

    def test_non_destructive_action(self):
        assert is_destructive("create") is False
        assert is_destructive("list") is False
        assert is_destructive("read") is False

    def test_manage_file_delete_is_destructive(self):
        assert is_destructive("run", tool_name="manage_file", tool_input={"action": "delete"}) is True

    def test_manage_file_copy_not_destructive(self):
        assert is_destructive("run", tool_name="manage_file", tool_input={"action": "copy"}) is False

    def test_send_email_tool_is_destructive(self):
        assert is_destructive("run", tool_name="send_email") is True

    def test_reply_to_tool_is_destructive(self):
        assert is_destructive("run", tool_name="reply_to") is True

    def test_fill_form_tool_is_destructive(self):
        assert is_destructive("run", tool_name="fill_form") is True

    def test_browse_url_not_destructive(self):
        assert is_destructive("run", tool_name="browse_url") is False


# ---------------------------------------------------------------------------
# Rule 1 — Confirmation flow
# ---------------------------------------------------------------------------


class TestConfirmation:
    @pytest.mark.asyncio
    async def test_confirmation_approved(self):
        """Approved confirmation returns True."""
        async def approve_soon():
            await asyncio.sleep(0.05)
            pending = get_pending_confirmations()
            assert len(pending) == 1
            resolve_confirmation(pending[0]["id"], approved=True)

        task = asyncio.create_task(approve_soon())
        result = await request_confirmation("Delete file?", automation_id=1, timeout_s=2.0)
        await task
        assert result is True

    @pytest.mark.asyncio
    async def test_confirmation_denied(self):
        """Denied confirmation returns False."""
        async def deny_soon():
            await asyncio.sleep(0.05)
            pending = get_pending_confirmations()
            assert len(pending) == 1
            resolve_confirmation(pending[0]["id"], approved=False)

        task = asyncio.create_task(deny_soon())
        result = await request_confirmation("Send email?", automation_id=2, timeout_s=2.0)
        await task
        assert result is False

    @pytest.mark.asyncio
    async def test_confirmation_timeout(self):
        """Timeout returns False and cleans up pending."""
        result = await request_confirmation("Risky action", automation_id=3, timeout_s=0.1)
        assert result is False
        assert len(get_pending_confirmations()) == 0

    @pytest.mark.asyncio
    async def test_confirmation_notify_callback(self):
        """Notify callback receives the correct event data."""
        callback = MagicMock()

        async def approve_soon():
            await asyncio.sleep(0.05)
            pending = get_pending_confirmations()
            resolve_confirmation(pending[0]["id"], approved=True)

        task = asyncio.create_task(approve_soon())
        await request_confirmation("Test", automation_id=5, timeout_s=2.0, notify_callback=callback)
        await task

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event["type"] == "confirmation_request"
        assert event["automation_id"] == 5
        assert event["action_description"] == "Test"

    def test_resolve_nonexistent_confirmation(self):
        """Resolving a non-existent confirmation returns False."""
        assert resolve_confirmation("nonexistent-id", approved=True) is False

    @pytest.mark.asyncio
    async def test_pending_cleaned_up_after_resolution(self):
        """After resolution, pending list is empty."""
        async def approve():
            await asyncio.sleep(0.05)
            pending = get_pending_confirmations()
            resolve_confirmation(pending[0]["id"], approved=True)

        task = asyncio.create_task(approve())
        await request_confirmation("Test cleanup", timeout_s=2.0)
        await task
        assert len(get_pending_confirmations()) == 0


# ---------------------------------------------------------------------------
# Rule 2 — Before/after logging
# ---------------------------------------------------------------------------


class TestLogging:
    def test_log_before_execution(self, memory_db):
        log_id = log_before_execution(memory_db, automation_id=1, command="check email")
        assert log_id > 0

        row = memory_db.execute("SELECT * FROM action_log WHERE id = ?", (log_id,)).fetchone()
        assert row is not None
        assert dict(row)["status"] == "pending"
        assert dict(row)["input_text"] == "check email"

    def test_log_after_execution(self, memory_db):
        log_id = log_after_execution(
            memory_db,
            automation_id=1,
            command="check email",
            status="success",
            result_message="Checked 3 emails",
            duration_ms=150,
        )
        assert log_id > 0

        row = memory_db.execute("SELECT * FROM action_log WHERE id = ?", (log_id,)).fetchone()
        assert dict(row)["status"] == "success"
        assert dict(row)["duration_ms"] == 150


# ---------------------------------------------------------------------------
# Rule 3 — Failure handling
# ---------------------------------------------------------------------------


class TestFailureHandling:
    def test_first_failure_does_not_pause(self, memory_db):
        # Create an automation first
        memory_db.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("test", "schedule", "{}", "check email"),
        )
        auto_id = memory_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        paused = handle_failure(memory_db, auto_id, current_retry=0, max_retries=3)
        assert paused is False

        row = memory_db.execute("SELECT * FROM automations WHERE id = ?", (auto_id,)).fetchone()
        assert dict(row)["is_enabled"] == 1  # Still enabled

    def test_second_failure_does_not_pause(self, memory_db):
        memory_db.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("test2", "schedule", "{}", "backup"),
        )
        auto_id = memory_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        paused = handle_failure(memory_db, auto_id, current_retry=1, max_retries=3)
        assert paused is False

    def test_third_failure_pauses_automation(self, memory_db):
        memory_db.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("test3", "schedule", "{}", "send report"),
        )
        auto_id = memory_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        paused = handle_failure(memory_db, auto_id, current_retry=2, max_retries=3)
        assert paused is True

        row = memory_db.execute("SELECT * FROM automations WHERE id = ?", (auto_id,)).fetchone()
        assert dict(row)["is_enabled"] == 0  # Disabled

    def test_custom_max_retries(self, memory_db):
        memory_db.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("test4", "schedule", "{}", "sync"),
        )
        auto_id = memory_db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # With max_retries=1, first failure pauses
        paused = handle_failure(memory_db, auto_id, current_retry=0, max_retries=1)
        assert paused is True


# ---------------------------------------------------------------------------
# Rule 4 — API key guard
# ---------------------------------------------------------------------------


class TestApiKeyGuard:
    def test_local_always_available(self):
        assert check_api_key_available("LOCAL") is True

    @patch.dict("os.environ", {"CLAUDE_API_KEY": "sk-test"})
    def test_claude_available(self):
        assert check_api_key_available("CLAUDE") is True

    @patch.dict("os.environ", {}, clear=True)
    def test_claude_not_available(self):
        assert check_api_key_available("CLAUDE") is False

    @patch.dict("os.environ", {"GEMINI_API_KEY": "gm-test"})
    def test_gemini_available(self):
        assert check_api_key_available("GEMINI") is True

    @patch.dict("os.environ", {"OPENAI_API_KEY": "oa-test"})
    def test_openai_available(self):
        assert check_api_key_available("OPENAI") is True

    def test_unknown_tier_not_available(self):
        assert check_api_key_available("UNKNOWN") is False


# ---------------------------------------------------------------------------
# Rule 5 — Global pause
# ---------------------------------------------------------------------------


class TestGlobalPause:
    def setup_method(self):
        """Reset global pause before each test."""
        set_global_pause(False)

    def test_initially_not_paused(self):
        assert is_globally_paused() is False

    def test_set_paused(self):
        set_global_pause(True)
        assert is_globally_paused() is True

    def test_set_resumed(self):
        set_global_pause(True)
        set_global_pause(False)
        assert is_globally_paused() is False
