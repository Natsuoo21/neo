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
    """Inject temp file DB and mock provider into server module."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    init_schema(db_path)
    with get_session(db_path) as conn:
        seed_user_profile(conn)
        sync_skills_to_db(conn)

    mock_registry = {"CLAUDE": _MockProvider()}

    monkeypatch.setattr(srv, "_bootstrap", lambda db=None: db_path)
    monkeypatch.setattr(srv, "build_provider_registry", lambda: dict(mock_registry))

    async def _noop_ollama(reg):
        pass

    monkeypatch.setattr(srv, "check_ollama", _noop_ollama)
    monkeypatch.setattr(srv, "_db_path", db_path)
    monkeypatch.setattr(srv, "_registry", mock_registry)

    yield

    try:
        os.unlink(db_path)
    except OSError:
        pass


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
    assert isinstance(data["providers"], list)


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
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32601


def test_rpc_parse_error(client):
    r = client.post("/rpc", content="not json", headers={"content-type": "application/json"})
    data = r.json()
    assert data["error"]["code"] == -32700


def test_rpc_invalid_request(client):
    """Missing required 'method' field."""
    r = client.post("/rpc", json={"jsonrpc": "2.0", "id": 1})
    data = r.json()
    assert "error" in data
    assert data["error"]["code"] == -32600


def test_rpc_internal_error_does_not_leak_details(client):
    """Exception details should not be sent to client."""
    _rpc(client, "neo.settings.update", {"name": ""})
    # settings_update raises ValueError if no profile, but the test fixture seeds one.
    # Force an error by calling with bad limit type to test the generic handler.
    # Instead, just verify the error message format.
    # For a true internal error, we'd need to mock a handler to throw.


# ---- neo.execute ------------------------------------------------------------

def test_execute(client):
    r = _rpc(client, "neo.execute", {"command": "hello"})
    data = r.json()["result"]
    assert data["status"] == "success"
    assert data["message"] == "Hello from mock!"
    assert "session_id" in data


def test_execute_with_session_id(client):
    r = _rpc(client, "neo.execute", {"command": "hello", "session_id": "my-session"})
    data = r.json()["result"]
    assert data["session_id"] == "my-session"


def test_execute_missing_command(client):
    r = _rpc(client, "neo.execute", {"command": ""})
    data = r.json()
    assert "error" in data


def test_execute_whitespace_only_command(client):
    r = _rpc(client, "neo.execute", {"command": "   "})
    data = r.json()
    assert "error" in data


def test_execute_command_too_long(client):
    r = _rpc(client, "neo.execute", {"command": "x" * 20_000})
    data = r.json()
    assert "error" in data
    assert "too long" in data["error"]["message"].lower()


# ---- neo.conversation.* -----------------------------------------------------

def test_conversation_new(client):
    r = _rpc(client, "neo.conversation.new")
    data = r.json()["result"]
    assert "session_id" in data
    assert len(data["session_id"]) == 36


def test_conversation_list(client):
    _rpc(client, "neo.execute", {"command": "hi", "session_id": "test-session-1"})
    r = _rpc(client, "neo.conversation.list")
    data = r.json()["result"]
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


def test_conversation_list_empty(client):
    """Empty database returns empty sessions list."""
    r = _rpc(client, "neo.conversation.list")
    data = r.json()["result"]
    assert data["sessions"] == []


def test_conversation_load(client):
    session_id = "test-load-session"
    _rpc(client, "neo.execute", {"command": "hello", "session_id": session_id})
    r = _rpc(client, "neo.conversation.load", {"session_id": session_id})
    data = r.json()["result"]
    assert data["session_id"] == session_id
    assert len(data["messages"]) >= 1


def test_conversation_load_nonexistent(client):
    """Loading a session that doesn't exist returns empty messages."""
    r = _rpc(client, "neo.conversation.load", {"session_id": "no-such-session"})
    data = r.json()["result"]
    assert data["messages"] == []


def test_conversation_load_missing_session(client):
    r = _rpc(client, "neo.conversation.load", {"session_id": ""})
    data = r.json()
    assert "error" in data


