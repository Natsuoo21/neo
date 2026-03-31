"""Seed data — Initialize user profile and default data on first run."""

import json
import sqlite3
from pathlib import Path

from neo.memory.models import get_user_profile, upsert_user_profile

# Default user profile template
_DEFAULT_PROFILE = {
    "name": "User",
    "role": "Professional",
    "preferences": {
        "language": "en",
        "timezone": "America/Sao_Paulo",
        "writing_style": "professional",
    },
    "tool_paths": {
        "obsidian_vault": "",
        "default_save_dir": "~/Documents/Neo",
        "downloads_dir": "~/Downloads",
    },
}

_SEED_PROFILE_PATH = Path(__file__).parent / "user_profile.json"


def seed_user_profile(conn: sqlite3.Connection) -> bool:
    """Seed the user profile if it doesn't exist.

    Uses user_profile.json if present, otherwise uses defaults.
    Returns True if a profile was created.
    """
    existing = get_user_profile(conn)
    if existing:
        return False

    # Load from file if it exists, otherwise use defaults
    if _SEED_PROFILE_PATH.exists():
        profile = json.loads(_SEED_PROFILE_PATH.read_text())
    else:
        profile = _DEFAULT_PROFILE

    upsert_user_profile(
        conn,
        name=profile["name"],
        role=profile.get("role", ""),
        preferences=profile.get("preferences"),
        tool_paths=profile.get("tool_paths"),
    )
    return True
