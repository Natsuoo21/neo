"""Tests for the remotes CRUD module."""

import json
import tempfile
from pathlib import Path

import pytest

from neo.plugins.remotes import (
    add_remote,
    load_remotes,
    remove_remote,
    save_remotes,
    validate_remote_config,
)


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "remotes.json"


# ============================================
# Validation
# ============================================


class TestValidation:
    def test_valid_config(self):
        cfg = {
            "name": "test-server",
            "transport": "streamable_http",
            "url": "https://api.example.com/mcp",
        }
        assert validate_remote_config(cfg) == []

    def test_missing_name(self):
        cfg = {"transport": "sse", "url": "https://example.com"}
        errors = validate_remote_config(cfg)
        assert any("name" in e for e in errors)

    def test_missing_url(self):
        cfg = {"name": "test", "transport": "sse"}
        errors = validate_remote_config(cfg)
        assert any("url" in e for e in errors)

    def test_invalid_transport(self):
        cfg = {"name": "test", "transport": "stdio", "url": "https://example.com"}
        errors = validate_remote_config(cfg)
        assert any("transport" in e for e in errors)

    def test_valid_auth(self):
        cfg = {
            "name": "test",
            "transport": "sse",
            "url": "https://example.com",
            "auth": {"type": "bearer", "token_env": "MY_TOKEN"},
        }
        assert validate_remote_config(cfg) == []

    def test_invalid_auth_type(self):
        cfg = {
            "name": "test",
            "transport": "sse",
            "url": "https://example.com",
            "auth": {"type": "invalid"},
        }
        errors = validate_remote_config(cfg)
        assert any("auth.type" in e for e in errors)

    def test_auth_not_dict(self):
        cfg = {
            "name": "test",
            "transport": "sse",
            "url": "https://example.com",
            "auth": "not-a-dict",
        }
        errors = validate_remote_config(cfg)
        assert any("auth" in e for e in errors)


# ============================================
# Load / Save
# ============================================


class TestLoadSave:
    def test_load_nonexistent_returns_empty(self, tmp_path):
        assert load_remotes(tmp_path) == []

    def test_save_and_load(self, tmp_path):
        data = [{"name": "s1", "transport": "sse", "url": "https://example.com"}]
        save_remotes(data, tmp_path)
        assert load_remotes(tmp_path) == data

    def test_load_corrupted_returns_empty(self, tmp_path):
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text("not json", encoding="utf-8")
        assert load_remotes(tmp_path) == []

    def test_load_non_array_returns_empty(self, tmp_path):
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text('{"key": "value"}', encoding="utf-8")
        assert load_remotes(tmp_path) == []


# ============================================
# Add / Remove
# ============================================


class TestAddRemove:
    def test_add_remote(self, tmp_path):
        cfg = {"name": "s1", "transport": "sse", "url": "https://example.com"}
        add_remote(cfg, tmp_path)
        remotes = load_remotes(tmp_path)
        assert len(remotes) == 1
        assert remotes[0]["name"] == "s1"

    def test_add_duplicate_raises(self, tmp_path):
        cfg = {"name": "s1", "transport": "sse", "url": "https://example.com"}
        add_remote(cfg, tmp_path)
        with pytest.raises(ValueError, match="already exists"):
            add_remote(cfg, tmp_path)

    def test_add_invalid_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid remote"):
            add_remote({"name": ""}, tmp_path)

    def test_remove_existing(self, tmp_path):
        cfg = {"name": "s1", "transport": "sse", "url": "https://example.com"}
        add_remote(cfg, tmp_path)
        assert remove_remote("s1", tmp_path) is True
        assert load_remotes(tmp_path) == []

    def test_remove_nonexistent(self, tmp_path):
        assert remove_remote("nope", tmp_path) is False
