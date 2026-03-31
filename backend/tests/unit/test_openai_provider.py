"""Tests for OpenAIProvider — mocked SDK calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neo.llm.openai_provider import OpenAIProvider


@pytest.fixture
def provider():
    return OpenAIProvider(api_key="test-key", model="gpt-4o")


def _mock_text_response(text: str, prompt_tokens: int = 10, completion_tokens: int = 20):
    """Create a mock OpenAI response with text content."""
    message = MagicMock()
    message.content = text
    message.tool_calls = None

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


def _mock_tool_response(
    tool_name: str,
    tool_args: dict,
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
):
    """Create a mock OpenAI response with a tool call."""
    import json

    function = MagicMock()
    function.name = tool_name
    function.arguments = json.dumps(tool_args)

    tool_call = MagicMock()
    tool_call.function = function

    message = MagicMock()
    message.content = None
    message.tool_calls = [tool_call]

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


class TestComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_text(self, provider):
        mock_response = _mock_text_response("Hello from GPT")
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.complete("You are helpful.", "Say hello")

        assert result == "Hello from GPT"

    @pytest.mark.asyncio
    async def test_complete_empty_response(self, provider):
        mock_response = _mock_text_response("")
        mock_response.choices[0].message.content = None
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.complete("sys", "user")

        assert result == ""

    @pytest.mark.asyncio
    async def test_complete_no_choices(self, provider):
        mock_response = MagicMock()
        mock_response.choices = []
        mock_response.usage = MagicMock(prompt_tokens=0, completion_tokens=0)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.complete("sys", "user")

        assert result == ""


class TestCompleteWithTools:
    @pytest.mark.asyncio
    async def test_returns_tool_use(self, provider):
        mock_response = _mock_tool_response("create_note", {"title": "Test"})
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.complete_with_tools("sys", "create a note", [])

        assert result["type"] == "tool_use"
        assert result["tool_name"] == "create_note"
        assert result["tool_input"] == {"title": "Test"}

    @pytest.mark.asyncio
    async def test_returns_text_when_no_tool_call(self, provider):
        mock_response = _mock_text_response("Just a text answer")
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.complete_with_tools("sys", "what is Neo?", [])

        assert result["type"] == "text"
        assert result["content"] == "Just a text answer"

    @pytest.mark.asyncio
    async def test_empty_choices(self, provider):
        mock_response = MagicMock()
        mock_response.choices = []
        mock_response.usage = MagicMock(prompt_tokens=0, completion_tokens=0)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            result = await provider.complete_with_tools("sys", "test", [])

        assert result["type"] == "text"
        assert result["content"] == ""

    @pytest.mark.asyncio
    async def test_messages_passed_to_api(self, provider):
        mock_response = _mock_text_response("ok")
        mock_client = MagicMock()
        mock_create = AsyncMock(return_value=mock_response)
        mock_client.chat.completions.create = mock_create

        messages = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "second"},
        ]

        with patch.object(provider, "_get_client", return_value=mock_client):
            await provider.complete_with_tools("sys", "ignored", [], messages=messages)

        call_kwargs = mock_create.call_args
        sent_messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        # System message + 3 history messages
        assert len(sent_messages) == 4
        assert sent_messages[0]["role"] == "system"


class TestTokenTracking:
    @pytest.mark.asyncio
    async def test_tracks_tokens(self, provider):
        mock_response = _mock_text_response("hi", prompt_tokens=100, completion_tokens=50)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            await provider.complete("sys", "user")

        assert provider.total_input_tokens == 100
        assert provider.total_output_tokens == 50

    @pytest.mark.asyncio
    async def test_accumulates_across_calls(self, provider):
        mock_response = _mock_text_response("hi", prompt_tokens=100, completion_tokens=50)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, "_get_client", return_value=mock_client):
            await provider.complete("sys", "call1")
            await provider.complete("sys", "call2")

        assert provider.total_input_tokens == 200
        assert provider.total_output_tokens == 100


class TestMeta:
    def test_name_returns_openai(self, provider):
        assert provider.name() == "openai"


class TestConvertTools:
    def test_converts_tool_definitions(self):
        tools = [
            {
                "name": "create_excel",
                "description": "Create spreadsheet",
                "input_schema": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                },
            }
        ]
        result = OpenAIProvider._convert_tools(tools)
        assert result is not None
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "create_excel"
        assert result[0]["function"]["parameters"]["type"] == "object"

    def test_empty_tools_returns_none(self):
        assert OpenAIProvider._convert_tools([]) is None


class TestParseToolResponse:
    def test_parse_tool_call(self):
        import json

        function = MagicMock()
        function.name = "manage_file"
        function.arguments = json.dumps({"action": "copy", "source": "a.txt"})

        tool_call = MagicMock()
        tool_call.function = function

        message = MagicMock()
        message.content = None
        message.tool_calls = [tool_call]

        choice = MagicMock()
        choice.message = message

        result = OpenAIProvider._parse_tool_response(choice)
        assert result["type"] == "tool_use"
        assert result["tool_name"] == "manage_file"
        assert result["tool_input"]["action"] == "copy"

    def test_parse_text(self):
        message = MagicMock()
        message.content = "Here is the answer"
        message.tool_calls = None

        choice = MagicMock()
        choice.message = message

        result = OpenAIProvider._parse_tool_response(choice)
        assert result["type"] == "text"
        assert result["content"] == "Here is the answer"

    def test_invalid_json_arguments(self):
        function = MagicMock()
        function.name = "create_note"
        function.arguments = "not valid json{"

        tool_call = MagicMock()
        tool_call.function = function

        message = MagicMock()
        message.content = None
        message.tool_calls = [tool_call]

        choice = MagicMock()
        choice.message = message

        result = OpenAIProvider._parse_tool_response(choice)
        assert result["type"] == "tool_use"
        assert result["tool_name"] == "create_note"
        assert result["tool_input"] == {}
