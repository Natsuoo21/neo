"""Tests for neo.tools.google_auth — OAuth2 credential management."""

from unittest.mock import MagicMock, patch

from neo.tools import google_auth


class TestIsConfigured:
    def test_not_configured(self, tmp_path):
        with patch.object(google_auth, "_CREDENTIALS_PATH", tmp_path / "nonexistent.json"):
            assert google_auth.is_configured() is False

    def test_configured(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text("{}")
        with patch.object(google_auth, "_CREDENTIALS_PATH", cred_file):
            assert google_auth.is_configured() is True


class TestIsAuthenticated:
    def test_not_authenticated(self, tmp_path):
        with patch.object(google_auth, "_TOKEN_PATH", tmp_path / "nonexistent.json"):
            assert google_auth.is_authenticated() is False

    def test_authenticated(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        with patch.object(google_auth, "_TOKEN_PATH", token_file):
            assert google_auth.is_authenticated() is True


class TestGetCredentials:
    def test_not_configured_returns_none(self, tmp_path):
        with patch.object(google_auth, "_CREDENTIALS_PATH", tmp_path / "nonexistent.json"):
            assert google_auth.get_credentials() is None

    def test_valid_credentials(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = True

        with (
            patch.object(google_auth, "_CREDENTIALS_PATH", cred_file),
            patch.object(google_auth, "_TOKEN_PATH", tmp_path / "token.json"),
            patch("neo.tools.google_auth.Credentials"),
        ):
            # Token file doesn't exist → returns None (no creds to load)
            result = google_auth.get_credentials()
            assert result is None

    def test_expired_credentials_refresh(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text("{}")
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh-token"
        mock_creds.to_json.return_value = '{"token": "test"}'

        with (
            patch.object(google_auth, "_CREDENTIALS_PATH", cred_file),
            patch.object(google_auth, "_TOKEN_PATH", token_file),
            patch.object(google_auth, "_DATA_DIR", tmp_path),
            patch("neo.tools.google_auth.Credentials") as MockCreds,
        ):
            MockCreds.from_authorized_user_file.return_value = mock_creds

            with patch("neo.tools.google_auth.Request"):
                result = google_auth.get_credentials()
                mock_creds.refresh.assert_called_once()
                assert result == mock_creds


class TestRunOAuthFlow:
    def test_not_configured(self, tmp_path):
        with patch.object(google_auth, "_CREDENTIALS_PATH", tmp_path / "nonexistent.json"):
            assert google_auth.run_oauth_flow() is None

    def test_successful_flow(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "test"}'

        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds

        with (
            patch.object(google_auth, "_CREDENTIALS_PATH", cred_file),
            patch.object(google_auth, "_TOKEN_PATH", tmp_path / "token.json"),
            patch.object(google_auth, "_DATA_DIR", tmp_path),
            patch("neo.tools.google_auth.InstalledAppFlow") as MockFlow,
        ):
            MockFlow.from_client_secrets_file.return_value = mock_flow
            result = google_auth.run_oauth_flow()

            assert result == mock_creds
            mock_flow.run_local_server.assert_called_once_with(port=0)
