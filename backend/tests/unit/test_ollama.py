"""Tests for OllamaProvider — mocked HTTP calls."""

import httpx
import pytest

from neo.llm.ollama import OllamaProvider

_DUMMY_REQUEST = httpx.Request("POST", "http://localhost:11434/api/chat")
_DUMMY_GET_REQUEST = httpx.Request("GET", "http://localhost:11434/api/tags")


def _ok_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json=data, request=_DUMMY_REQUEST)


@pytest.fixture
def provider():
    return OllamaProvider(base_url="http://localhost:11434", model="llama3.1:8b")


class TestComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_text(self, provider, monkeypatch):
        async def mock_post(self, url, **kwargs):
            return _ok_response({"message": {"role": "assistant", "content": "Hello from Ollama"}})

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        result = await provider.complete("You are helpful.", "Say hello")
        assert result == "Hello from Ollama"

    @pytest.mark.asyncio
    async def test_complete_empty_response(self, provider, monkeypatch):
        async def mock_post(self, url, **kwargs):
            return _ok_response({"message": {"role": "assistant", "content": ""}})

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        result = await provider.complete("sys", "user")
        assert result == ""


class TestCompleteWithTools:
    @pytest.mark.asyncio
    async def test_returns_tool_use(self, provider, monkeypatch):
        async def mock_post(self, url, **kwargs):
            return _ok_response(
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "create_note",
                                    "arguments": {"title": "Test Note"},
                                }
                            }
                        ],
                    }
                }
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        result = await provider.complete_with_tools("sys", "create a note", [])
        assert result["type"] == "tool_use"
        assert result["tool_name"] == "create_note"
        assert result["tool_input"] == {"title": "Test Note"}

    @pytest.mark.asyncio
    async def test_returns_text_when_no_tool_call(self, provider, monkeypatch):
        async def mock_post(self, url, **kwargs):
            return _ok_response({"message": {"role": "assistant", "content": "Just text here"}})

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        result = await provider.complete_with_tools("sys", "what is Neo?", [])
        assert result["type"] == "text"
        assert result["content"] == "Just text here"

    @pytest.mark.asyncio
    async def test_tools_formatted_in_request(self, provider, monkeypatch):
        captured_payload = {}

        async def mock_post(self, url, **kwargs):
            captured_payload.update(kwargs.get("json", {}))
            return _ok_response({"message": {"role": "assistant", "content": "ok"}})

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
        tools = [{"name": "create_note", "description": "Create a note", "input_schema": {"type": "object"}}]
        await provider.complete_with_tools("sys", "test", tools)
        assert len(captured_payload["tools"]) == 1
        assert captured_payload["tools"][0]["type"] == "function"
        assert captured_payload["tools"][0]["function"]["name"] == "create_note"


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_available_when_running(self, provider, monkeypatch):
        async def mock_get(self, url, **kwargs):
            return httpx.Response(200, json={"models": []}, request=_DUMMY_GET_REQUEST)

        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        assert await provider.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_on_connection_error(self, provider, monkeypatch):
        async def mock_get(self, url, **kwargs):
            raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        assert await provider.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_on_timeout(self, provider, monkeypatch):
        async def mock_get(self, url, **kwargs):
            raise httpx.TimeoutException("Timed out")

        monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
        assert await provider.is_available() is False


class TestMeta:
    def test_name_returns_ollama(self, provider):
        assert provider.name() == "ollama"


class TestFormatTools:
    def test_converts_to_ollama_format(self):
        tools = [
            {
                "name": "create_excel",
                "description": "Create a spreadsheet",
                "input_schema": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                },
            }
        ]
        result = OllamaProvider._format_tools(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        fn = result[0]["function"]
        assert fn["name"] == "create_excel"
        assert fn["description"] == "Create a spreadsheet"
        assert fn["parameters"]["type"] == "object"

    def test_empty_tools_list(self):
        assert OllamaProvider._format_tools([]) == []


class TestParseToolResponse:
    def test_parse_tool_call(self):
        data = {
            "message": {
                "tool_calls": [{"function": {"name": "manage_file", "arguments": {"action": "copy", "source": "a"}}}]
            }
        }
        result = OllamaProvider._parse_tool_response(data)
        assert result["type"] == "tool_use"
        assert result["tool_name"] == "manage_file"
        assert result["tool_input"]["action"] == "copy"

    def test_parse_text_response(self):
        data = {"message": {"content": "Here you go"}}
        result = OllamaProvider._parse_tool_response(data)
        assert result["type"] == "text"
        assert result["content"] == "Here you go"
