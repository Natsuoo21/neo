"""Tests for conversation history and context window management."""

import pytest

from neo.llm.mock import MockProvider
from neo.memory.models import add_message, create_project, get_conversation
from neo.orchestrator import (
    CONTEXT_BUDGETS,
    _estimate_tokens,
    _truncate_history,
    build_system_prompt,
    process,
)


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_short_string(self):
        assert _estimate_tokens("hello") == 1  # 5 chars // 4

    def test_longer_string(self):
        text = "a" * 400
        assert _estimate_tokens(text) == 100


class TestTruncateHistory:
    def test_empty_history(self):
        result = _truncate_history([], max_tokens=1000, reserved_tokens=100)
        assert result == []

    def test_all_fit(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = _truncate_history(messages, max_tokens=1000, reserved_tokens=100)
        assert len(result) == 2

    def test_oldest_dropped(self):
        # Each message is ~250 tokens (1000 chars)
        messages = [
            {"role": "user", "content": "A" * 1000},  # 250 tokens
            {"role": "assistant", "content": "B" * 1000},  # 250 tokens
            {"role": "user", "content": "C" * 1000},  # 250 tokens
        ]
        # Budget: 600 - 100 = 500 tokens → can fit 2 messages
        result = _truncate_history(messages, max_tokens=600, reserved_tokens=100)
        assert len(result) == 2
        # Should keep the two most recent (C and B)
        assert result[0]["content"] == "B" * 1000
        assert result[1]["content"] == "C" * 1000

    def test_zero_budget_keeps_last(self):
        messages = [
            {"role": "user", "content": "hello"},
        ]
        result = _truncate_history(messages, max_tokens=10, reserved_tokens=100)
        # Budget is negative → keep last message only
        assert len(result) == 1

    def test_single_message_fits(self):
        messages = [{"role": "user", "content": "hi"}]
        result = _truncate_history(messages, max_tokens=1000, reserved_tokens=100)
        assert len(result) == 1


class TestContextBudgets:
    def test_budgets_defined(self):
        assert "ollama" in CONTEXT_BUDGETS
        assert "gemini" in CONTEXT_BUDGETS
        assert "claude" in CONTEXT_BUDGETS
        assert "mock" in CONTEXT_BUDGETS

    def test_ollama_smallest(self):
        assert CONTEXT_BUDGETS["ollama"] < CONTEXT_BUDGETS["gemini"]
        assert CONTEXT_BUDGETS["gemini"] < CONTEXT_BUDGETS["claude"]


class TestHistoryInProcess:
    @pytest.mark.asyncio
    async def test_messages_passed_to_provider(self, memory_db):
        provider = MockProvider()
        messages = [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "first reply"},
            {"role": "user", "content": "second message"},
        ]
        await process("second message", provider, memory_db, messages=messages)
        assert provider.last_messages is not None
        assert len(provider.last_messages) == 3

    @pytest.mark.asyncio
    async def test_no_messages_passes_none(self, memory_db):
        provider = MockProvider()
        await process("hello", provider, memory_db)
        assert provider.last_messages is None

    @pytest.mark.asyncio
    async def test_empty_messages_passes_none(self, memory_db):
        provider = MockProvider()
        await process("hello", provider, memory_db, messages=[])
        # Empty list → _truncate_history([]) returns [] → falsy → passed as None
        assert provider.last_messages is None


class TestProjectContextInPrompt:
    def test_project_injected(self, memory_db):
        pid = create_project(
            memory_db,
            name="MIP",
            description="Personal intelligence",
            goals=["MVP by Q2"],
            conventions={"naming": "snake_case"},
        )
        memory_db.commit()
        prompt = build_system_prompt(memory_db, project_id=pid)
        assert "MIP" in prompt
        assert "Personal intelligence" in prompt
        assert "MVP by Q2" in prompt
        assert "snake_case" in prompt

    def test_no_project_no_section(self, memory_db):
        prompt = build_system_prompt(memory_db)
        assert "Active Project" not in prompt

    def test_invalid_project_id_no_crash(self, memory_db):
        prompt = build_system_prompt(memory_db, project_id=9999)
        assert "Active Project" not in prompt


class TestConversationStorage:
    def test_messages_stored_and_retrieved(self, memory_db):
        session = "test-session-123"
        add_message(memory_db, session, "user", "hello")
        add_message(memory_db, session, "assistant", "hi there", model_used="mock")
        memory_db.commit()

        history = get_conversation(memory_db, session)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "hello"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "hi there"
        assert history[1]["model_used"] == "mock"

    def test_separate_sessions_isolated(self, memory_db):
        add_message(memory_db, "session-a", "user", "msg a")
        add_message(memory_db, "session-b", "user", "msg b")
        memory_db.commit()

        history_a = get_conversation(memory_db, "session-a")
        history_b = get_conversation(memory_db, "session-b")
        assert len(history_a) == 1
        assert len(history_b) == 1
        assert history_a[0]["content"] == "msg a"
        assert history_b[0]["content"] == "msg b"

    def test_limit_respected(self, memory_db):
        session = "test-limit"
        for i in range(25):
            add_message(memory_db, session, "user", f"msg {i}")
        memory_db.commit()

        history = get_conversation(memory_db, session, limit=10)
        assert len(history) == 10
