"""Tests for the MCP transport layer."""

import pytest

from neo.plugins.transports import (
    RemoteConfig,
    StdioConfig,
    TransportType,
    _build_auth_headers,
    resolve_auth_token,
    validate_url,
)


# ============================================
# URL Validation
# ============================================


class TestValidateUrl:
    def test_https_allowed(self):
        validate_url("https://api.example.com/mcp")  # Should not raise

    def test_http_localhost_allowed(self):
        validate_url("http://localhost:8080/mcp")
        validate_url("http://127.0.0.1:3000/sse")

    def test_http_remote_blocked(self):
        with pytest.raises(ValueError, match="only allowed for localhost"):
            validate_url("http://api.example.com/mcp")

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            validate_url("ftp://example.com/mcp")

    def test_missing_hostname(self):
        with pytest.raises(ValueError, match="missing hostname"):
            validate_url("https://")


# ============================================
# Auth token resolution
# ============================================


class TestResolveAuthToken:
    def test_from_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        config = RemoteConfig(url="https://example.com", token_env="MY_TOKEN")
        assert resolve_auth_token(config) == "secret123"

    def test_no_token_env(self):
        config = RemoteConfig(url="https://example.com")
        assert resolve_auth_token(config) is None

    def test_missing_env_var_falls_through(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_TOKEN", raising=False)
        config = RemoteConfig(url="https://example.com", token_env="NONEXISTENT_TOKEN")
        # Falls through to secrets file, which likely doesn't exist in tests
        result = resolve_auth_token(config)
        assert result is None


# ============================================
# Auth header building
# ============================================


class TestBuildAuthHeaders:
    def test_bearer_token(self, monkeypatch):
        monkeypatch.setenv("MY_TOKEN", "abc123")
        config = RemoteConfig(
            url="https://example.com",
            auth_type="bearer",
            token_env="MY_TOKEN",
        )
        headers = _build_auth_headers(config)
        assert headers["Authorization"] == "Bearer abc123"

    def test_api_key(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "key456")
        config = RemoteConfig(
            url="https://example.com",
            auth_type="api_key",
            token_env="API_KEY",
        )
        headers = _build_auth_headers(config)
        assert headers["X-API-Key"] == "key456"

    def test_no_auth(self):
        config = RemoteConfig(url="https://example.com")
        headers = _build_auth_headers(config)
        assert "Authorization" not in headers
        assert "X-API-Key" not in headers

    def test_preserves_custom_headers(self, monkeypatch):
        monkeypatch.setenv("TOK", "val")
        config = RemoteConfig(
            url="https://example.com",
            auth_type="bearer",
            token_env="TOK",
            headers={"X-Custom": "hello"},
        )
        headers = _build_auth_headers(config)
        assert headers["X-Custom"] == "hello"
        assert headers["Authorization"] == "Bearer val"


# ============================================
# Config dataclasses
# ============================================


class TestConfigs:
    def test_stdio_config_defaults(self):
        cfg = StdioConfig(command="python")
        assert cfg.args == []
        assert cfg.env == {}
        assert cfg.cwd is None

    def test_remote_config_defaults(self):
        cfg = RemoteConfig(url="https://example.com")
        assert cfg.auth_type is None
        assert cfg.token_env is None
        assert cfg.headers == {}

    def test_transport_type_values(self):
        assert TransportType.STDIO.value == "stdio"
        assert TransportType.SSE.value == "sse"
        assert TransportType.STREAMABLE_HTTP.value == "streamable_http"
