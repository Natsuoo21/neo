"""Automation scheduler — APScheduler with in-memory job store.

Parses natural-language schedule expressions into cron strings,
manages APScheduler jobs, and executes automations through the
orchestrator with full safety checks.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from neo.automations.safety import (
    check_api_key_available,
    handle_failure,
    is_destructive,
    is_globally_paused,
    log_after_execution,
    log_before_execution,
    request_confirmation,
)
from neo.memory.db import get_session
from neo.memory.models import get_automation, get_automations_by_trigger, update_automation_status

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schedule parsing — regex-first, LLM fallback
# ---------------------------------------------------------------------------

_WEEKDAY_MAP: dict[str, int] = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# Regex patterns for common schedule expressions
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "every day at HH:MM" or "every day at Ham/Hpm"
    (
        re.compile(r"every\s+day\s+at\s+(\d{1,2}):(\d{2})", re.IGNORECASE),
        "daily_hhmm",
    ),
    (
        re.compile(r"every\s+day\s+at\s+(\d{1,2})\s*(am|pm)", re.IGNORECASE),
        "daily_ampm",
    ),
    # "every N hours"
    (
        re.compile(r"every\s+(\d+)\s+hours?", re.IGNORECASE),
        "every_n_hours",
    ),
    # "every N minutes"
    (
        re.compile(r"every\s+(\d+)\s+minutes?", re.IGNORECASE),
        "every_n_minutes",
    ),
    # "every {weekday} at HH:MM"
    (
        re.compile(
            r"every\s+(" + "|".join(_WEEKDAY_MAP.keys()) + r")\s+at\s+(\d{1,2}):(\d{2})",
            re.IGNORECASE,
        ),
        "weekday_hhmm",
    ),
    # "every {weekday} at Ham/Hpm"
    (
        re.compile(
            r"every\s+(" + "|".join(_WEEKDAY_MAP.keys()) + r")\s+at\s+(\d{1,2})\s*(am|pm)",
            re.IGNORECASE,
        ),
        "weekday_ampm",
    ),
]


def _to_24h(hour: int, ampm: str) -> int:
    """Convert 12-hour time to 24-hour."""
    ampm = ampm.lower()
    if ampm == "am":
        return 0 if hour == 12 else hour
    else:
        return hour if hour == 12 else hour + 12


def parse_schedule(text: str) -> str | None:
    """Parse a natural-language schedule into a 5-field cron expression.

    Returns None if no pattern matches.

    Examples:
        "every day at 7:30"     -> "30 7 * * *"
        "every day at 9am"      -> "0 9 * * *"
        "every 6 hours"         -> "0 */6 * * *"
        "every 15 minutes"      -> "*/15 * * * *"
        "every monday at 9:00"  -> "0 9 * * 0"
        "every friday at 5pm"   -> "0 17 * * 4"
    """
    text = text.strip()

    for pattern, kind in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue

        if kind == "daily_hhmm":
            hour, minute = int(m.group(1)), int(m.group(2))
            return f"{minute} {hour} * * *"

        if kind == "daily_ampm":
            hour = _to_24h(int(m.group(1)), m.group(2))
            return f"0 {hour} * * *"

        if kind == "every_n_hours":
            n = int(m.group(1))
            return f"0 */{n} * * *"

        if kind == "every_n_minutes":
            n = int(m.group(1))
            return f"*/{n} * * * *"

        if kind == "weekday_hhmm":
            day = _WEEKDAY_MAP[m.group(1).lower()]
            hour, minute = int(m.group(2)), int(m.group(3))
            return f"{minute} {hour} * * {day}"

        if kind == "weekday_ampm":
            day = _WEEKDAY_MAP[m.group(1).lower()]
            hour = _to_24h(int(m.group(2)), m.group(3))
            return f"0 {hour} * * {day}"

    return None


async def parse_schedule_with_llm(text: str, provider: Any) -> str | None:
    """Fallback: use LLM to parse schedule text into cron expression.

    Returns a validated 5-field cron string, or None on failure.
    """
    prompt = (
        "Convert the following schedule description to a standard 5-field cron expression "
        "(minute hour day-of-month month day-of-week). Reply with ONLY the cron expression, "
        "nothing else.\n\n"
        f"Schedule: {text}"
    )

    try:
        response = await provider.complete(system="You are a cron expression generator.", user=prompt)
        cron = response.strip()
        # Validate: must be exactly 5 space-separated fields
        parts = cron.split()
        if len(parts) == 5:
            # Quick validation — try to create a CronTrigger
            CronTrigger.from_crontab(cron)
            return cron
    except Exception:
        logger.exception("LLM cron parsing failed for: %s", text)

    return None


# ---------------------------------------------------------------------------
# NeoScheduler class
# ---------------------------------------------------------------------------


def _noop_broadcast(event_data: dict) -> None:
    """No-op broadcast for when server broadcast isn't available."""


