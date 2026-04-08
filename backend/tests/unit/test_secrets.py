"""Tests for the secrets credential storage module."""

import json
import tempfile
from pathlib import Path

import pytest

from neo.plugins.secrets import delete_secret, get_secret, set_secret


@pytest.fixture
def secrets_path():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "secrets.json"


# ============================================
# get_secret
# ============================================


class TestGetSecret:
    def test_from_env_var(self, monkeypatch, secrets_path):
        monkeypatch.setenv("MY_KEY", "env_value")
        assert get_secret("MY_KEY", secrets_path) == "env_value"

    def test_from_file(self, secrets_path):
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        secrets_path.write_text('{"server1": "file_token"}', encoding="utf-8")
        assert get_secret("server1", secrets_path) == "file_token"

    def test_env_takes_priority(self, monkeypatch, secrets_path):
        monkeypatch.setenv("server1", "env_token")
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        secrets_path.write_text('{"server1": "file_token"}', encoding="utf-8")
        assert get_secret("server1", secrets_path) == "env_token"

    def test_missing_returns_none(self, secrets_path):
        assert get_secret("nonexistent", secrets_path) is None

    def test_empty_name_returns_none(self, secrets_path):
        assert get_secret("", secrets_path) is None

    def test_corrupted_file_returns_none(self, secrets_path):
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        secrets_path.write_text("bad json", encoding="utf-8")
        assert get_secret("key", secrets_path) is None


# ============================================
# set_secret
# ============================================


class TestSetSecret:
    def test_creates_file(self, secrets_path):
        set_secret("key1", "value1", secrets_path)
        assert secrets_path.exists()
        data = json.loads(secrets_path.read_text(encoding="utf-8"))
        assert data["key1"] == "value1"

    def test_appends_to_existing(self, secrets_path):
        set_secret("key1", "v1", secrets_path)
        set_secret("key2", "v2", secrets_path)
        data = json.loads(secrets_path.read_text(encoding="utf-8"))
        assert data == {"key1": "v1", "key2": "v2"}

    def test_overwrites_existing_key(self, secrets_path):
        set_secret("key1", "old", secrets_path)
        set_secret("key1", "new", secrets_path)
        data = json.loads(secrets_path.read_text(encoding="utf-8"))
        assert data["key1"] == "new"


# ============================================
# delete_secret
# ============================================


class TestDeleteSecret:
    def test_delete_existing(self, secrets_path):
        set_secret("key1", "val", secrets_path)
        assert delete_secret("key1", secrets_path) is True
        data = json.loads(secrets_path.read_text(encoding="utf-8"))
        assert "key1" not in data

    def test_delete_nonexistent(self, secrets_path):
        assert delete_secret("nope", secrets_path) is False

    def test_delete_from_missing_file(self, secrets_path):
        assert delete_secret("key", secrets_path) is False
