"""CRUD operations for remote MCP server configurations.

Remote servers are stored in ``~/.neo/remotes.json`` as a JSON array of
server descriptors.  Each descriptor has at minimum a ``name``,
``transport``, and ``url``.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_REMOTES_PATH = Path.home() / ".neo" / "remotes.json"

_VALID_TRANSPORTS = {"sse", "streamable_http"}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_remote_config(config: dict) -> list[str]:
    """Validate a remote server config dict.

    Returns a list of error strings (empty means valid).
    """
    errors: list[str] = []

    if not config.get("name"):
        errors.append("'name' is required.")

    transport = config.get("transport", "")
    if transport not in _VALID_TRANSPORTS:
        errors.append(f"'transport' must be one of {sorted(_VALID_TRANSPORTS)}. Got: '{transport}'.")

    if not config.get("url"):
        errors.append("'url' is required for remote servers.")

    auth = config.get("auth")
    if auth is not None:
        if not isinstance(auth, dict):
            errors.append("'auth' must be an object with 'type' and optionally 'token_env'.")
        else:
            if auth.get("type") not in (None, "bearer", "api_key", "header"):
                errors.append(f"auth.type must be 'bearer', 'api_key', or 'header'. Got: '{auth.get('type')}'.")

    return errors


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------


def load_remotes(path: Path | None = None) -> list[dict]:
    """Load remote server configs from the JSON file.

    Returns an empty list if the file does not exist.
    """
    path = path or _DEFAULT_REMOTES_PATH
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning("remotes.json is not a JSON array — returning empty list")
            return []
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read remotes.json: %s", exc)
        return []


def save_remotes(remotes: list[dict], path: Path | None = None) -> None:
    """Write remote server configs to the JSON file."""
    path = path or _DEFAULT_REMOTES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(remotes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Add / Remove
# ---------------------------------------------------------------------------


def add_remote(config: dict, path: Path | None = None) -> None:
    """Append a new remote server config.

    Raises ``ValueError`` if the config is invalid or a server with the
    same name already exists.
    """
    errors = validate_remote_config(config)
    if errors:
        raise ValueError("Invalid remote config: " + "; ".join(errors))

    remotes = load_remotes(path)
    names = {r["name"] for r in remotes}
    if config["name"] in names:
        raise ValueError(f"Remote server '{config['name']}' already exists.")

    remotes.append(config)
    save_remotes(remotes, path)


def remove_remote(name: str, path: Path | None = None) -> bool:
    """Remove a remote server by name.

    Returns ``True`` if removed, ``False`` if not found.
    """
    remotes = load_remotes(path)
    filtered = [r for r in remotes if r.get("name") != name]
    if len(filtered) == len(remotes):
        return False
    save_remotes(filtered, path)
    return True