class NeoScheduler:
    """Manages scheduled automations via APScheduler."""

    def __init__(
        self,
        db_path: str,
        provider_registry: dict,
        broadcast_fn: Any = None,
    ):
        self._db_path = db_path
        self._registry = provider_registry
        self._broadcast = broadcast_fn or _noop_broadcast
        self._scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,
            }
        )

    def start(self) -> None:
        """Load enabled schedule automations from DB and start the scheduler."""
        with get_session(self._db_path) as conn:
            automations = get_automations_by_trigger(conn, "schedule")

        for auto in automations:
            config = json.loads(auto.get("trigger_config", "{}") or "{}")
            cron_expr = config.get("cron", "")
            if cron_expr:
                self.add_automation(auto["id"], auto["name"], cron_expr, auto["command"])

        self._scheduler.start()
        logger.info("Scheduler started with %d jobs", len(self._scheduler.get_jobs()))

    def shutdown(self, wait: bool = True) -> None:
        """Gracefully stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Scheduler shut down")

    def add_automation(self, automation_id: int, name: str, cron_expr: str, command: str) -> None:
        """Register a scheduled job."""
        job_id = f"automation_{automation_id}"

        # Remove existing job if any
        existing = self._scheduler.get_job(job_id)
        if existing:
            self._scheduler.remove_job(job_id)

        try:
            trigger = CronTrigger.from_crontab(cron_expr)
        except ValueError:
            logger.error("Invalid cron expression for automation %d: %s", automation_id, cron_expr)
            return

        self._scheduler.add_job(
            self._execute_automation,
            trigger=trigger,
            id=job_id,
            name=name,
            args=[automation_id, command],
        )
        logger.info("Registered job %s: %s [%s]", job_id, name, cron_expr)

    def remove_automation(self, automation_id: int) -> None:
        """Remove a scheduled job."""
        job_id = f"automation_{automation_id}"
        existing = self._scheduler.get_job(job_id)
        if existing:
            self._scheduler.remove_job(job_id)
            logger.info("Removed job %s", job_id)

    def get_next_run(self, automation_id: int) -> str | None:
        """Get the next scheduled run time for an automation."""
        job_id = f"automation_{automation_id}"
        job = self._scheduler.get_job(job_id)
        if job and job.next_run_time:
            return job.next_run_time.isoformat()
        return None

    def _execute_automation(self, automation_id: int, command: str) -> None:
        """Execute an automation (runs in APScheduler thread).

        Applies all 5 safety rules in order.
        """
        start = time.time()

        # RULE 5 — Global pause check
        if is_globally_paused():
            logger.info("Skipping automation %d — globally paused", automation_id)
            return

        # Fetch current automation state
        with get_session(self._db_path) as conn:
            auto = get_automation(conn, automation_id)
            if not auto or not auto.get("is_enabled"):
                return

            # RULE 2 — Log before execution
            log_before_execution(conn, automation_id, command)

        try:
            # RULE 1 — Check destructive → request confirmation
            if is_destructive(command):
                loop = asyncio.new_event_loop()
                try:
                    approved = loop.run_until_complete(
                        request_confirmation(
                            f"Automation '{auto['name']}' wants to execute: {command}",
                            automation_id=automation_id,
                            timeout_s=60.0,
                            notify_callback=self._broadcast,
                        )
                    )
                finally:
                    loop.close()

                if not approved:
                    logger.info("Automation %d cancelled — confirmation denied/timed out", automation_id)
                    with get_session(self._db_path) as conn:
                        log_after_execution(conn, automation_id, command, "cancelled", "User denied", 0)
                    return

            # RULE 4 — Check API key availability
            from neo.router import route
            tier = route(command)
            if not check_api_key_available(tier):
                tier = "LOCAL"
                if not check_api_key_available(tier):
                    raise RuntimeError(f"No API key available for tier {tier}")

            # Execute via orchestrator
            from neo.orchestrator import process
            from neo.router import strip_override
            from neo.skills.loader import route_skill_with_name

            clean_command = strip_override(command)
            provider = self._select_provider(tier)
            if provider is None:
                raise RuntimeError("No LLM provider available")

            loop = asyncio.new_event_loop()
            try:
                with get_session(self._db_path) as conn:
                    skill_name, skill_content = route_skill_with_name(clean_command, conn)
                    result = loop.run_until_complete(
                        process(
                            clean_command,
                            provider,
                            conn,
                            skill_content,
                            skill_name=skill_name,
                            routed_tier=tier,
                        )
                    )
            finally:
                loop.close()

            elapsed_ms = int((time.time() - start) * 1000)

            # RULE 2 — Log after execution
            with get_session(self._db_path) as conn:
                log_after_execution(
                    conn, automation_id, command,
                    result["status"], result.get("message", ""), elapsed_ms,
                )
                if result["status"] == "success":
                    update_automation_status(conn, automation_id, "success")
                else:
                    # RULE 3 — Handle failure
                    auto = get_automation(conn, automation_id)
                    retry_count = auto.get("retry_count", 0) if auto else 0
                    paused = handle_failure(conn, automation_id, retry_count)
                    if paused:
                        self._broadcast({
                            "type": "automation_status",
                            "automation_id": automation_id,
                            "status": "paused",
                            "message": (
                                f"Automation '{auto['name'] if auto else automation_id}' "
                                "paused after repeated failures"
                            ),
                        })
                        self.remove_automation(automation_id)

        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            logger.exception("Automation %d failed", automation_id)

            with get_session(self._db_path) as conn:
                log_after_execution(conn, automation_id, command, "error", str(e), elapsed_ms)
                auto = get_automation(conn, automation_id)
                retry_count = auto.get("retry_count", 0) if auto else 0
                paused = handle_failure(conn, automation_id, retry_count)
                if paused:
                    self.remove_automation(automation_id)

    def _select_provider(self, tier: str) -> Any:
        """Select an LLM provider with fallback chain."""
        from neo.router import CLAUDE, GEMINI, LOCAL, OPENAI
        fallback = [LOCAL, GEMINI, OPENAI, CLAUDE]

        if tier in self._registry:
            return self._registry[tier]

        start_idx = fallback.index(tier) if tier in fallback else 0
        for t in fallback[start_idx:]:
            if t in self._registry:
                return self._registry[t]

        return None
