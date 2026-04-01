"""Google OAuth2 authentication for Calendar and Gmail APIs.

Manages OAuth2 flow, token storage, and credential refresh.
Credentials are stored in the data/ directory.
"""

import logging
import signal
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_TOKEN_PATH = _DATA_DIR / "google_token.json"
_CREDENTIALS_PATH = _DATA_DIR / "google_credentials.json"
_CREDENTIAL_TIMEOUT_S = 30


@contextmanager
def _timeout(seconds: int):
    """Context manager that raises TimeoutError after N seconds (Unix only)."""
    def _handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds}s")

    try:
        old_handler = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(seconds)
        yield
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
    except (ValueError, OSError):
        # signal.alarm not available (e.g. Windows) — run without timeout
        yield


def is_configured() -> bool:
    """Check if Google OAuth credentials file exists."""
    return _CREDENTIALS_PATH.exists()


def is_authenticated() -> bool:
    """Check if a valid token exists (may need refresh)."""
    return _TOKEN_PATH.exists()


def get_credentials() -> Any:
    """Load and return valid Google credentials, refreshing if needed.

    Returns None if not configured or authentication failed.
    """
    if not is_configured():
        logger.warning("Google credentials file not found at %s", _CREDENTIALS_PATH)
        return None

    try:
        creds = None
        if _TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            with _timeout(_CREDENTIAL_TIMEOUT_S):
                creds.refresh(Request())
            _save_token(creds)
            return creds

        # No valid credentials — need full OAuth flow
        return None

    except TimeoutError:
        logger.error("Google credential refresh timed out after %ds", _CREDENTIAL_TIMEOUT_S)
        return None
    except Exception:
        logger.exception("Failed to load Google credentials")
        return None


def run_oauth_flow() -> Any:
    """Run the full OAuth2 flow (opens browser for consent).

    Returns Credentials on success, None on failure.
    """
    if not is_configured():
        logger.error("Cannot run OAuth flow: credentials file not found at %s", _CREDENTIALS_PATH)
        return None

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(_CREDENTIALS_PATH),
            scopes=_SCOPES,
        )
        creds = flow.run_local_server(port=0)
        _save_token(creds)
        logger.info("Google OAuth flow completed successfully")
        return creds

    except Exception:
        logger.exception("Google OAuth flow failed")
        return None


def _save_token(creds: Any) -> None:
    """Save credentials to token file."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(creds.to_json())
    logger.info("Google token saved to %s", _TOKEN_PATH)
