"""Skill loader — Parse .md skill files and route to correct skill.

Skills are markdown files with YAML frontmatter that get prepended to LLM
system prompts. This gives Neo domain-specific instructions for different
task types (e.g., "write an email", "create a spreadsheet").

Skill file format:
    ---
    name: skill_name
    description: What this skill does
    task_types: [keyword1, keyword2, ...]
    tools: [tool1, tool2]
    ---
    <Markdown instructions for the LLM>

Activation: slash commands only (e.g., /email write a follow-up).
"""

import json
import logging
import os
import re
import sqlite3

from neo.memory.models import get_enabled_skills, upsert_skill

logger = logging.getLogger(__name__)

# Directories to scan for skill files
_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "public")
_USER_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "user")
_COMMUNITY_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "community")


# ---------------------------------------------------------------------------
# Slash command parsing
# ---------------------------------------------------------------------------


def parse_slash_command(command: str) -> tuple[str, str]:
    """Parse ``/skill-name rest of command`` into (slug, remainder).

    Returns:
        (slug, remainder) if command starts with ``/``,
        ("", original_command) otherwise.
    """
    stripped = command.strip()
    if not stripped.startswith("/"):
        return "", stripped

    # Split on first whitespace: "/email write a note" → "email", "write a note"
    parts = stripped[1:].split(None, 1)
    if not parts:
        return "", stripped

    slug = parts[0].lower()
    remainder = parts[1] if len(parts) > 1 else ""
    return slug, remainder


def resolve_skill_slug(slug: str, conn: sqlite3.Connection) -> str | None:
    """Map a user-typed slug to a DB skill name.

    Resolution order:
    1. Exact match on skill name
    2. Prefix match (e.g., ``/email`` → ``email_writer``)

    Returns:
        Skill name string, or None if no match.
    """
    enabled = get_enabled_skills(conn)

    # 1. Exact match
    for skill in enabled:
        if skill["name"] == slug:
            return skill["name"]

    # 2. Prefix match
    for skill in enabled:
        if skill["name"].startswith(slug):
            return skill["name"]

    return None


def get_skill_by_name(name: str, conn: sqlite3.Connection) -> tuple[str, str]:
    """Look up an enabled skill by exact name and return (name, content).

    Returns:
        (name, content) or ("", "") if not found or disabled.
    """
    row = conn.execute(
        "SELECT name, file_path FROM skills WHERE name = ? AND is_enabled = 1",
        (name,),
    ).fetchone()
    if not row:
        return "", ""

    parsed = parse_skill_file(row["file_path"])
    if parsed:
        return parsed["name"], parsed["content"]
    return "", ""


def get_available_skill_commands(conn: sqlite3.Connection) -> list[dict]:
    """Return list of ``{name, description}`` for all enabled skills.

    Used to populate the system prompt with available slash commands.
    """
    enabled = get_enabled_skills(conn)
    return [
        {"name": s["name"], "description": s.get("description", "")}
        for s in enabled
    ]


def delete_skill(conn: sqlite3.Connection, name: str) -> bool:
    """Delete a user or community skill file and its DB row.

    Refuses to delete public (built-in) skills.

    Returns:
        True if deleted, False if not found or protected.
    """
    row = conn.execute(
        "SELECT file_path, skill_type FROM skills WHERE name = ?", (name,)
    ).fetchone()
    if not row:
        return False

    if row["skill_type"] == "public":
        logger.warning("Refusing to delete built-in skill: %s", name)
        return False

    # Remove the file
    file_path = row["file_path"]
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)
        logger.info("Deleted skill file: %s", file_path)

    # Remove the DB row
    conn.execute("DELETE FROM skills WHERE name = ?", (name,))
    return True


# ---------------------------------------------------------------------------
# LLM tool wrapper for create_skill
# ---------------------------------------------------------------------------


def create_user_skill_from_tool(
    name: str,
    description: str,
    instructions: str,
    task_types: list[str] | None = None,
    tools: list[str] | None = None,
) -> str:
    """Wrapper for LLM tool dispatch — opens its own DB session.

    Called by ``dispatch_tool()`` which doesn't pass ``conn``.
    """
    from neo.memory.db import get_session

    db_path = os.environ.get("NEO_DB_PATH", "./data/neo.db")
    with get_session(db_path) as conn:
        path = create_user_skill(
            conn,
            name=name,
            description=description,
            task_types=task_types or [],
            content=instructions,
            tools=tools,
        )
    return f"Skill '{name}' created at {path}"


