"""Database models — CRUD operations for all tables."""

import json
import re
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
    allowed = {"name", "description", "goals", "stakeholders", "file_paths", "conventions", "is_active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False

    # Validate that all keys are safe identifiers (defense-in-depth)
    for key in updates:
        if not re.match(r"^[a-z_]+$", key):
            raise ValueError(f"Invalid column name: {key}")

    # Serialize JSON fields
    for key in ("goals", "stakeholders", "file_paths", "conventions"):
        if key in updates and not isinstance(updates[key], str):
            updates[key] = json.dumps(updates[key])

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [project_id]
    conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)
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
# HELPERS
# ============================================


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)
