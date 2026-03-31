"""Seed data — Initialize user profile and default data on first run."""

import json
import logging
import sqlite3
from pathlib import Path

from neo.memory.models import get_user_profile, upsert_user_profile

logger = logging.getLogger(__name__)

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

# Expected keys in a valid seed profile
_REQUIRED_KEYS = {"name"}
_ALLOWED_KEYS = {"name", "role", "preferences", "tool_paths"}


def _validate_seed_profile(profile: dict) -> dict:
    """Validate and sanitize a seed profile dict.

    Returns the profile if valid, or the default profile on invalid input.
    """
    if not isinstance(profile, dict):
        logger.warning("Seed profile is not a dict, using defaults")
        return _DEFAULT_PROFILE

    if not _REQUIRED_KEYS.issubset(profile.keys()):
        logger.warning("Seed profile missing required keys %s, using defaults", _REQUIRED_KEYS - profile.keys())
        return _DEFAULT_PROFILE

    if not isinstance(profile["name"], str) or not profile["name"].strip():
        logger.warning("Seed profile has invalid 'name', using defaults")
        return _DEFAULT_PROFILE

    # Filter to allowed keys only
    return {k: v for k, v in profile.items() if k in _ALLOWED_KEYS}


def seed_user_profile(conn: sqlite3.Connection) -> bool:
    """Seed the user profile if it doesn't exist.

    Uses user_profile.json if present and valid, otherwise uses defaults.
    Returns True if a profile was created.
    """
    existing = get_user_profile(conn)
    if existing:
        return False

    # Load from file if it exists, otherwise use defaults
    if _SEED_PROFILE_PATH.exists():
        try:
            raw = json.loads(_SEED_PROFILE_PATH.read_text())
            profile = _validate_seed_profile(raw)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load seed profile: %s, using defaults", e)
            profile = _DEFAULT_PROFILE
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
