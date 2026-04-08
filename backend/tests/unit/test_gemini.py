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


def _mock_text_response(
    text: str,
    prompt_tokens: int = 10,
    candidate_tokens: int = 20,
    grounding_chunks: list | None = None,
):
    """Create a mock Gemini response with text content."""
    part = MagicMock()
    part.function_call = None
    part.text = text

    candidate = MagicMock()
    candidate.content.parts = [part]
    if grounding_chunks is not None:
        candidate.grounding_metadata.grounding_chunks = grounding_chunks
    else:
        candidate.grounding_metadata = None

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


def _mock_client(response):
    """Create a mock genai.Client with async generate_content."""
    mock = MagicMock()
    mock.aio.models.generate_content = AsyncMock(return_value=response)
    return mock


class TestComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_text(self, provider):
        mock_response = _mock_text_response("Hello from Gemini")
        client = _mock_client(mock_response)

        with patch.object(provider, "_get_client", return_value=client):
            result = await provider.complete("You are helpful.", "Say hello")

        assert result == "Hello from Gemini"

    @pytest.mark.asyncio
    async def test_complete_empty_response(self, provider):
        mock_response = _mock_text_response("")
        mock_response.text = None
        client = _mock_client(mock_response)

        with patch.object(provider, "_get_client", return_value=client):
            result = await provider.complete("sys", "user")

        assert result == ""


class TestCompleteWithTools:
    @pytest.mark.asyncio
    async def test_returns_tool_use(self, provider):
        mock_response = _mock_tool_response("create_note", {"title": "Test"})
        client = _mock_client(mock_response)

        with patch.object(provider, "_get_client", return_value=client):
            result = await provider.complete_with_tools("sys", "create a note", [])

        assert result["type"] == "tool_use"
        assert result["tool_name"] == "create_note"
        assert result["tool_input"] == {"title": "Test"}

    @pytest.mark.asyncio
    async def test_returns_text_when_no_tool_call(self, provider):
        mock_response = _mock_text_response("Just a text answer")
        client = _mock_client(mock_response)

        with patch.object(provider, "_get_client", return_value=client):
            result = await provider.complete_with_tools("sys", "what is Neo?", [])

        assert result["type"] == "text"
        assert result["content"] == "Just a text answer"

    @pytest.mark.asyncio
    async def test_empty_candidates(self, provider):
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_response.usage_metadata = MagicMock(prompt_token_count=0, candidates_token_count=0)
        client = _mock_client(mock_response)

        with patch.object(provider, "_get_client", return_value=client):
            result = await provider.complete_with_tools("sys", "test", [])

        assert result["type"] == "text"
        assert result["content"] == ""


class TestDailyTokenTracking:
    @pytest.mark.asyncio
    async def test_tracks_tokens(self, provider):
        mock_response = _mock_text_response("hi", prompt_tokens=100, candidate_tokens=50)
        client = _mock_client(mock_response)

        with patch.object(provider, "_get_client", return_value=client):
            await provider.complete("sys", "user")

        assert provider.daily_tokens_used == 150

    @pytest.mark.asyncio
    async def test_accumulates_across_calls(self, provider):
        mock_response = _mock_text_response("hi", prompt_tokens=100, candidate_tokens=50)
        client = _mock_client(mock_response)

        with patch.object(provider, "_get_client", return_value=client):
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
        with patch("google.genai.types.Tool") as mock_tool:
            result = GeminiProvider._convert_tools(tools)
            assert result is not None
            mock_tool.assert_called_once()

    def test_empty_tools_returns_none(self):
        assert GeminiProvider._convert_tools([]) is None


class TestParseResponse:
    def test_parse_tool_call(self, provider):
        response = _mock_tool_response("manage_file", {"action": "copy", "source": "a.txt"})
        result = provider._parse_response(response)
        assert result["type"] == "tool_use"
        assert result["tool_name"] == "manage_file"
        assert result["tool_input"]["action"] == "copy"

    def test_parse_text(self, provider):
        response = _mock_text_response("Here is the answer")
        # Ensure function_call is falsy for text parts
        response.candidates[0].content.parts[0].function_call = None
        result = provider._parse_response(response)
        assert result["type"] == "text"
        assert result["content"] == "Here is the answer"

    def test_parse_text_with_grounding_sources(self, provider):
        chunk1 = MagicMock()
        chunk1.web.title = "Example Article"
        chunk1.web.uri = "https://example.com/article"
        chunk2 = MagicMock()
        chunk2.web.title = "Another Source"
        chunk2.web.uri = "https://example.com/source"

        response = _mock_text_response("The answer is 42", grounding_chunks=[chunk1, chunk2])
        response.candidates[0].content.parts[0].function_call = None
        result = provider._parse_response(response)
        assert result["type"] == "text"
        assert "The answer is 42" in result["content"]
        assert "**Sources:**" in result["content"]
        assert "https://example.com/article" in result["content"]
        assert "https://example.com/source" in result["content"]


class TestGroundingSources:
    def test_extract_grounding_sources(self, provider):
        chunk = MagicMock()
        chunk.web.title = "Test Page"
        chunk.web.uri = "https://test.com"

        response = _mock_text_response("text", grounding_chunks=[chunk])
        sources = provider._extract_grounding_sources(response)
        assert "**Sources:**" in sources
        assert "[Test Page](https://test.com)" in sources

    def test_no_grounding_metadata(self, provider):
        response = _mock_text_response("text")
        sources = provider._extract_grounding_sources(response)
        assert sources == ""

    def test_complete_includes_sources(self, provider):
        """complete() should append grounding sources to the text."""
        chunk = MagicMock()
        chunk.web.title = "Wiki"
        chunk.web.uri = "https://wiki.com"
        mock_response = _mock_text_response("Research result", grounding_chunks=[chunk])
        client = _mock_client(mock_response)

        with patch.object(provider, "_get_client", return_value=client):
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                provider.complete("sys", "search something")
            )

        assert "Research result" in result
        assert "**Sources:**" in result
        assert "https://wiki.com" in result