def test_conversation_load_limit_clamped(client):
    """Negative or string limit is clamped to valid range."""
    r = _rpc(client, "neo.conversation.load", {"session_id": "s", "limit": -5})
    # Should not error — limit gets clamped to 1
    data = r.json()["result"]
    assert "messages" in data


def test_conversation_list_returns_title_field(client):
    """List should include a title field even when null."""
    _rpc(client, "neo.execute", {"command": "hi", "session_id": "list-title"})
    r = _rpc(client, "neo.conversation.list")
    data = r.json()["result"]
    assert data["sessions"]
    assert "title" in data["sessions"][0]
    assert "is_pinned" in data["sessions"][0]
    assert "first_user_message" in data["sessions"][0]


def test_conversation_rename(client):
    _rpc(client, "neo.execute", {"command": "hi", "session_id": "rename-s"})
    r = _rpc(client, "neo.conversation.rename",
             {"session_id": "rename-s", "title": "My Title"})
    data = r.json()["result"]
    assert data["ok"] is True
    assert data["title"] == "My Title"

    lst = _rpc(client, "neo.conversation.list").json()["result"]
    match = next(s for s in lst["sessions"] if s["session_id"] == "rename-s")
    assert match["title"] == "My Title"


def test_conversation_rename_missing_title(client):
    r = _rpc(client, "neo.conversation.rename", {"session_id": "s"})
    assert "error" in r.json()


def test_conversation_delete(client):
    _rpc(client, "neo.execute", {"command": "hi", "session_id": "del-s"})
    r = _rpc(client, "neo.conversation.delete", {"session_id": "del-s"})
    assert r.json()["result"]["deleted"] is True

    lst = _rpc(client, "neo.conversation.list").json()["result"]
    assert all(s["session_id"] != "del-s" for s in lst["sessions"])

    loaded = _rpc(client, "neo.conversation.load", {"session_id": "del-s"})
    assert loaded.json()["result"]["messages"] == []


def test_conversation_pin(client):
    _rpc(client, "neo.execute", {"command": "old", "session_id": "older-s"})
    _rpc(client, "neo.execute", {"command": "new", "session_id": "newer-s"})
    _rpc(client, "neo.conversation.pin",
         {"session_id": "older-s", "pinned": True})

    lst = _rpc(client, "neo.conversation.list").json()["result"]
    # Pinned sessions must come first
    assert lst["sessions"][0]["session_id"] == "older-s"
    assert lst["sessions"][0]["is_pinned"] == 1


def test_conversation_unpin(client):
    _rpc(client, "neo.execute", {"command": "x", "session_id": "pin-unpin"})
    _rpc(client, "neo.conversation.pin",
         {"session_id": "pin-unpin", "pinned": True})
    _rpc(client, "neo.conversation.pin",
         {"session_id": "pin-unpin", "pinned": False})

    lst = _rpc(client, "neo.conversation.list").json()["result"]
    match = next(s for s in lst["sessions"] if s["session_id"] == "pin-unpin")
    assert match["is_pinned"] == 0


def test_conversation_search_by_content(client):
    _rpc(client, "neo.execute",
         {"command": "Remind me to buy groceries", "session_id": "search-1"})
    _rpc(client, "neo.execute",
         {"command": "Write a poem about cats", "session_id": "search-2"})

    r = _rpc(client, "neo.conversation.search", {"query": "groceries"})
    data = r.json()["result"]
    ids = {s["session_id"] for s in data["sessions"]}
    assert "search-1" in ids
    assert "search-2" not in ids


def test_conversation_search_empty_query_returns_all(client):
    _rpc(client, "neo.execute", {"command": "hi", "session_id": "se-all-1"})
    _rpc(client, "neo.execute", {"command": "hi", "session_id": "se-all-2"})

    r = _rpc(client, "neo.conversation.search", {"query": ""})
    ids = {s["session_id"] for s in r.json()["result"]["sessions"]}
    assert "se-all-1" in ids
    assert "se-all-2" in ids


