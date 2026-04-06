"""Tests for neo.updater — GitHub release version checker."""

from unittest.mock import MagicMock, patch

from neo.updater import UpdateChecker, _is_newer

# ---------------------------------------------------------------------------
# _is_newer version comparison
# ---------------------------------------------------------------------------


class TestIsNewer:
    def test_newer_patch(self):
        assert _is_newer("0.2.0", "0.1.0") is True

    def test_newer_minor(self):
        assert _is_newer("1.0.0", "0.9.9") is True

    def test_same_version(self):
        assert _is_newer("0.1.0", "0.1.0") is False

    def test_older_version(self):
        assert _is_newer("0.0.9", "0.1.0") is False

    def test_different_length(self):
        assert _is_newer("1.0.0.1", "1.0.0") is True

    def test_padding(self):
        assert _is_newer("1.0", "1.0.0") is False

    def test_invalid_remote(self):
        assert _is_newer("abc", "0.1.0") is False

    def test_invalid_current(self):
        assert _is_newer("0.2.0", "abc") is False

    def test_both_invalid(self):
        assert _is_newer("abc", "def") is False

    def test_empty_string(self):
        assert _is_newer("", "0.1.0") is False

    def test_prerelease_tag(self):
        # Pre-release tags with non-numeric parts return False (safe default)
        assert _is_newer("1.0.0-beta", "0.9.0") is False


# ---------------------------------------------------------------------------
# UpdateChecker
# ---------------------------------------------------------------------------


class TestUpdateChecker:
    def test_defaults(self):
        checker = UpdateChecker()
        assert checker.owner == "Natsuoo21"
        assert checker.repo == "neo"
        assert checker.current_version == "0.1.0"

    @patch("neo.updater.httpx.get")
    def test_newer_version_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v0.2.0",
            "name": "Release 0.2.0",
            "html_url": "https://github.com/Natsuoo21/neo/releases/v0.2.0",
            "published_at": "2026-01-01T00:00:00Z",
            "body": "What's new",
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        checker = UpdateChecker(current_version="0.1.0")
        info = checker.check()
        assert info is not None
        assert info["tag"] == "v0.2.0"
        assert info["url"] == "https://github.com/Natsuoo21/neo/releases/v0.2.0"

    @patch("neo.updater.httpx.get")
    def test_up_to_date(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"tag_name": "v0.1.0"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        checker = UpdateChecker(current_version="0.1.0")
        assert checker.check() is None

    @patch("neo.updater.httpx.get")
    def test_no_releases(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        checker = UpdateChecker()
        assert checker.check() is None

    @patch("neo.updater.httpx.get")
    def test_network_error(self, mock_get):
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        checker = UpdateChecker()
        assert checker.check() is None

    @patch("neo.updater.httpx.get")
    def test_strips_v_prefix(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"tag_name": "v0.2.0"}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        checker = UpdateChecker(current_version="0.1.0")
        info = checker.check()
        assert info is not None