# ---------------------------------------------------------------------------
# Skill file parsing
# ---------------------------------------------------------------------------


def parse_skill_file(file_path: str) -> dict:
    """Parse a .md skill file into frontmatter dict + content string.

    Returns:
        dict with keys: name, description, task_types, tools, content, file_path
        Returns empty dict if parsing fails.
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        logger.error("Cannot read skill file %s: %s", file_path, e)
        return {}

    # Split on YAML frontmatter delimiters
    if not text.startswith("---"):
        logger.warning("Skill file %s has no frontmatter", file_path)
        return {}

    parts = text.split("---", 2)
    if len(parts) < 3:
        logger.warning("Skill file %s has malformed frontmatter", file_path)
        return {}

    frontmatter_raw = parts[1].strip()
    content = parts[2].strip()

    # Simple YAML parser (no dependency needed for flat key-value + lists)
    meta = _parse_simple_yaml(frontmatter_raw)
    if not meta.get("name"):
        logger.warning("Skill file %s missing 'name' in frontmatter", file_path)
        return {}

    return {
        "name": meta["name"],
        "description": meta.get("description", ""),
        "task_types": meta.get("task_types", []),
        "tools": meta.get("tools", []),
        "content": content,
        "file_path": file_path,
    }


def _parse_simple_yaml(raw: str) -> dict:
    """Parse simple YAML frontmatter (flat keys, inline lists).

    Supports:
        key: value
        key: [item1, item2, ...]
    """
    result: dict = {}
    for line in raw.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        # Parse inline list [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            result[key] = [item.strip().strip("\"'") for item in items if item.strip()]
        else:
            result[key] = value.strip("\"'")

    return result


# ---------------------------------------------------------------------------
# Load & sync
# ---------------------------------------------------------------------------


def load_all_skills(extra_dirs: list[str] | None = None) -> list[dict]:
    """Load all skill files from built-in + extra directories.

    Scans: public/, user/, community/, plus any extra_dirs provided
    (e.g. user-configured local folders).

    Returns:
        List of parsed skill dicts.
    """
    skills = []
    seen_names: set[str] = set()

    dirs = [_SKILLS_DIR, _USER_SKILLS_DIR, _COMMUNITY_SKILLS_DIR]
    for extra in extra_dirs or []:
        expanded = os.path.expanduser(extra.strip())
        if expanded and expanded not in dirs:
            dirs.append(expanded)

    for skills_dir in dirs:
        if not os.path.isdir(skills_dir):
            continue
        for filename in sorted(os.listdir(skills_dir)):
            if not filename.endswith(".md"):
                continue
            file_path = os.path.join(skills_dir, filename)
            skill = parse_skill_file(file_path)
            if skill and skill["name"] not in seen_names:
                skills.append(skill)
                seen_names.add(skill["name"])

    return skills


def _detect_skill_type(file_path: str) -> str:
    """Determine skill type based on which directory the file is in."""
    real_path = os.path.realpath(file_path)
    real_public = os.path.realpath(_SKILLS_DIR)
    real_community = os.path.realpath(_COMMUNITY_SKILLS_DIR)
    if real_path.startswith(real_public + os.sep):
        return "public"
    if real_path.startswith(real_community + os.sep):
        return "community"
    return "user"


def _get_extra_skill_dirs(conn: sqlite3.Connection) -> list[str]:
    """Read extra skill directories from user profile tool_paths."""
    from neo.memory.models import get_user_profile

    profile = get_user_profile(conn)
    if not profile:
        return []
    raw = profile.get("tool_paths", "{}")
    try:
        paths = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (json.JSONDecodeError, TypeError):
        return []
    dirs_raw = paths.get("skills_dirs", "")
    if isinstance(dirs_raw, list):
        return dirs_raw
    if isinstance(dirs_raw, str) and dirs_raw.strip():
        return [d.strip() for d in dirs_raw.split(",") if d.strip()]
    return []


def sync_skills_to_db(conn: sqlite3.Connection) -> int:
    """Scan skill files and upsert them into the skills table.

    Reads extra skill directories from user profile ``tool_paths.skills_dirs``.

    Returns:
        Number of skills synced.
    """
    extra_dirs = _get_extra_skill_dirs(conn)
    skills = load_all_skills(extra_dirs=extra_dirs)
    count = 0

    for skill in skills:
        upsert_skill(
            conn,
            name=skill["name"],
            file_path=skill["file_path"],
            skill_type=_detect_skill_type(skill["file_path"]),
            description=skill["description"],
            task_types=skill["task_types"],
        )
        count += 1

    logger.info("Synced %d skills to database", count)
    return count


def list_skills(conn: sqlite3.Connection) -> list[dict]:
    """Return all skills with their enabled status."""
    return get_enabled_skills(conn)


def toggle_skill(conn: sqlite3.Connection, skill_name: str, enabled: bool) -> bool:
    """Enable or disable a skill by name.

    Returns True if a skill was updated, False if not found.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "UPDATE skills SET is_enabled=?, updated_at=? WHERE name=?",
        (1 if enabled else 0, now, skill_name),
    )
    return cursor.rowcount > 0


