"""Tests for neo.automations.scheduler — cron parsing + NeoScheduler."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from neo.automations.scheduler import (
    NeoScheduler,
    parse_schedule,
    parse_schedule_with_llm,
)

# ---------------------------------------------------------------------------
# Cron parsing tests
# ---------------------------------------------------------------------------


class TestParseSchedule:
    def test_every_day_hhmm(self):
        assert parse_schedule("every day at 7:30") == "30 7 * * *"
        assert parse_schedule("every day at 0:00") == "0 0 * * *"
        assert parse_schedule("every day at 23:59") == "59 23 * * *"

    def test_every_day_ampm(self):
        assert parse_schedule("every day at 9am") == "0 9 * * *"
        assert parse_schedule("every day at 9pm") == "0 21 * * *"
        assert parse_schedule("every day at 12am") == "0 0 * * *"
        assert parse_schedule("every day at 12pm") == "0 12 * * *"

    def test_every_n_hours(self):
        assert parse_schedule("every 6 hours") == "0 */6 * * *"
        assert parse_schedule("every 1 hour") == "0 */1 * * *"
        assert parse_schedule("every 12 hours") == "0 */12 * * *"

    def test_every_n_minutes(self):
        assert parse_schedule("every 15 minutes") == "*/15 * * * *"
        assert parse_schedule("every 1 minute") == "*/1 * * * *"
        assert parse_schedule("every 30 minutes") == "*/30 * * * *"

    def test_weekday_hhmm(self):
        assert parse_schedule("every monday at 9:00") == "0 9 * * 0"
        assert parse_schedule("every friday at 17:30") == "30 17 * * 4"
        assert parse_schedule("every sunday at 8:00") == "0 8 * * 6"

    def test_weekday_ampm(self):
        assert parse_schedule("every monday at 9am") == "0 9 * * 0"
        assert parse_schedule("every friday at 5pm") == "0 17 * * 4"
        assert parse_schedule("every wed at 10am") == "0 10 * * 2"

    def test_case_insensitive(self):
        assert parse_schedule("Every Day At 7:30") == "30 7 * * *"
        assert parse_schedule("EVERY MONDAY AT 9AM") == "0 9 * * 0"

    def test_no_match_returns_none(self):
        assert parse_schedule("run at some point") is None
        assert parse_schedule("tomorrow at noon") is None
        assert parse_schedule("") is None

    def test_abbreviated_weekdays(self):
        assert parse_schedule("every mon at 9:00") == "0 9 * * 0"
        assert parse_schedule("every tue at 10:00") == "0 10 * * 1"
        assert parse_schedule("every wed at 11:00") == "0 11 * * 2"
        assert parse_schedule("every thu at 12:00") == "0 12 * * 3"
        assert parse_schedule("every fri at 13:00") == "0 13 * * 4"
        assert parse_schedule("every sat at 14:00") == "0 14 * * 5"


class TestParseScheduleWithLLM:
    @pytest.mark.asyncio
    async def test_valid_llm_response(self):
        provider = MagicMock()
        provider.complete = AsyncMock(return_value="30 7 * * *")

        result = await parse_schedule_with_llm("every day at 7:30", provider)
        assert result == "30 7 * * *"

    @pytest.mark.asyncio
    async def test_invalid_llm_response(self):
        provider = MagicMock()
        provider.complete = AsyncMock(return_value="not a cron expression")

        result = await parse_schedule_with_llm("something complex", provider)
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_exception(self):
        provider = MagicMock()
        provider.complete = AsyncMock(side_effect=RuntimeError("fail"))

        result = await parse_schedule_with_llm("fail test", provider)
        assert result is None


# ---------------------------------------------------------------------------
# NeoScheduler tests
# ---------------------------------------------------------------------------


class TestNeoScheduler:
    def _create_scheduler(self, db_path, registry=None):
        return NeoScheduler(db_path, registry or {}, broadcast_fn=MagicMock())

    def test_start_loads_from_db(self, memory_db, tmp_path):
        """Scheduler loads enabled schedule automations on start."""
        # Create a DB file for real get_session usage
        db_path = str(tmp_path / "test.db")

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)

        # Insert automation
        conn.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("daily report", "schedule", json.dumps({"cron": "0 9 * * *"}), "generate report"),
        )
        conn.commit()
        conn.close()

        scheduler = self._create_scheduler(db_path)
        scheduler.start()
        try:
            jobs = scheduler._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].name == "daily report"
        finally:
            scheduler.shutdown(wait=False)

    def test_add_and_remove_automation(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        import sqlite3
        from pathlib import Path

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        conn.close()

        scheduler = self._create_scheduler(db_path)
        scheduler._scheduler.start()
        try:
            scheduler.add_automation(1, "test job", "*/5 * * * *", "check email")
            assert len(scheduler._scheduler.get_jobs()) == 1

            scheduler.remove_automation(1)
            assert len(scheduler._scheduler.get_jobs()) == 0
        finally:
            scheduler.shutdown(wait=False)

    def test_add_invalid_cron(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        import sqlite3
        from pathlib import Path

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        conn.close()

        scheduler = self._create_scheduler(db_path)
        scheduler._scheduler.start()
        try:
            scheduler.add_automation(1, "bad cron", "invalid", "do something")
            assert len(scheduler._scheduler.get_jobs()) == 0
        finally:
            scheduler.shutdown(wait=False)

    def test_get_next_run(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        import sqlite3
        from pathlib import Path

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        conn.close()

        scheduler = self._create_scheduler(db_path)
        scheduler._scheduler.start()
        try:
            scheduler.add_automation(1, "test", "0 9 * * *", "check")
            next_run = scheduler.get_next_run(1)
            assert next_run is not None

            # Non-existent automation
            assert scheduler.get_next_run(999) is None
        finally:
            scheduler.shutdown(wait=False)

    def test_global_pause_skips_execution(self, tmp_path):
        """When globally paused, _execute_automation does nothing."""
        db_path = str(tmp_path / "test.db")
        import sqlite3
        from pathlib import Path

        from neo.automations.safety import set_global_pause

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("test", "schedule", "{}", "run something"),
        )
        conn.commit()
        auto_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        scheduler = self._create_scheduler(db_path)
        set_global_pause(True)
        try:
            # Should return immediately without executing
            scheduler._execute_automation(auto_id, "run something")
            # No error = passed (skipped due to global pause)
        finally:
            set_global_pause(False)

    def test_replace_existing_job(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        import sqlite3
        from pathlib import Path

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        conn.close()

        scheduler = self._create_scheduler(db_path)
        scheduler._scheduler.start()
        try:
            scheduler.add_automation(1, "job v1", "0 9 * * *", "old command")
            scheduler.add_automation(1, "job v2", "0 10 * * *", "new command")
            jobs = scheduler._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].name == "job v2"
        finally:
            scheduler.shutdown(wait=False)

    def test_remove_nonexistent_job(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        import sqlite3
        from pathlib import Path

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        conn.close()

        scheduler = self._create_scheduler(db_path)
        scheduler._scheduler.start()
        try:
            # Should not raise
            scheduler.remove_automation(999)
        finally:
            scheduler.shutdown(wait=False)

    def test_jobs_persist_across_restart(self, tmp_path):
        """Jobs in SQLAlchemyJobStore survive scheduler restart."""
        db_path = str(tmp_path / "test.db")
        import sqlite3
        from pathlib import Path

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("persist test", "schedule", json.dumps({"cron": "0 9 * * *"}), "generate report"),
        )
        conn.commit()
        conn.close()

        # First scheduler — start, add job, shutdown
        scheduler1 = self._create_scheduler(db_path)
        scheduler1.start()
        jobs1 = scheduler1._scheduler.get_jobs()
        assert len(jobs1) == 1
        assert jobs1[0].name == "persist test"
        scheduler1.shutdown(wait=False)

        # Second scheduler — same DB, should recover the job
        scheduler2 = self._create_scheduler(db_path)
        scheduler2.start()
        try:
            jobs2 = scheduler2._scheduler.get_jobs()
            assert len(jobs2) == 1
            assert jobs2[0].name == "persist test"
        finally:
            scheduler2.shutdown(wait=False)

    def test_sync_removes_orphaned_jobs(self, tmp_path):
        """Jobs for deleted/disabled automations are removed on sync."""
        db_path = str(tmp_path / "test.db")
        import sqlite3
        from pathlib import Path

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("will be deleted", "schedule", json.dumps({"cron": "0 9 * * *"}), "do stuff"),
        )
        conn.commit()
        auto_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        # First run — job registered
        scheduler1 = self._create_scheduler(db_path)
        scheduler1.start()
        assert len(scheduler1._scheduler.get_jobs()) == 1
        scheduler1.shutdown(wait=False)

        # Delete the automation from DB while scheduler is down
        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM automations WHERE id = ?", (auto_id,))
        conn.commit()
        conn.close()

        # Second run — orphaned job should be removed by sync
        scheduler2 = self._create_scheduler(db_path)
        scheduler2.start()
        try:
            assert len(scheduler2._scheduler.get_jobs()) == 0
        finally:
            scheduler2.shutdown(wait=False)

    def test_sync_adds_new_automations(self, tmp_path):
        """Automations added while scheduler was down get synced on restart."""
        db_path = str(tmp_path / "test.db")
        import sqlite3
        from pathlib import Path

        schema_path = Path(__file__).resolve().parent.parent.parent / "neo" / "memory" / "schema.sql"
        conn = sqlite3.connect(db_path)
        for stmt in schema_path.read_text().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        conn.close()

        # First run — no automations
        scheduler1 = self._create_scheduler(db_path)
        scheduler1.start()
        assert len(scheduler1._scheduler.get_jobs()) == 0
        scheduler1.shutdown(wait=False)

        # Add automation to DB while scheduler is down
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("new job", "schedule", json.dumps({"cron": "30 8 * * *"}), "new command"),
        )
        conn.commit()
        conn.close()

        # Second run — new automation should be synced
        scheduler2 = self._create_scheduler(db_path)
        scheduler2.start()
        try:
            jobs = scheduler2._scheduler.get_jobs()
            assert len(jobs) == 1
            assert jobs[0].name == "new job"
        finally:
            scheduler2.shutdown(wait=False)
