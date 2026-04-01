"""Tests for neo.automations.watcher — file system monitoring."""

import json
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neo.automations.watcher import DebouncedHandler, NeoFileWatcher


# ---------------------------------------------------------------------------
# Mock events
# ---------------------------------------------------------------------------


class FakeEvent:
    """Minimal fake watchdog event."""

    def __init__(self, src_path: str, event_type: str = "created", is_directory: bool = False):
        self.src_path = src_path
        self.event_type = event_type
        self.is_directory = is_directory


# ---------------------------------------------------------------------------
# DebouncedHandler tests
# ---------------------------------------------------------------------------


class TestDebouncedHandler:
    def test_fires_callback_after_debounce(self):
        callback = MagicMock()
        handler = DebouncedHandler(
            automation_id=1,
            pattern="*.txt",
            event_types=["created"],
            callback=callback,
            debounce_seconds=0.1,
        )

        handler.on_any_event(FakeEvent("/tmp/test.txt", "created"))
        time.sleep(0.3)

        callback.assert_called_once()
        assert callback.call_args[0][0] == 1  # automation_id
        assert callback.call_args[0][1] == "/tmp/test.txt"

    def test_debounce_prevents_duplicates(self):
        callback = MagicMock()
        handler = DebouncedHandler(
            automation_id=1,
            pattern="*.txt",
            event_types=["modified"],
            callback=callback,
            debounce_seconds=0.2,
        )

        # Rapid events — only the last should fire
        handler.on_any_event(FakeEvent("/tmp/test.txt", "modified"))
        handler.on_any_event(FakeEvent("/tmp/test.txt", "modified"))
        handler.on_any_event(FakeEvent("/tmp/test.txt", "modified"))

        time.sleep(0.5)

        callback.assert_called_once()

    def test_skips_directory_events(self):
        callback = MagicMock()
        handler = DebouncedHandler(
            automation_id=1,
            pattern="*",
            event_types=["created"],
            callback=callback,
            debounce_seconds=0.1,
        )

        handler.on_any_event(FakeEvent("/tmp/mydir", "created", is_directory=True))
        time.sleep(0.3)

        callback.assert_not_called()

    def test_skips_non_matching_event_type(self):
        callback = MagicMock()
        handler = DebouncedHandler(
            automation_id=1,
            pattern="*.txt",
            event_types=["created"],
            callback=callback,
            debounce_seconds=0.1,
        )

        handler.on_any_event(FakeEvent("/tmp/test.txt", "deleted"))
        time.sleep(0.3)

        callback.assert_not_called()

    def test_skips_non_matching_pattern(self):
        callback = MagicMock()
        handler = DebouncedHandler(
            automation_id=1,
            pattern="*.txt",
            event_types=["created"],
            callback=callback,
            debounce_seconds=0.1,
        )

        handler.on_any_event(FakeEvent("/tmp/image.png", "created"))
        time.sleep(0.3)

        callback.assert_not_called()

    def test_global_pause_skips(self):
        callback = MagicMock()
        handler = DebouncedHandler(
            automation_id=1,
            pattern="*",
            event_types=["created"],
            callback=callback,
            debounce_seconds=0.1,
        )

        from neo.automations.safety import set_global_pause
        set_global_pause(True)
        try:
            handler.on_any_event(FakeEvent("/tmp/test.txt", "created"))
            time.sleep(0.3)
            callback.assert_not_called()
        finally:
            set_global_pause(False)

    def test_cancel_all(self):
        callback = MagicMock()
        handler = DebouncedHandler(
            automation_id=1,
            pattern="*",
            event_types=["created"],
            callback=callback,
            debounce_seconds=0.5,
        )

        handler.on_any_event(FakeEvent("/tmp/test.txt", "created"))
        handler.cancel_all()
        time.sleep(0.8)

        callback.assert_not_called()

    def test_different_files_fire_separately(self):
        callback = MagicMock()
        handler = DebouncedHandler(
            automation_id=1,
            pattern="*.txt",
            event_types=["created"],
            callback=callback,
            debounce_seconds=0.1,
        )

        handler.on_any_event(FakeEvent("/tmp/a.txt", "created"))
        handler.on_any_event(FakeEvent("/tmp/b.txt", "created"))
        time.sleep(0.4)

        assert callback.call_count == 2


# ---------------------------------------------------------------------------
# NeoFileWatcher tests
# ---------------------------------------------------------------------------


class TestNeoFileWatcher:
    def _make_db(self, tmp_path):
        """Create a test database."""
        db_path = str(tmp_path / "test.db")
        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        conn.close()
        return db_path

    def test_add_and_remove_watcher(self, tmp_path):
        db_path = self._make_db(tmp_path)
        watch_dir = str(tmp_path / "watch")
        Path(watch_dir).mkdir()

        callback = MagicMock()
        watcher = NeoFileWatcher(db_path, callback)
        watcher._observer.start()

        try:
            watcher.add_watcher(1, watch_dir, "*.txt", ["created"])
            assert 1 in watcher._handlers

            watcher.remove_watcher(1)
            assert 1 not in watcher._handlers
        finally:
            watcher._observer.stop()
            watcher._observer.join(timeout=2)

    def test_remove_nonexistent_watcher(self, tmp_path):
        db_path = self._make_db(tmp_path)
        callback = MagicMock()
        watcher = NeoFileWatcher(db_path, callback)
        # Should not raise
        watcher.remove_watcher(999)

    def test_start_loads_from_db(self, tmp_path):
        db_path = self._make_db(tmp_path)
        watch_dir = str(tmp_path / "watch")
        Path(watch_dir).mkdir()

        # Insert file_event automation
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            (
                "watch downloads",
                "file_event",
                json.dumps({"path": watch_dir, "pattern": "*.pdf", "event_types": ["created"]}),
                "process new PDF",
            ),
        )
        conn.commit()
        conn.close()

        callback = MagicMock()
        watcher = NeoFileWatcher(db_path, callback)
        watcher.start()

        try:
            assert len(watcher._handlers) == 1
        finally:
            watcher.shutdown()

    def test_invalid_path_handled(self, tmp_path):
        db_path = self._make_db(tmp_path)
        callback = MagicMock()
        watcher = NeoFileWatcher(db_path, callback)
        watcher._observer.start()

        try:
            # Non-existent path should not crash
            watcher.add_watcher(1, "/nonexistent/path/12345", "*.txt", ["created"])
            assert 1 not in watcher._handlers  # Should fail gracefully
        finally:
            watcher._observer.stop()
            watcher._observer.join(timeout=2)