def route_skill_with_name(command: str, conn: sqlite3.Connection) -> tuple[str, str]:
    """Match a user command to the best skill and return (name, content).

    Returns:
        Tuple of (skill_name, skill_content), or ("", "") if no match.
    """
    words = set(command.lower().split())

    enabled = get_enabled_skills(conn)
    best_skill = None
    best_score = 0

    for skill_row in enabled:
        task_types = skill_row.get("task_types", "[]")
        if isinstance(task_types, str):
            try:
                task_types = json.loads(task_types)
            except (json.JSONDecodeError, TypeError):
                task_types = []

        score = len(words & set(t.lower() for t in task_types))
        if score > best_score:
            best_score = score
            best_skill = skill_row

    if best_skill and best_skill.get("file_path"):
        parsed = parse_skill_file(best_skill["file_path"])
        if parsed:
            return parsed["name"], parsed["content"]

    return "", ""


def create_user_skill(
    conn: sqlite3.Connection,
    name: str,
    description: str,
    task_types: list[str],
    content: str,
    tools: list[str] | None = None,
) -> str:
    """Create a user skill file in the user/ directory and register it in DB.

    Args:
        conn: SQLite connection.
        name: Skill name (used as filename, e.g., 'monthly_report').
        description: What this skill does.
        task_types: Keywords that trigger this skill.
        content: Markdown body with LLM instructions.
        tools: Optional list of tools this skill uses.

    Returns:
        Path to the created skill file.
    """
    # Sanitize name for filename
    safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower().strip())
    if not safe_name:
        raise ValueError("Skill name cannot be empty.")

    os.makedirs(_USER_SKILLS_DIR, exist_ok=True)
    file_path = os.path.join(_USER_SKILLS_DIR, f"{safe_name}.md")

    # Build skill file content
    tools_list = tools or []
    frontmatter = (
        f"---\n"
        f"name: {safe_name}\n"
        f"description: {description}\n"
        f"task_types: [{', '.join(task_types)}]\n"
        f"tools: [{', '.join(tools_list)}]\n"
        f"---\n"
    )
    full_content = frontmatter + "\n" + content.strip() + "\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    # Register in DB
    upsert_skill(
        conn,
        name=safe_name,
        file_path=file_path,
        skill_type="user",
        description=description,
        task_types=task_types,
    )

    logger.info("Created user skill '%s' at %s", safe_name, file_path)
    return file_path


def route_skill(command: str, conn: sqlite3.Connection) -> str:
    """Match a user command to the best skill and return its content.

    Routing strategy (simple keyword matching for P0):
    1. Tokenize the command into lowercase words
    2. Check each enabled skill's task_types for overlap
    3. Return the content of the best match (most keyword hits)

    Returns:
        Skill content string, or empty string if no match.
    """
    words = set(command.lower().split())

    # Try DB-based routing first (skills registered via sync)
    enabled = get_enabled_skills(conn)
    best_skill = None
    best_score = 0

    for skill_row in enabled:
        task_types = skill_row.get("task_types", "[]")
        if isinstance(task_types, str):
            try:
                task_types = json.loads(task_types)
            except (json.JSONDecodeError, TypeError):
                task_types = []

        score = len(words & set(t.lower() for t in task_types))
        if score > best_score:
            best_score = score
            best_skill = skill_row

    if best_skill and best_skill.get("file_path"):
        parsed = parse_skill_file(best_skill["file_path"])
        if parsed:
            return parsed["content"]

    return ""
