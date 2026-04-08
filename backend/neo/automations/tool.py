"""LLM tool wrapper for creating automations via chat."""

import os

from neo.memory.db import get_session
from neo.memory.models import create_automation


def create_automation_from_tool(
    name: str,
    trigger_type: str,
    command: str,
    trigger_config: dict | None = None,
) -> str:
    """Create an automation from an LLM tool call.

    Opens its own DB session since ``dispatch_tool()`` doesn't pass ``conn``.

    Returns a human-readable confirmation string.
    """
    if trigger_type not in ("schedule", "startup", "file_event", "pattern"):
        return f"Error: Invalid trigger_type '{trigger_type}'. Must be one of: schedule, startup, file_event, pattern."

    db_path = os.environ.get("NEO_DB_PATH", "./data/neo.db")
    with get_session(db_path) as conn:
        auto_id = create_automation(
            conn,
            name=name,
            trigger_type=trigger_type,
            command=command,
            trigger_config=trigger_config or {},
        )

    trigger_desc = {
        "schedule": f"on schedule (cron: {(trigger_config or {}).get('cron', 'not set')})",
        "startup": "when Neo starts",
        "file_event": f"when files change in {(trigger_config or {}).get('path', 'not set')}",
        "pattern": f"when command matches '{(trigger_config or {}).get('match', '')}'",
    }

    return (
        f"Automation '{name}' created (ID: {auto_id}). "
        f"It will trigger {trigger_desc.get(trigger_type, trigger_type)}. "
        f"Command: {command}"
    )