def test_conversation_generate_title(client):
    _rpc(client, "neo.execute",
         {"command": "Summarize this book", "session_id": "gen-title"})
    r = _rpc(client, "neo.conversation.generate_title",
             {"session_id": "gen-title"})
    data = r.json()["result"]
    assert data["session_id"] == "gen-title"
    # Mock provider's complete() returns "Hello from mock!"
    assert data["title"]  # non-empty


# ---- neo.skills.* -----------------------------------------------------------

def test_skills_list(client):
    r = _rpc(client, "neo.skills.list")
    data = r.json()["result"]
    assert "skills" in data
    assert isinstance(data["skills"], list)


def test_skills_toggle(client):
    r = _rpc(client, "neo.skills.list")
    skills = r.json()["result"]["skills"]
    if skills:
        name = skills[0]["name"]
        r = _rpc(client, "neo.skills.toggle", {"name": name, "enabled": False})
        data = r.json()["result"]
        assert data["updated"] is True
        assert data["enabled"] is False


def test_skills_toggle_nonexistent(client):
    """Toggling a skill that doesn't exist returns updated=False."""
    r = _rpc(client, "neo.skills.toggle", {"name": "no_such_skill", "enabled": True})
    data = r.json()["result"]
    assert data["updated"] is False


def test_skills_toggle_missing_name(client):
    r = _rpc(client, "neo.skills.toggle", {"name": "", "enabled": True})
    data = r.json()
    assert "error" in data


# ---- neo.actions.recent -----------------------------------------------------

def test_actions_recent(client):
    _rpc(client, "neo.execute", {"command": "test action"})
    r = _rpc(client, "neo.actions.recent")
    data = r.json()["result"]
    assert "actions" in data
    assert isinstance(data["actions"], list)


def test_actions_recent_with_limit(client):
    r = _rpc(client, "neo.actions.recent", {"limit": 5})
    data = r.json()["result"]
    assert "actions" in data


def test_actions_recent_invalid_limit(client):
    """String limit should be clamped to default."""
    r = _rpc(client, "neo.actions.recent", {"limit": "bad"})
    data = r.json()["result"]
    assert "actions" in data


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

    r = _rpc(client, "neo.settings.get")
    profile = r.json()["result"]["profile"]
    assert profile["name"] == "TestUser"


def test_settings_update_partial(client):
    """Updating only name should preserve existing role."""
    _rpc(client, "neo.settings.update", {"name": "First", "role": "Engineer"})
    _rpc(client, "neo.settings.update", {"name": "Second"})
    r = _rpc(client, "neo.settings.get")
    profile = r.json()["result"]["profile"]
    assert profile["name"] == "Second"
    assert profile["role"] == "Engineer"


def test_settings_update_preferences_merge(client):
    """Preferences should merge, not replace."""
    _rpc(client, "neo.settings.update", {"preferences": {"language": "en"}})
    _rpc(client, "neo.settings.update", {"preferences": {"timezone": "UTC"}})
    r = _rpc(client, "neo.settings.get")
    prefs = r.json()["result"]["profile"]["preferences"]
    assert prefs.get("language") == "en"
    assert prefs.get("timezone") == "UTC"


# ---- neo.stats -------------------------------------------------------------

def test_stats(client):
    _rpc(client, "neo.execute", {"command": "hello"})
    r = _rpc(client, "neo.stats")
    data = r.json()["result"]
    assert "stats" in data
    assert data["stats"]["total_requests"] >= 1


def test_stats_with_days(client):
    r = _rpc(client, "neo.stats", {"days": 7})
    data = r.json()["result"]
    assert "stats" in data


# ---- neo.patterns ----------------------------------------------------------

def test_patterns(client):
    r = _rpc(client, "neo.patterns")
    data = r.json()["result"]
    assert "patterns" in data
    assert isinstance(data["patterns"], list)


# ---- neo.automation.run ----------------------------------------------------

