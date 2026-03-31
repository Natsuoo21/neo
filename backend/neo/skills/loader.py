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
"""

import logging
import os
import sqlite3

from neo.memory.models import get_enabled_skills, upsert_skill

logger = logging.getLogger(__name__)

# Directories to scan for skill files
_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "public")
_USER_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "user")


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


def load_all_skills() -> list[dict]:
    """Load all skill files from public/ and user/ directories.

    Returns:
        List of parsed skill dicts.
    """
    skills = []

    for skills_dir in [_SKILLS_DIR, _USER_SKILLS_DIR]:
        if not os.path.isdir(skills_dir):
            continue
        for filename in sorted(os.listdir(skills_dir)):
            if not filename.endswith(".md"):
                continue
            file_path = os.path.join(skills_dir, filename)
            skill = parse_skill_file(file_path)
            if skill:
                skills.append(skill)

    return skills


def sync_skills_to_db(conn: sqlite3.Connection) -> int:
    """Scan skill files and upsert them into the skills table.

    Returns:
        Number of skills synced.
    """
    skills = load_all_skills()
    count = 0

    for skill in skills:
        upsert_skill(
            conn,
            name=skill["name"],
            file_path=skill["file_path"],
            skill_type="public" if "/public/" in skill["file_path"] else "user",
            description=skill["description"],
            task_types=skill["task_types"],
        )
        count += 1

    conn.commit()
    logger.info("Synced %d skills to database", count)
    return count


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
            # task_types is stored as JSON string in DB
            import json

            try:
                task_types = json.loads(task_types)
            except (json.JSONDecodeError, TypeError):
                task_types = []

        score = len(words & set(task_types))
        if score > best_score:
            best_score = score
            best_skill = skill_row

    if best_skill and best_skill.get("file_path"):
        parsed = parse_skill_file(best_skill["file_path"])
        if parsed:
            return parsed["content"]

    return ""
