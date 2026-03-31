"""Tests for the orchestrator — intent parsing, tool dispatch, action logging."""

import os
import tempfile

import pytest

from neo.llm.mock import MockProvider
from neo.llm.provider import LLMProvider
from neo.memory.db import get_connection, init_schema
from neo.memory.models import get_recent_actions, upsert_user_profile
from neo.orchestrator import (
    TOOL_DEFINITIONS,
    TOOL_REGISTRY,
    ToolError,
    build_system_prompt,
    dispatch_tool,
    process,
)


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "test.db")
        init_schema(path)
        yield path


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


# ============================================
# SYSTEM PROMPT BUILDER
# ============================================


class TestSystemPrompt:
    def test_base_prompt_contains_neo_identity(self, conn):
        prompt = build_system_prompt(conn)
        assert "Neo" in prompt
        assert "personal intelligence agent" in prompt

    def test_prompt_includes_user_profile(self, conn):
        upsert_user_profile(
            conn,
            name="Andre",
            role="Developer",
            preferences={"language": "en", "timezone": "America/Sao_Paulo"},
            tool_paths={"default_save_dir": "~/Documents/Neo"},
        )
        conn.commit()
        prompt = build_system_prompt(conn)
        assert "Andre" in prompt
        assert "Developer" in prompt
        assert "America/Sao_Paulo" in prompt
        assert "~/Documents/Neo" in prompt

    def test_prompt_includes_skill_content(self, conn):
        skill = "## Excel Conventions\n- Always bold headers\n- Use SUM() for totals"
        prompt = build_system_prompt(conn, skill_content=skill)
        assert "Skill Instructions" in prompt
        assert "Always bold headers" in prompt

    def test_prompt_without_skill(self, conn):
        prompt = build_system_prompt(conn, skill_content="")
        assert "Skill Instructions" not in prompt

    def test_prompt_with_empty_profile(self, conn):
        # No profile seeded — should still work
        prompt = build_system_prompt(conn)
        assert "Neo" in prompt


# ============================================
# TOOL DEFINITIONS
# ============================================


class TestToolDefinitions:
    def test_all_tools_have_name_and_schema(self):
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["name"] in TOOL_REGISTRY

    def test_registry_covers_all_definitions(self):
        defined_names = {t["name"] for t in TOOL_DEFINITIONS}
        registry_names = set(TOOL_REGISTRY.keys())
        assert defined_names == registry_names


# ============================================
# TOOL DISPATCH
# ============================================


class TestToolDispatch:
    def test_unknown_tool_raises_error(self):
        with pytest.raises(ToolError, match="Unknown tool"):
            dispatch_tool("nonexistent_tool", {})

    def test_dispatch_calls_correct_module(self, tmp_path):
        # Use tmp_path to avoid creating files in user's home
        result = dispatch_tool("create_excel", {"title": str(tmp_path / "Test")})
        assert "Test" in result or ".xlsx" in result


# ============================================
# ORCHESTRATOR PROCESS — FULL LOOP
# ============================================


class TestProcess:
    @pytest.mark.asyncio
    async def test_text_response(self, conn):
        provider = MockProvider(tool_response={"type": "text", "content": "Here's what I think..."})
        result = await process("What is Neo?", provider, conn)
        assert result["status"] == "success"
        assert result["message"] == "Here's what I think..."
        assert result["model_used"] == "mock"
        assert result["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_tool_use_response(self, conn):
        provider = MockProvider(
            tool_response={
                "type": "tool_use",
                "content": None,
                "tool_name": "create_excel",
                "tool_input": {"title": "Weekly Report"},
            }
        )
        result = await process("Create a weekly report spreadsheet", provider, conn)
        assert result["status"] == "success"
        assert result["tool_used"] == "create_excel"

    @pytest.mark.asyncio
    async def test_action_logged_to_db(self, conn):
        provider = MockProvider(tool_response={"type": "text", "content": "Done!"})
        await process("test command", provider, conn)
        actions = get_recent_actions(conn)
        assert len(actions) >= 1
        assert actions[0]["input_text"] == "test command"
        assert actions[0]["model_used"] == "mock"

    @pytest.mark.asyncio
    async def test_error_handled_gracefully(self, conn):
        # Provider that raises
        class FailProvider(LLMProvider):
            async def complete(self, system, user):
                raise RuntimeError("API down")

            async def complete_with_tools(self, system, user, tools):
                raise RuntimeError("API down")

            def name(self):
                return "fail"

        result = await process("do something", FailProvider(), conn)
        assert result["status"] == "error"
        assert result["message"]  # Has an error message

    @pytest.mark.asyncio
    async def test_system_prompt_sent_to_provider(self, conn):
        upsert_user_profile(conn, name="Andre")
        conn.commit()
        provider = MockProvider()
        await process("hello", provider, conn)
        assert "Andre" in provider.last_system
        assert "Neo" in provider.last_system

    @pytest.mark.asyncio
    async def test_skill_content_in_prompt(self, conn):
        provider = MockProvider()
        await process(
            "create a spreadsheet",
            provider,
            conn,
            skill_content="Always use bold headers.",
        )
        assert "Always use bold headers" in provider.last_system

    @pytest.mark.asyncio
    async def test_tools_sent_to_provider(self, conn):
        provider = MockProvider()
        await process("create a note", provider, conn)
        assert len(provider.last_tools) == len(TOOL_DEFINITIONS)


# ============================================
# MOCK PROVIDER
# ============================================


class TestMockProvider:
    @pytest.mark.asyncio
    async def test_mock_returns_text(self):
        p = MockProvider(text_response="Hello!")
        result = await p.complete("sys", "user")
        assert result == "Hello!"
        assert p.call_count == 1

    @pytest.mark.asyncio
    async def test_mock_returns_tool_use(self):
        p = MockProvider(
            tool_response={
                "type": "tool_use",
                "tool_name": "create_note",
                "tool_input": {"title": "Test"},
            }
        )
        result = await p.complete_with_tools("sys", "user", [])
        assert result["type"] == "tool_use"
        assert result["tool_name"] == "create_note"

    @pytest.mark.asyncio
    async def test_mock_tracks_calls(self):
        p = MockProvider()
        await p.complete("s1", "u1")
        await p.complete("s2", "u2")
        assert p.call_count == 2
        assert p.last_user == "u2"