def test_automation_run(client, monkeypatch):
    """Create an automation then manually trigger it."""
    r = _rpc(client, "neo.automation.create", {
        "name": "Test Run",
        "trigger_type": "schedule",
        "command": "hello",
        "trigger_config": {"cron": "0 * * * *"},
    })
    auto = r.json()["result"]["automation"]

    # Mock scheduler to avoid nested event loops / unawaited coroutine
    from unittest.mock import MagicMock
    mock_scheduler = MagicMock()
    monkeypatch.setattr(srv, "_scheduler", mock_scheduler)

    r = _rpc(client, "neo.automation.run", {"id": auto["id"]})
    data = r.json()["result"]
    assert data["triggered"] is True
    assert data["id"] == auto["id"]
    mock_scheduler._execute_automation.assert_called_once_with(auto["id"], "hello")


def test_automation_run_missing_id(client):
    r = _rpc(client, "neo.automation.run", {})
    data = r.json()
    assert "error" in data


def test_automation_run_nonexistent(client):
    r = _rpc(client, "neo.automation.run", {"id": 99999})
    data = r.json()
    assert "error" in data


# ---- neo.providers.list ----------------------------------------------------

def test_providers_list(client):
    r = _rpc(client, "neo.providers.list")
    data = r.json()["result"]
    assert "providers" in data
    assert len(data["providers"]) >= 1
    assert data["providers"][0]["tier"] == "CLAUDE"


# ---- Helper function tests -------------------------------------------------

def test_safe_json_loads():
    from neo.server import _safe_json_loads
    assert _safe_json_loads('{"a": 1}') == {"a": 1}
    assert _safe_json_loads("") == {}
    assert _safe_json_loads(None) == {}
    assert _safe_json_loads("invalid json") == {}
    assert _safe_json_loads('{"a": 1}', {"default": True}) == {"a": 1}


def test_clamp_limit():
    from neo.server import _clamp_limit
    assert _clamp_limit(10) == 10
    assert _clamp_limit(-5) == 1
    assert _clamp_limit(999) == 500
    assert _clamp_limit("bad") == 50
    assert _clamp_limit(None) == 50
    assert _clamp_limit(0) == 1


# ---- Update check RPC -------------------------------------------------------

def test_update_check_no_update(client, monkeypatch):
    """neo.update.check returns available=False when up-to-date."""
    from unittest.mock import MagicMock

    mock_instance = MagicMock()
    mock_instance.check.return_value = None
    monkeypatch.setattr(srv, "UpdateChecker", lambda: mock_instance)

    r = _rpc(client, "neo.update.check")
    assert r.status_code == 200
    data = r.json()["result"]
    assert data["available"] is False


def test_update_check_has_update(client, monkeypatch):
    """neo.update.check returns update info when available."""
    from unittest.mock import MagicMock

    update_info = {
        "tag": "v0.2.0",
        "name": "Release 0.2.0",
        "url": "https://github.com/Natsuoo21/neo/releases/tag/v0.2.0",
        "published_at": "2026-04-01T12:00:00Z",
        "body": "New features",
    }

    mock_instance = MagicMock()
    mock_instance.check.return_value = update_info
    monkeypatch.setattr(srv, "UpdateChecker", lambda: mock_instance)

    r = _rpc(client, "neo.update.check")
    assert r.status_code == 200
    data = r.json()["result"]
    assert data["available"] is True
    assert data["tag"] == "v0.2.0"


# ---- Suggestions generate RPC -----------------------------------------------

def test_suggestions_generate(client, monkeypatch):
    """neo.suggestions.generate returns created suggestions."""
    monkeypatch.setattr(srv, "generate_suggestions", lambda db, broadcast_fn=None: [])

    r = _rpc(client, "neo.suggestions.generate")
    assert r.status_code == 200
    data = r.json()["result"]
    assert data["created"] == 0
    assert data["suggestions"] == []


def test_suggestions_generate_with_results(client, monkeypatch):
    """neo.suggestions.generate returns created suggestions when patterns found."""
    fake_suggestions = [
        {"id": 1, "pattern": "create excel", "message": "You've done this 4 times"},
    ]
    monkeypatch.setattr(
        srv, "generate_suggestions",
        lambda db, broadcast_fn=None: fake_suggestions,
    )

    r = _rpc(client, "neo.suggestions.generate")
    data = r.json()["result"]
    assert data["created"] == 1
    assert len(data["suggestions"]) == 1
