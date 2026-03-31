"""Tests for Neo HTTP server (JSON-RPC 2.0)."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

import neo.server as srv
from neo.memory.db import get_session, init_schema
from neo.memory.seed import seed_user_profile
from neo.server import app
from neo.skills.loader import sync_skills_to_db


class _MockProvider:
    """Minimal mock LLM provider with sync name() and async complete_with_tools()."""

    def name(self) -> str:
        return "mock"

    async def complete(self, system: str, user: str) -> str:
        return "Hello from mock!"

    async def complete_with_tools(self, system, user, tools, messages=None):
        return {"type": "text", "content": "Hello from mock!"}


@pytest.fixture(autouse=True)
def _patch_server_state(monkeypatch):
    """Inject temp file DB and mock provider into server module.

    Also patches bootstrap helpers so the lifespan (triggered by TestClient)
    reuses our mock state instead of building its own.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    init_schema(db_path)
    with get_session(db_path) as conn:
        seed_user_profile(conn)
        sync_skills_to_db(conn)

    mock_registry = {"CLAUDE": _MockProvider()}

    # Patch bootstrap so lifespan doesn't overwrite our state
    monkeypatch.setattr(srv, "_bootstrap", lambda db=None: db_path)
    monkeypatch.setattr(srv, "_build_provider_registry", lambda: dict(mock_registry))

    async def _noop_ollama(reg):
        pass

    monkeypatch.setattr(srv, "_check_ollama", _noop_ollama)

    # Also set module-level state directly (used by handlers)
    monkeypatch.setattr(srv, "_db_path", db_path)
    monkeypatch.setattr(srv, "_registry", mock_registry)

    yield

    os.unlink(db_path)


@pytest.fixture
def client():
    """Sync test client — lifespan runs but uses our patched bootstrap."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---- Health -----------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "providers" in data


# ---- JSON-RPC basics --------------------------------------------------------

def _rpc(client, method, params=None, rpc_id=1):
    payload = {"jsonrpc": "2.0", "method": method, "id": rpc_id}
    if params is not None:
        payload["params"] = params
    return client.post("/rpc", json=payload)


def test_rpc_health(client):
    r = _rpc(client, "neo.health")
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    assert data["result"]["status"] == "ok"


def test_rpc_method_not_found(client):
    r = _rpc(client, "neo.nonexistent")
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32601


def test_rpc_parse_error(client):
    r = client.post("/rpc", content="not json", headers={"content-type": "application/json"})
    assert r.status_code == 200
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32700


# ---- neo.execute ------------------------------------------------------------

def test_execute(client):
    r = _rpc(client, "neo.execute", {"command": "hello"})
    data = r.json()["result"]
    assert data["status"] == "success"
    assert data["message"] == "Hello from mock!"
    assert "session_id" in data


def test_execute_missing_command(client):
    r = _rpc(client, "neo.execute", {"command": ""})
    data = r.json()
    assert "error" in data


# ---- neo.conversation.* -----------------------------------------------------

def test_conversation_new(client):
    r = _rpc(client, "neo.conversation.new")
    data = r.json()["result"]
    assert "session_id" in data
    assert len(data["session_id"]) == 36  # UUID


def test_conversation_list(client):
    # Execute a command first to create a conversation
    _rpc(client, "neo.execute", {"command": "hi", "session_id": "test-session-1"})
    r = _rpc(client, "neo.conversation.list")
    data = r.json()["result"]
    assert "sessions" in data


def test_conversation_load(client):
    session_id = "test-load-session"
    _rpc(client, "neo.execute", {"command": "hello", "session_id": session_id})
    r = _rpc(client, "neo.conversation.load", {"session_id": session_id})
    data = r.json()["result"]
    assert data["session_id"] == session_id
    assert len(data["messages"]) >= 1


def test_conversation_load_missing_session(client):
    r = _rpc(client, "neo.conversation.load", {"session_id": ""})
    data = r.json()
    assert "error" in data


# ---- neo.skills.* -----------------------------------------------------------

def test_skills_list(client):
    r = _rpc(client, "neo.skills.list")
    data = r.json()["result"]
    assert "skills" in data
    assert isinstance(data["skills"], list)


def test_skills_toggle(client):
    # Get a skill name first
    r = _rpc(client, "neo.skills.list")
    skills = r.json()["result"]["skills"]
    if skills:
        name = skills[0]["name"]
        r = _rpc(client, "neo.skills.toggle", {"name": name, "enabled": False})
        data = r.json()["result"]
        assert data["updated"] is True
        assert data["enabled"] is False


def test_skills_toggle_missing_name(client):
    r = _rpc(client, "neo.skills.toggle", {"name": "", "enabled": True})
    data = r.json()
    assert "error" in data


# ---- neo.actions.recent -----------------------------------------------------

def test_actions_recent(client):
    # Execute something to create an action
    _rpc(client, "neo.execute", {"command": "test action"})
    r = _rpc(client, "neo.actions.recent")
    data = r.json()["result"]
    assert "actions" in data
    assert isinstance(data["actions"], list)


# ---- neo.settings.* ---------------------------------------------------------

def test_settings_get(client):
    r = _rpc(client, "neo.settings.get")
    data = r.json()["result"]
    assert "profile" in data
    assert data["profile"] is not None
    assert isinstance(data["profile"]["preferences"], dict)
    assert isinstance(data["profile"]["tool_paths"], dict)


def test_settings_update(client):
    r = _rpc(client, "neo.settings.update", {"name": "TestUser", "role": "Tester"})
    data = r.json()["result"]
    assert data["updated"] is True

    # Verify the change
    r = _rpc(client, "neo.settings.get")
    profile = r.json()["result"]["profile"]
    assert profile["name"] == "TestUser"


# ---- neo.providers.list ----------------------------------------------------

def test_providers_list(client):
    r = _rpc(client, "neo.providers.list")
    data = r.json()["result"]
    assert "providers" in data
    assert len(data["providers"]) >= 1
    assert data["providers"][0]["tier"] == "CLAUDE"
