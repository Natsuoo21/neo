"""Secure credential storage for MCP remote server tokens.

Tokens are resolved in priority order:
1. Environment variable (preferred — no file I/O)
2. ``~/.neo/secrets.json`` (fallback — file with 0600 permissions)
"""

import json
import logging
import os
import stat
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_SECRETS_PATH = Path.home() / ".neo" / "secrets.json"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_secret(name: str, path: Path | None = None) -> str | None:
    """Retrieve a secret by server name.

    Checks the environment variable ``name`` first, then falls back to
    ``~/.neo/secrets.json``.
    """
    if not name:
        return None

    # 1. Environment variable
    value = os.environ.get(name)
    if value:
        return value

    # 2. Secrets file
    path = path or _DEFAULT_SECRETS_PATH
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get(name)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read secrets.json: %s", exc)

    return None


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def set_secret(name: str, value: str, path: Path | None = None) -> None:
    """Store a secret in ``~/.neo/secrets.json``.

    Creates the file with 0600 permissions if it does not exist.
    """
    path = path or _DEFAULT_SECRETS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing
    data: dict[str, str] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            pass

    data[name] = value
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Restrict permissions (owner read/write only)
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Windows may not support chmod — log and continue
        logger.debug("Could not set 0600 permissions on %s", path)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def delete_secret(name: str, path: Path | None = None) -> bool:
    """Remove a secret from ``~/.neo/secrets.json``.

    Returns ``True`` if the key was found and removed.
    """
    path = path or _DEFAULT_SECRETS_PATH
    if not path.exists():
        return False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or name not in data:
            return False
        del data[name]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return True
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to update secrets.json: %s", exc)
        return False
