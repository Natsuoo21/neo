"""Auto-updater — checks GitHub Releases for new versions.

Runs a weekly background check (configurable) and broadcasts an SSE
event when a newer release is found. Does NOT auto-install — only
notifies the user via the frontend tray/banner.

Usage::

    checker = UpdateChecker("Natsuoo21", "neo", "0.1.0")
    info = checker.check()
    if info:
        print(f"New version available: {info['tag']}")
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_TIMEOUT = 10


class UpdateChecker:
    """Compares current version against latest GitHub release."""

    def __init__(
        self,
        owner: str = "Natsuoo21",
        repo: str = "neo",
        current_version: str = "0.1.0",
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.current_version = current_version

    def check(self) -> dict | None:
        """Check for a newer release on GitHub.

        Returns dict with release info if a newer version exists,
        or None if already up-to-date or check fails.

        Return keys: tag, name, url, published_at, body
        """
        try:
            url = f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/releases/latest"
            resp = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)

            if resp.status_code == 404:
                logger.debug("No releases found for %s/%s", self.owner, self.repo)
                return None

            resp.raise_for_status()
            data = resp.json()

            tag = data.get("tag_name", "")
            remote_version = tag.lstrip("v")

            if _is_newer(remote_version, self.current_version):
                info = {
                    "tag": tag,
                    "name": data.get("name", tag),
                    "url": data.get("html_url", ""),
                    "published_at": data.get("published_at", ""),
                    "body": data.get("body", ""),
                }
                logger.info("New version available: %s (current: %s)", tag, self.current_version)
                return info

            logger.debug("Up to date (current: %s, latest: %s)", self.current_version, tag)
            return None

        except (httpx.HTTPError, ValueError, KeyError):
            logger.exception("Update check failed")
            return None


def _is_newer(remote: str, current: str) -> bool:
    """Compare semver-ish version strings. Returns True if remote > current."""
    try:
        r_parts = [int(x) for x in remote.split(".")]
        c_parts = [int(x) for x in current.split(".")]
        # Pad shorter list with zeros
        while len(r_parts) < len(c_parts):
            r_parts.append(0)
        while len(c_parts) < len(r_parts):
            c_parts.append(0)
        return r_parts > c_parts
    except (ValueError, AttributeError):
        return False
