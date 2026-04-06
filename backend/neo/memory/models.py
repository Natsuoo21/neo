"""Database models — CRUD operations for all tables."""

import json
import sqlite3
from datetime import datetime, timezone

# ============================================
# USER PROFILE
# ============================================


def get_user_profile(conn: sqlite3.Connection) -> dict | None:
    """Get the user profile (single row, always id=1)."""
    row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def upsert_user_profile(
    conn: sqlite3.Connection,
    name: str,
    role: str = "",
    preferences: dict | None = None,
    tool_paths: dict | None = None,
) -> int:
    """Create or update the user profile."""
    existing = conn.execute("SELECT id FROM user_profile WHERE id = 1").fetchone()
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        conn.execute(
            """UPDATE user_profile
               SET name=?, role=?, preferences=?, tool_paths=?, updated_at=?
               WHERE id = 1""",
            (name, role, json.dumps(preferences or {}), json.dumps(tool_paths or {}), now),
        )
        return 1
    else:
        conn.execute(
            """INSERT INTO user_profile (name, role, preferences, tool_paths, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, role, json.dumps(preferences or {}), json.dumps(tool_paths or {}), now, now),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ============================================
# PROJECTS
# ============================================


def create_project(
    conn: sqlite3.Connection,
    name: str,
    description: str = "",
    goals: list | None = None,
    stakeholders: list | None = None,
    file_paths: dict | None = None,
    conventions: dict | None = None,
) -> int:
    """Create a new project. Returns project ID."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO projects
           (name, description, goals, stakeholders, file_paths, conventions, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            description,
            json.dumps(goals or []),
            json.dumps(stakeholders or []),
            json.dumps(file_paths or {}),
            json.dumps(conventions or {}),
            now,
            now,
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_project(conn: sqlite3.Connection, project_id: int) -> dict | None:
    """Get a project by ID."""
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_active_projects(conn: sqlite3.Connection) -> list[dict]:
    """Get all active projects."""
    rows = conn.execute("SELECT * FROM projects WHERE is_active = 1 ORDER BY name").fetchall()
    return [_row_to_dict(r) for r in rows]


def update_project(conn: sqlite3.Connection, project_id: int, **kwargs) -> bool:
    """Update project fields. Pass only the fields to change."""
    # Allowlist maps valid field names to themselves — only these columns can be updated.
    _ALLOWED_COLUMNS = {
        "name": "name",
        "description": "description",
        "goals": "goals",
        "stakeholders": "stakeholders",
        "file_paths": "file_paths",
        "conventions": "conventions",
        "is_active": "is_active",
    }
    updates = {_ALLOWED_COLUMNS[k]: v for k, v in kwargs.items() if k in _ALLOWED_COLUMNS}
    if not updates:
        return False

    # Serialize JSON fields
    for key in ("goals", "stakeholders", "file_paths", "conventions"):
        if key in updates and not isinstance(updates[key], str):
            updates[key] = json.dumps(updates[key])

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    # Safe: column names are from _ALLOWED_COLUMNS (hardcoded strings), not user input
    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [project_id]
    conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)  # noqa: S608
    return True


# ============================================
# ACTION LOG
# ============================================


def log_action(
    conn: sqlite3.Connection,
    input_text: str,
    intent: str = "",
    skill_used: str = "",
    tool_used: str = "",
    model_used: str = "",
    routed_tier: str = "",
    result: dict | None = None,
    status: str = "success",
    duration_ms: int = 0,
    tokens_used: int = 0,
    cost_brl: float = 0.0,
) -> int:
    """Log an action execution. Returns log entry ID."""
    conn.execute(
        """INSERT INTO action_log
           (input_text, intent, skill_used, tool_used, model_used, routed_tier,
            result, status, duration_ms, tokens_used, cost_brl)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            input_text,
            intent,
            skill_used,
            tool_used,
            model_used,
            routed_tier,
            json.dumps(result or {}),
            status,
            duration_ms,
            tokens_used,
            cost_brl,
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_recent_actions(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """Get the most recent action log entries."""
    rows = conn.execute("SELECT * FROM action_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_actions_by_tool(conn: sqlite3.Connection, tool_name: str, limit: int = 50) -> list[dict]:
    """Get action log entries for a specific tool."""
    rows = conn.execute(
        "SELECT * FROM action_log WHERE tool_used = ? ORDER BY created_at DESC LIMIT ?",
        (tool_name, limit),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_stats(conn: sqlite3.Connection, days: int = 30) -> dict:
    """Get telemetry stats for the last N days.

    Returns dict with: total_requests, success_count, error_count,
    total_duration_ms, total_tokens, total_cost, model_breakdown, tool_breakdown.
    """
    row = conn.execute(
        """SELECT
            COUNT(*) AS total_requests,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS error_count,
            COALESCE(SUM(duration_ms), 0) AS total_duration_ms,
            COALESCE(SUM(tokens_used), 0) AS total_tokens,
            COALESCE(SUM(cost_brl), 0) AS total_cost
        FROM action_log
        WHERE created_at >= datetime('now', ?)""",
        (f"-{days} days",),
    ).fetchone()

    stats = dict(row) if row else {}

    # Model breakdown
    model_rows = conn.execute(
        """SELECT model_used, COUNT(*) AS count, SUM(tokens_used) AS tokens, SUM(cost_brl) AS cost
        FROM action_log
        WHERE created_at >= datetime('now', ?) AND model_used != ''
        GROUP BY model_used ORDER BY count DESC""",
        (f"-{days} days",),
    ).fetchall()
    stats["model_breakdown"] = [dict(r) for r in model_rows]

    # Tool breakdown
    tool_rows = conn.execute(
        """SELECT tool_used, COUNT(*) AS count
        FROM action_log
        WHERE created_at >= datetime('now', ?) AND tool_used != ''
        GROUP BY tool_used ORDER BY count DESC""",
        (f"-{days} days",),
    ).fetchall()
    stats["tool_breakdown"] = [dict(r) for r in tool_rows]

    # Routed tier breakdown
    tier_rows = conn.execute(
        """SELECT routed_tier, COUNT(*) AS count
        FROM action_log
        WHERE created_at >= datetime('now', ?) AND routed_tier != ''
        GROUP BY routed_tier ORDER BY count DESC""",
        (f"-{days} days",),
    ).fetchall()
    stats["tier_breakdown"] = [dict(r) for r in tier_rows]

    return stats


def detect_patterns(conn: sqlite3.Connection, days: int = 14, min_count: int = 3) -> list[dict]:
    """Detect repeated command patterns in the action_log.

    Looks for similar commands executed >= min_count times in the last N days.
    Groups by the first 3 significant words (lowercased) to find repetitions.

    Returns:
        List of dicts with keys: pattern, count, last_run, sample_input.
    """
    rows = conn.execute(
        """SELECT input_text, created_at FROM action_log
           WHERE status = 'success'
             AND created_at >= datetime('now', ?)
           ORDER BY created_at DESC""",
        (f"-{days} days",),
    ).fetchall()

    # Group by normalized pattern (first 3 significant words)
    pattern_map: dict[str, list[dict]] = {}
    for row in rows:
        d = _row_to_dict(row)
        words = d["input_text"].lower().split()[:3]
        key = " ".join(words) if words else ""
        if not key:
            continue
        pattern_map.setdefault(key, []).append(d)

    results = []
    for pattern, entries in pattern_map.items():
        if len(entries) >= min_count:
            results.append(
                {
                    "pattern": pattern,
                    "count": len(entries),
                    "last_run": entries[0]["created_at"],
                    "sample_input": entries[0]["input_text"],
                }
            )

    return sorted(results, key=lambda x: x["count"], reverse=True)


# ============================================
# SKILLS
# ============================================


def upsert_skill(
    conn: sqlite3.Connection,
    name: str,
    file_path: str,
    skill_type: str,
    description: str = "",
    task_types: list | None = None,
) -> int:
    """Insert or update a skill in the registry."""
    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute("SELECT id FROM skills WHERE name = ?", (name,)).fetchone()

    if existing:
        conn.execute(
            """UPDATE skills SET file_path=?, skill_type=?, description=?, task_types=?, updated_at=?
               WHERE name = ?""",
            (file_path, skill_type, description, json.dumps(task_types or []), now, name),
        )
        return existing["id"]
    else:
        conn.execute(
            """INSERT INTO skills (name, file_path, skill_type, description, task_types, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, file_path, skill_type, description, json.dumps(task_types or []), now, now),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_enabled_skills(conn: sqlite3.Connection) -> list[dict]:
    """Get all enabled skills."""
    rows = conn.execute("SELECT * FROM skills WHERE is_enabled = 1 ORDER BY name").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_skill_by_task_type(conn: sqlite3.Connection, task_type: str) -> dict | None:
    """Find a skill whose task_types array contains the given task type."""
    rows = conn.execute("SELECT * FROM skills WHERE is_enabled = 1").fetchall()
    for row in rows:
        d = _row_to_dict(row)
        types = json.loads(d.get("task_types", "[]"))
        if task_type in types:
            return d
    return None


# ============================================
# AUTOMATIONS
# ============================================


def create_automation(
    conn: sqlite3.Connection,
    name: str,
    trigger_type: str,
    command: str,
    trigger_config: dict | None = None,
) -> int:
    """Create a new automation. Returns automation ID."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO automations (name, trigger_type, trigger_config, command, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, trigger_type, json.dumps(trigger_config or {}), command, now, now),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_enabled_automations(conn: sqlite3.Connection) -> list[dict]:
    """Get all enabled automations."""
    rows = conn.execute("SELECT * FROM automations WHERE is_enabled = 1 ORDER BY name").fetchall()
    return [_row_to_dict(r) for r in rows]


def update_automation_status(
    conn: sqlite3.Connection, automation_id: int, status: str, increment_retry: bool = False
) -> None:
    """Update an automation's last run status."""
    now = datetime.now(timezone.utc).isoformat()
    if increment_retry:
        conn.execute(
            """UPDATE automations
               SET last_status=?, last_run_at=?, retry_count=retry_count+1, updated_at=?
               WHERE id=?""",
            (status, now, now, automation_id),
        )
    else:
        conn.execute(
            """UPDATE automations SET last_status=?, last_run_at=?, retry_count=0, updated_at=? WHERE id=?""",
            (status, now, now, automation_id),
        )


def disable_automation(conn: sqlite3.Connection, automation_id: int) -> None:
    """Disable an automation (pause it)."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE automations SET is_enabled=0, updated_at=? WHERE id=?", (now, automation_id))


def get_automation(conn: sqlite3.Connection, automation_id: int) -> dict | None:
    """Get a single automation by ID."""
    row = conn.execute("SELECT * FROM automations WHERE id = ?", (automation_id,)).fetchone()
    return _row_to_dict(row) if row else None


def delete_automation(conn: sqlite3.Connection, automation_id: int) -> bool:
    """Delete an automation by ID. Returns True if deleted."""
    cursor = conn.execute("DELETE FROM automations WHERE id = ?", (automation_id,))
    return cursor.rowcount > 0


def get_automations_by_trigger(conn: sqlite3.Connection, trigger_type: str) -> list[dict]:
    """Get enabled automations filtered by trigger type."""
    rows = conn.execute(
        "SELECT * FROM automations WHERE trigger_type = ? AND is_enabled = 1 ORDER BY name",
        (trigger_type,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_all_automations(conn: sqlite3.Connection) -> list[dict]:
    """Get all automations (enabled and disabled)."""
    rows = conn.execute("SELECT * FROM automations ORDER BY name").fetchall()
    return [_row_to_dict(r) for r in rows]


def enable_automation(conn: sqlite3.Connection, automation_id: int) -> None:
    """Enable an automation."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE automations SET is_enabled=1, retry_count=0, updated_at=? WHERE id=?",
        (now, automation_id),
    )


# ============================================
# CONVERSATIONS
# ============================================


def add_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
    model_used: str = "",
) -> int:
    """Add a message to a conversation session."""
    conn.execute(
        "INSERT INTO conversations (session_id, role, content, model_used) VALUES (?, ?, ?, ?)",
        (session_id, role, content, model_used),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_conversation(conn: sqlite3.Connection, session_id: str, limit: int = 20) -> list[dict]:
    """Get messages for a session, most recent last."""
    rows = conn.execute(
        """SELECT * FROM conversations WHERE session_id = ?
           ORDER BY created_at ASC LIMIT ?""",
        (session_id, limit),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ============================================
# SUGGESTIONS
# ============================================


def create_suggestion(
    conn: sqlite3.Connection,
    pattern: str,
    message: str,
    count: int = 0,
    sample_input: str = "",
) -> int:
    """Create a new suggestion. Returns suggestion ID."""
    conn.execute(
        "INSERT INTO suggestions (pattern, message, count, sample_input) VALUES (?, ?, ?, ?)",
        (pattern, message, count, sample_input),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_active_suggestions(conn: sqlite3.Connection) -> list[dict]:
    """Get non-dismissed, non-accepted suggestions."""
    rows = conn.execute(
        "SELECT * FROM suggestions WHERE dismissed = 0 AND accepted = 0 ORDER BY created_at DESC"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def dismiss_suggestion(conn: sqlite3.Connection, suggestion_id: int) -> bool:
    """Dismiss a suggestion."""
    cursor = conn.execute("UPDATE suggestions SET dismissed = 1 WHERE id = ?", (suggestion_id,))
    return cursor.rowcount > 0


def accept_suggestion(conn: sqlite3.Connection, suggestion_id: int) -> dict | None:
    """Accept a suggestion and return it. Only accepts non-dismissed suggestions."""
    cursor = conn.execute(
        "UPDATE suggestions SET accepted = 1 WHERE id = ? AND accepted = 0 AND dismissed = 0",
        (suggestion_id,),
    )
    if cursor.rowcount == 0:
        return None
    row = conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_suggestion(conn: sqlite3.Connection, suggestion_id: int) -> dict | None:
    """Get a single suggestion by ID."""
    row = conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    return _row_to_dict(row) if row else None


def has_recent_suggestion(conn: sqlite3.Connection, hours: int = 24) -> bool:
    """Check if a suggestion was created in the last N hours (throttling)."""
    safe_hours = int(hours)  # S4: prevent SQL injection via string interpolation
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM suggestions WHERE created_at >= datetime('now', ?)",
        (f"-{safe_hours} hours",),
    ).fetchone()
    return (row["cnt"] if row else 0) > 0


# ============================================
# HELPERS
# ============================================


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)
