"""Tests for GeminiProvider — mocked SDK calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neo.llm.gemini import (
    _DAILY_TOKEN_LIMIT,
    GeminiProvider,
    GeminiRateLimitError,
)


@pytest.fixture
def provider():
    return GeminiProvider(api_key="test-key", model="gemini-2.0-flash")


def _mock_text_response(text: str, prompt_tokens: int = 10, candidate_tokens: int = 20):
    """Create a mock Gemini response with text content."""
    part = MagicMock()
    part.function_call = None
    part.text = text

    candidate = MagicMock()
    candidate.content.parts = [part]

    usage = MagicMock()
    usage.prompt_token_count = prompt_tokens
    usage.candidates_token_count = candidate_tokens

    response = MagicMock()
    response.candidates = [candidate]
    response.text = text
    response.usage_metadata = usage
    return response


def _mock_tool_response(tool_name: str, tool_args: dict, prompt_tokens: int = 10, candidate_tokens: int = 20):
    """Create a mock Gemini response with a function call."""
    fc = MagicMock()
    fc.name = tool_name
    fc.args = tool_args

    part = MagicMock()
    part.function_call = fc

    candidate = MagicMock()
    candidate.content.parts = [part]

    usage = MagicMock()
    usage.prompt_token_count = prompt_tokens
    usage.candidates_token_count = candidate_tokens

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = usage
    return response


class TestComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_text(self, provider):
        mock_response = _mock_text_response("Hello from Gemini")
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_model", return_value=mock_model):
            result = await provider.complete("You are helpful.", "Say hello")

        assert result == "Hello from Gemini"

    @pytest.mark.asyncio
    async def test_complete_empty_response(self, provider):
        mock_response = _mock_text_response("")
        mock_response.text = None
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_model", return_value=mock_model):
            result = await provider.complete("sys", "user")

        assert result == ""


class TestCompleteWithTools:
    @pytest.mark.asyncio
    async def test_returns_tool_use(self, provider):
        mock_response = _mock_tool_response("create_note", {"title": "Test"})
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_model", return_value=mock_model):
            result = await provider.complete_with_tools("sys", "create a note", [])

        assert result["type"] == "tool_use"
        assert result["tool_name"] == "create_note"
        assert result["tool_input"] == {"title": "Test"}

    @pytest.mark.asyncio
    async def test_returns_text_when_no_tool_call(self, provider):
        mock_response = _mock_text_response("Just a text answer")
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_model", return_value=mock_model):
            result = await provider.complete_with_tools("sys", "what is Neo?", [])

        assert result["type"] == "text"
        assert result["content"] == "Just a text answer"

    @pytest.mark.asyncio
    async def test_empty_candidates(self, provider):
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.usage_metadata = MagicMock(prompt_token_count=0, candidates_token_count=0)

        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_model", return_value=mock_model):
            result = await provider.complete_with_tools("sys", "test", [])

        assert result["type"] == "text"
        assert result["content"] == ""


class TestDailyTokenTracking:
    @pytest.mark.asyncio
    async def test_tracks_tokens(self, provider):
        mock_response = _mock_text_response("hi", prompt_tokens=100, candidate_tokens=50)
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_model", return_value=mock_model):
            await provider.complete("sys", "user")

        assert provider.daily_tokens_used == 150

    @pytest.mark.asyncio
    async def test_accumulates_across_calls(self, provider):
        mock_response = _mock_text_response("hi", prompt_tokens=100, candidate_tokens=50)
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_model", return_value=mock_model):
            await provider.complete("sys", "call1")
            await provider.complete("sys", "call2")

        assert provider.daily_tokens_used == 300


class TestRateLimit:
    def test_raises_at_limit(self, provider):
        from datetime import datetime, timezone

        provider._daily_tokens_used = _DAILY_TOKEN_LIMIT
        provider._last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # today → no reset

        with pytest.raises(GeminiRateLimitError, match="Daily token limit"):
            provider._check_rate_limit()

    def test_resets_on_new_day(self, provider):
        provider._daily_tokens_used = _DAILY_TOKEN_LIMIT
        provider._last_reset_date = "2020-01-01"  # old date → will reset

        # Should not raise — counter resets
        provider._check_rate_limit()
        assert provider.daily_tokens_used == 0


class TestMeta:
    def test_name_returns_gemini(self, provider):
        assert provider.name() == "gemini"


class TestConvertTools:
    def test_converts_tool_definitions(self):
        tools = [
            {
                "name": "create_excel",
                "description": "Create spreadsheet",
                "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
            }
        ]
        with patch("google.generativeai.protos") as mock_protos:
            mock_protos.FunctionDeclaration = MagicMock()
            mock_protos.Tool = MagicMock()
            result = GeminiProvider._convert_tools(tools)
            assert result is not None
            mock_protos.FunctionDeclaration.assert_called_once()

    def test_empty_tools_returns_none(self):
        assert GeminiProvider._convert_tools([]) is None


class TestParseResponse:
    def test_parse_tool_call(self):
        response = _mock_tool_response("manage_file", {"action": "copy", "source": "a.txt"})
        result = GeminiProvider._parse_response(response)
        assert result["type"] == "tool_use"
        assert result["tool_name"] == "manage_file"
        assert result["tool_input"]["action"] == "copy"

    def test_parse_text(self):
        response = _mock_text_response("Here is the answer")
        # Ensure function_call is falsy for text parts
        response.candidates[0].content.parts[0].function_call = None
        result = GeminiProvider._parse_response(response)
        assert result["type"] == "text"
        assert result["content"] == "Here is the answer"
