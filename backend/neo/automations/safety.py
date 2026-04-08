"""Safety system — 5 rules that govern all automation execution.

Rule 1: Destructive actions require user confirmation.
Rule 2: All executions are logged before and after.
Rule 3: 3 consecutive failures pause the automation.
Rule 4: API key availability is checked before execution.
Rule 5: Global pause stops all automations instantly.
"""

import asyncio
import logging
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from neo.memory.models import (
    disable_automation,
    log_action,
    update_automation_status,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule 5 — Global pause (threading.Lock for cross-thread safety)
# ---------------------------------------------------------------------------

_pause_lock = threading.Lock()
_global_paused: bool = False


def is_globally_paused() -> bool:
    """Check if all automations are paused."""
    with _pause_lock:
        return _global_paused


def set_global_pause(paused: bool) -> None:
    """Set the global pause state for all automations."""
    global _global_paused
    with _pause_lock:
        _global_paused = paused
    logger.info("Global automation pause set to %s", paused)


# ---------------------------------------------------------------------------
# Rule 1 — Destructive action detection + confirmation
# ---------------------------------------------------------------------------

DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({
    "delete",
    "send_email",
    "reply_to",
    "submit_form",
    "fill_form",
})

_DESTRUCTIVE_TOOL_NAMES: frozenset[str] = frozenset({
    "send_email",
    "reply_to",
    "fill_form",
    "submit_form",
    "open_app",
})


def is_destructive(action: str, tool_name: str = "", tool_input: dict | None = None) -> bool:
    """Check if an action is destructive and requires confirmation.

    Args:
        action: The action name or command keyword.
        tool_name: The tool being invoked (e.g., "manage_file").
        tool_input: The tool's input parameters.

    Returns:
        True if the action is destructive.
    """
    if action.lower() in DESTRUCTIVE_ACTIONS:
        return True

    if tool_name in _DESTRUCTIVE_TOOL_NAMES:
        return True

    if tool_name == "manage_file" and isinstance(tool_input, dict):
        if tool_input.get("action") == "delete":
            return True

    return False


@dataclass
class PendingConfirmation:
    """A pending user confirmation for a destructive action.

    Note: `future` is NOT set via default_factory — it must be created
    explicitly with the correct event loop context by the caller.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    automation_id: int = 0
    action_description: str = ""
    future: asyncio.Future | None = field(default=None, repr=False)


# In-memory store of pending confirmations, guarded by a lock
_pending_lock = threading.Lock()
_pending: dict[str, PendingConfirmation] = {}


async def request_confirmation(
    action_description: str,
    automation_id: int = 0,
    timeout_s: float = 60.0,
    notify_callback: Callable[..., Any] | None = None,
) -> bool:
    """Request user confirmation for a destructive action.

    Creates a PendingConfirmation with an asyncio.Future, pushes an SSE
    event via notify_callback, and waits up to timeout_s for resolution.

    Args:
        action_description: Human-readable description of the action.
        automation_id: ID of the automation requesting confirmation.
        timeout_s: Seconds to wait before auto-cancelling.
        notify_callback: Callable to push SSE event to frontend.

    Returns:
        True if approved, False if denied or timed out.
    """
    loop = asyncio.get_running_loop()
    confirmation = PendingConfirmation(
        automation_id=automation_id,
        action_description=action_description,
        future=loop.create_future(),
    )

    with _pending_lock:
        _pending[confirmation.id] = confirmation

    # Notify frontend via SSE
    if notify_callback:
        try:
            notify_callback({
                "type": "confirmation_request",
                "confirmation_id": confirmation.id,
                "automation_id": automation_id,
                "action_description": action_description,
                "timeout_s": timeout_s,
            })
        except Exception:
            logger.exception("Failed to send confirmation notification")

    try:
        assert confirmation.future is not None
        result = await asyncio.wait_for(confirmation.future, timeout=timeout_s)
        return bool(result)
    except asyncio.TimeoutError:
        logger.warning(
            "Confirmation timed out for automation %d: %s",
            automation_id, action_description,
        )
        return False
    finally:
        with _pending_lock:
            _pending.pop(confirmation.id, None)


def resolve_confirmation(confirmation_id: str, approved: bool) -> bool:
    """Resolve a pending confirmation (thread-safe).

    Args:
        confirmation_id: UUID of the pending confirmation.
        approved: True to approve, False to deny.

    Returns:
        True if the confirmation was found and resolved.
    """
    with _pending_lock:
        confirmation = _pending.get(confirmation_id)

    if confirmation is None or confirmation.future is None:
        return False

    try:
        if not confirmation.future.done():
            confirmation.future.set_result(approved)
    except asyncio.InvalidStateError:
        # Future was already resolved (race between timeout and manual resolve)
        logger.debug("Confirmation %s already resolved", confirmation_id)

    return True


def get_pending_confirmations() -> list[dict]:
    """Get all pending confirmations as dicts for the frontend (thread-safe)."""
    with _pending_lock:
        items = list(_pending.values())

    return [
        {
            "id": c.id,
            "automation_id": c.automation_id,
            "action_description": c.action_description,
        }
        for c in items
    ]


# ---------------------------------------------------------------------------
# Rule 2 — Before/after logging
# ---------------------------------------------------------------------------


def log_before_execution(conn: sqlite3.Connection, automation_id: int, command: str) -> int:
    """Log an action before execution with status='pending'.

    Returns the log entry ID.
    """
    return log_action(
        conn,
        input_text=command,
        intent="automation",
        tool_used="automation",
        status="pending",
        result={"automation_id": automation_id},
    )


def log_after_execution(
    conn: sqlite3.Connection,
    automation_id: int,
    command: str,
    status: str,
    result_message: str = "",
    duration_ms: int = 0,
) -> int:
    """Log an action after execution with the final status.

    Returns the log entry ID.
    """
    return log_action(
        conn,
        input_text=command,
        intent="automation",
        tool_used="automation",
        status=status,
        result={"automation_id": automation_id, "message": result_message},
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Rule 3 — Failure handling with retry + auto-pause
# ---------------------------------------------------------------------------

_DEFAULT_MAX_RETRIES = 3


def handle_failure(
    conn: sqlite3.Connection,
    automation_id: int,
    current_retry: int,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> bool:
    """Handle an automation failure with retry logic.

    Increments retry count. If current_retry + 1 >= max_retries,
    disables the automation.

    Args:
        conn: SQLite connection.
        automation_id: The automation that failed.
        current_retry: Current retry count (0-based).
        max_retries: Max retries before pausing.

    Returns:
        True if the automation was paused (hit max retries).
    """
    update_automation_status(conn, automation_id, "error", increment_retry=True)

    if current_retry + 1 >= max_retries:
        disable_automation(conn, automation_id)
        logger.warning(
            "Automation %d paused after %d consecutive failures",
            automation_id,
            current_retry + 1,
        )
        return True

    return False


# ---------------------------------------------------------------------------
# Rule 4 — API key availability guard
# ---------------------------------------------------------------------------

_TIER_ENV_KEYS: dict[str, str] = {
    "CLAUDE": "CLAUDE_API_KEY",
    "OPENAI": "OPENAI_API_KEY",
    "GEMINI": "GEMINI_API_KEY",
}


def check_api_key_available(tier: str) -> bool:
    """Check if the API key for the given tier is available.

    LOCAL tier always returns True (no API key needed).
    """
    if tier == "LOCAL":
        return True

    env_key = _TIER_ENV_KEYS.get(tier, "")
    if not env_key:
        return False

    return bool(os.environ.get(env_key, ""))
