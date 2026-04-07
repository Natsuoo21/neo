"""GitHub skill importer — download .md skill files from GitHub repos.

Supports:
- Single file:  github.com/user/repo/blob/main/skill.md
- Directory:    github.com/user/repo/tree/main/skills/
- Raw URLs:     raw.githubusercontent.com/...

Downloaded skills are validated (must have YAML frontmatter with ``name``)
and saved to the ``community/`` directory.
"""

import logging
import os
import re
import tempfile

import httpx

from neo.memory.models import upsert_skill
from neo.skills.loader import _COMMUNITY_SKILLS_DIR, parse_skill_file

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_RAW_BASE = "https://raw.githubusercontent.com"


def to_raw_url(url: str) -> str | None:
    """Convert a GitHub web URL to a raw content URL.

    Handles:
    - ``github.com/user/repo/blob/branch/path`` → raw URL
    - ``raw.githubusercontent.com/...`` → returned as-is

    Returns None if the URL is not a recognised GitHub file URL.
    """
    # Already a raw URL
    if "raw.githubusercontent.com" in url:
        return url

    # github.com/user/repo/blob/branch/path/to/file.md
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/blob/(.+)", url
    )
    if m:
        user, repo, rest = m.group(1), m.group(2), m.group(3)
        return f"{_RAW_BASE}/{user}/{repo}/{rest}"

    return None


def _parse_tree_url(url: str) -> tuple[str, str, str] | None:
    """Parse ``github.com/user/repo/tree/branch/path`` into (user, repo, branch/path)."""
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/tree/(.+)", url
    )
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None


def download_and_validate(url: str, *, timeout: float = 30) -> dict:
    """Download a single .md file and validate its frontmatter.

    Returns:
        Parsed skill dict (from ``parse_skill_file``), or empty dict on failure.
    """
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("Failed to download %s: %s", url, e)
        return {}

    content = resp.text

    # Write to temp file for parse_skill_file (it reads from disk)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        parsed = parse_skill_file(tmp_path)
    finally:
        os.unlink(tmp_path)

    return parsed


def _save_to_community(parsed: dict) -> str:
    """Write a validated skill dict to the community/ directory.

    Returns the saved file path.
    """
    safe_name = re.sub(r"[^a-z0-9_]", "_", parsed["name"].lower().strip())
    os.makedirs(_COMMUNITY_SKILLS_DIR, exist_ok=True)
    file_path = os.path.join(_COMMUNITY_SKILLS_DIR, f"{safe_name}.md")

    tools_list = parsed.get("tools", [])
    task_types = parsed.get("task_types", [])
    frontmatter = (
        f"---\n"
        f"name: {safe_name}\n"
        f"description: {parsed.get('description', '')}\n"
        f"task_types: [{', '.join(task_types)}]\n"
        f"tools: [{', '.join(tools_list)}]\n"
        f"---\n"
    )
    full_content = frontmatter + "\n" + parsed["content"].strip() + "\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    return file_path


def import_single_file(
    url: str,
    conn: "sqlite3.Connection",  # noqa: F821
    *,
    timeout: float = 30,
) -> dict | None:
    """Import a single skill file from a GitHub URL.

    Returns the imported skill dict, or None on failure.
    """
    raw_url = to_raw_url(url)
    if raw_url is None:
        logger.error("Cannot convert URL to raw: %s", url)
        return None

    parsed = download_and_validate(raw_url, timeout=timeout)
    if not parsed:
        return None

    file_path = _save_to_community(parsed)

    upsert_skill(
        conn,
        name=parsed["name"],
        file_path=file_path,
        skill_type="community",
        description=parsed.get("description", ""),
        task_types=parsed.get("task_types", []),
    )

    logger.info("Imported skill '%s' from %s", parsed["name"], url)
    return parsed


def import_directory(
    url: str,
    conn: "sqlite3.Connection",  # noqa: F821
    *,
    timeout: float = 30,
) -> list[dict]:
    """Import all .md skill files from a GitHub directory URL.

    Uses the GitHub API to list directory contents, then downloads each .md file.

    Returns list of imported skill dicts.
    """
    parts = _parse_tree_url(url)
    if parts is None:
        logger.error("Cannot parse GitHub tree URL: %s", url)
        return []

    user, repo, branch_path = parts
    api_url = f"{_GITHUB_API}/repos/{user}/{repo}/contents/{branch_path.split('/', 1)[1] if '/' in branch_path else ''}"
    ref = branch_path.split("/", 1)[0] if "/" in branch_path else branch_path

    try:
        resp = httpx.get(
            api_url,
            params={"ref": ref},
            timeout=timeout,
            follow_redirects=True,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.error("GitHub API error for %s: %s", api_url, e)
        return []

    entries = resp.json()
    if not isinstance(entries, list):
        logger.error("Expected directory listing, got: %s", type(entries).__name__)
        return []

    imported = []
    for entry in entries:
        if entry.get("type") != "file" or not entry.get("name", "").endswith(".md"):
            continue

        download_url = entry.get("download_url", "")
        if not download_url:
            continue

        parsed = download_and_validate(download_url, timeout=timeout)
        if not parsed:
            continue

        file_path = _save_to_community(parsed)
        upsert_skill(
            conn,
            name=parsed["name"],
            file_path=file_path,
            skill_type="community",
            description=parsed.get("description", ""),
            task_types=parsed.get("task_types", []),
        )
        imported.append(parsed)
        logger.info("Imported skill '%s' from directory", parsed["name"])

    return imported


def import_from_github(
    url: str,
    conn: "sqlite3.Connection",  # noqa: F821
    *,
    timeout: float = 30,
) -> list[dict]:
    """Smart import — detect whether URL is a single file or directory.

    Returns list of imported skill dicts.
    """
    # Directory URL (tree)
    if "/tree/" in url:
        return import_directory(url, conn, timeout=timeout)

    # Single file URL (blob or raw)
    result = import_single_file(url, conn, timeout=timeout)
    return [result] if result else []
