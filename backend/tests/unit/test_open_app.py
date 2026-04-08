"""Tests for the open_app tool module."""

from unittest.mock import MagicMock, patch

import pytest

from neo.tools.open_app import (
    _is_uri,
    _is_wsl,
    _resolve_alias,
    _validate_app,
    get_platform,
    open_app,
)


# ============================================
# Platform detection
# ============================================


class TestPlatformDetection:
    @patch("neo.tools.open_app.sys")
    def test_windows_platform(self, mock_sys):
        mock_sys.platform = "win32"
        assert get_platform() == "windows"

    @patch("neo.tools.open_app.sys")
    def test_macos_platform(self, mock_sys):
        mock_sys.platform = "darwin"
        assert get_platform() == "macos"

    @patch("neo.tools.open_app.sys")
    @patch("neo.tools.open_app.platform")
    def test_wsl_platform(self, mock_platform, mock_sys):
        mock_sys.platform = "linux"
        mock_platform.release.return_value = "5.15.0-1-microsoft-standard-WSL2"
        assert get_platform() == "wsl"

    @patch("neo.tools.open_app.sys")
    @patch("neo.tools.open_app.platform")
    def test_linux_platform(self, mock_platform, mock_sys):
        mock_sys.platform = "linux"
        mock_platform.release.return_value = "6.1.0-generic"
        assert get_platform() == "linux"

    @patch("neo.tools.open_app.sys")
    @patch("neo.tools.open_app.platform")
    def test_is_wsl_true(self, mock_platform, mock_sys):
        mock_sys.platform = "linux"
        mock_platform.release.return_value = "5.15.0-microsoft-standard"
        assert _is_wsl() is True

    @patch("neo.tools.open_app.sys")
    def test_is_wsl_false_on_windows(self, mock_sys):
        mock_sys.platform = "win32"
        assert _is_wsl() is False


# ============================================
# Alias resolution
# ============================================


class TestAliasResolution:
    @patch("neo.tools.open_app.get_platform", return_value="windows")
    def test_obsidian_alias(self, _mock):
        assert _resolve_alias("obsidian") == "obsidian://"

    @patch("neo.tools.open_app.get_platform", return_value="windows")
    def test_vscode_alias_windows(self, _mock):
        assert _resolve_alias("vscode") == "code"

    @patch("neo.tools.open_app.get_platform", return_value="macos")
    def test_chrome_alias_macos(self, _mock):
        assert _resolve_alias("chrome") == "Google Chrome"

    @patch("neo.tools.open_app.get_platform", return_value="linux")
    def test_chrome_alias_linux(self, _mock):
        assert _resolve_alias("chrome") == "google-chrome"

    def test_unknown_alias_passthrough(self):
        assert _resolve_alias("my-custom-app") == "my-custom-app"

    @patch("neo.tools.open_app.get_platform", return_value="windows")
    def test_case_insensitive(self, _mock):
        assert _resolve_alias("Obsidian") == "obsidian://"
        assert _resolve_alias("NOTEPAD") == "notepad.exe"


# ============================================
# URI detection
# ============================================


class TestUriDetection:
    def test_obsidian_uri(self):
        assert _is_uri("obsidian://open") is True

    def test_https_uri(self):
        assert _is_uri("https://example.com") is True

    def test_plain_app_name(self):
        assert _is_uri("notepad.exe") is False

    def test_uri_protocol_only(self):
        assert _is_uri("obsidian://") is True


# ============================================
# Safety validation
# ============================================


class TestSafety:
    def test_blocks_bat_files(self):
        with pytest.raises(ValueError, match="script file"):
            _validate_app("malicious.bat", "")

    def test_blocks_ps1_files(self):
        with pytest.raises(ValueError, match="script file"):
            _validate_app("hack.ps1", "")

    def test_blocks_sh_files(self):
        with pytest.raises(ValueError, match="script file"):
            _validate_app("danger.sh", "")

    def test_blocks_scripts_in_args(self):
        with pytest.raises(ValueError, match="arguments"):
            _validate_app("notepad.exe", "evil.bat")

    def test_allows_normal_app(self):
        _validate_app("notepad.exe", "")  # Should not raise

    def test_allows_uri(self):
        _validate_app("obsidian://open", "")  # Should not raise


# ============================================
# open_app dispatch
# ============================================


class TestOpenApp:
    @patch("neo.tools.open_app.get_platform", return_value="wsl")
    @patch("neo.tools.open_app.subprocess.Popen")
    def test_open_notepad_wsl(self, mock_popen, _mock_plat):
        result = open_app("notepad")
        assert "Opened" in result
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "cmd.exe"

    @patch("neo.tools.open_app.get_platform", return_value="wsl")
    @patch("neo.tools.open_app.subprocess.Popen")
    def test_open_obsidian_uri_wsl(self, mock_popen, _mock_plat):
        result = open_app("obsidian")
        assert "URI" in result
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert "cmd.exe" in call_args
        assert "obsidian://" in call_args[-1]

    @patch("neo.tools.open_app.get_platform", return_value="macos")
    @patch("neo.tools.open_app.subprocess.Popen")
    def test_open_chrome_macos(self, mock_popen, _mock_plat):
        result = open_app("chrome")
        assert "Opened" in result
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "open"
        assert call_args[1] == "-a"
        assert call_args[2] == "Google Chrome"

    @patch("neo.tools.open_app.get_platform", return_value="linux")
    @patch("neo.tools.open_app.subprocess.Popen")
    def test_open_uri_linux(self, mock_popen, _mock_plat):
        result = open_app("https://google.com")
        assert "URI" in result
        call_args = mock_popen.call_args[0][0]
        assert call_args[0] == "xdg-open"

    @patch("neo.tools.open_app.get_platform", return_value="wsl")
    @patch("neo.tools.open_app.subprocess.Popen", side_effect=FileNotFoundError)
    def test_app_not_found(self, _mock_popen, _mock_plat):
        with pytest.raises(RuntimeError, match="not found"):
            open_app("nonexistent-app-xyz")

    def test_blocked_script(self):
        with pytest.raises(ValueError, match="script"):
            open_app("evil.bat")

    @patch("neo.tools.open_app.get_platform", return_value="wsl")
    @patch("neo.tools.open_app.subprocess.Popen")
    def test_open_with_args(self, mock_popen, _mock_plat):
        result = open_app("notepad", args="file.txt")
        assert "file.txt" in result
        mock_popen.assert_called_once()
