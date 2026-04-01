"""Proactive Intelligence — Suggestion Engine.

Analyses action_log patterns and generates suggestions for automations.
Runs as a background task on a 6-hour interval, throttled to max 1
suggestion per 24 hours.

Lifecycle:
    1. detect_patterns() — find repeated commands
    2. Filter out already-suggested or dismissed patterns
    3. Create suggestion row in DB
    4. Broadcast via SSE to frontend
"""

import logging
from typing import Callable

from neo.memory.db import get_session
from neo.memory.models import (
    create_suggestion,
    detect_patterns,
    get_active_suggestions,
    has_recent_suggestion,
)

logger = logging.getLogger(__name__)

# Minimum pattern occurrences to trigger a suggestion
_MIN_PATTERN_COUNT = 4

# How many days of history to scan
_PATTERN_DAYS = 14

# Throttle: max 1 suggestion per N hours
_THROTTLE_HOURS = 24


def _noop_broadcast(event_data: dict) -> None:
    """No-op broadcast fallback."""


def generate_suggestions(
    db_path: str,
    broadcast_fn: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Scan patterns and generate suggestions if applicable.

    Returns list of newly created suggestions.
    """
    broadcast = broadcast_fn or _noop_broadcast
    created: list[dict] = []

    with get_session(db_path) as conn:
        # Throttle: skip if we already suggested recently
        if has_recent_suggestion(conn, hours=_THROTTLE_HOURS):
            logger.debug("Suggestion throttled — recent suggestion exists")
            return []

        # Get current patterns
        patterns = detect_patterns(conn, days=_PATTERN_DAYS, min_count=_MIN_PATTERN_COUNT)
        if not patterns:
            return []

        # Get existing suggestions to avoid duplicates
        existing = get_active_suggestions(conn)
        existing_patterns = {s["pattern"] for s in existing}

        # Also check dismissed patterns (don't re-suggest)
        dismissed_rows = conn.execute(
            "SELECT pattern FROM suggestions WHERE dismissed = 1"
        ).fetchall()
        dismissed_patterns = {r["pattern"] for r in dismissed_rows}

        for p in patterns:
            pattern_key = p["pattern"]
            if pattern_key in existing_patterns or pattern_key in dismissed_patterns:
                continue

            message = (
                f"You've done \"{p['sample_input']}\" {p['count']} times. "
                f"Want to automate it?"
            )

            suggestion_id = create_suggestion(
                conn,
                pattern=pattern_key,
                message=message,
                count=p["count"],
                sample_input=p["sample_input"],
            )

            suggestion = {
                "id": suggestion_id,
                "pattern": pattern_key,
                "message": message,
                "count": p["count"],
                "sample_input": p["sample_input"],
            }
            created.append(suggestion)

            # Broadcast to frontend
            broadcast({
                "type": "suggestion",
                "suggestion": suggestion,
            })

            # Only create one suggestion per run (throttling)
            break

    if created:
        logger.info("Generated %d new suggestion(s)", len(created))

    return created


def get_pending_suggestions(db_path: str) -> list[dict]:
    """Get all active (non-dismissed, non-accepted) suggestions."""
    with get_session(db_path) as conn:
        return get_active_suggestions(conn)
