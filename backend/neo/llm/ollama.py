"""Ollama Provider — Local LLM integration via HTTP API.

Connects to a locally running Ollama instance for cost-free inference.
Falls back gracefully if Ollama is not running.
"""

import logging
import os

import httpx

from neo.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "qwen2.5:3b"
_TIMEOUT = 120.0  # seconds — local models can be slow on first load


class OllamaProvider(LLMProvider):
    """Local LLM provider via Ollama HTTP API."""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self._base_url = (base_url or os.environ.get("OLLAMA_HOST", _DEFAULT_BASE_URL)).rstrip("/")
        self._model = model or os.environ.get("OLLAMA_MODEL", _DEFAULT_MODEL)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a reusable async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._client

    async def complete(self, system: str, user: str) -> str:
        """Send a completion request to Ollama."""
        # Strip images from multimodal user content if present
        user_content = user
        if isinstance(user, list):
            text_parts = []
            for block in user:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            user_content = "\n".join(text_parts)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        client = await self._get_client()
        response = await client.post(
            f"{self._base_url}/api/chat",
            json={"model": self._model, "messages": messages, "stream": False},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")

    @staticmethod
    def _strip_images(messages: list[dict]) -> list[dict]:
        """Strip image blocks from multimodal messages.

        Most local Ollama models lack vision capabilities, so we extract
        only text content from multimodal messages.
        """
        stripped = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                # Extract only text blocks and join them
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                stripped.append({"role": msg["role"], "content": "\n".join(text_parts)})
            else:
                stripped.append(msg)
        return stripped

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict],
        messages: list[dict] | None = None,
    ) -> dict:
        """Send a completion request with tool definitions to Ollama."""
        if messages:
            msg_list = [{"role": "system", "content": system}] + self._strip_images(messages)
        else:
            msg_list = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        ollama_tools = self._format_tools(tools)

        client = await self._get_client()
        payload: dict = {"model": self._model, "messages": msg_list, "stream": False}
        if ollama_tools:
            payload["tools"] = ollama_tools

        response = await client.post(f"{self._base_url}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        return self._parse_tool_response(data)

    def name(self) -> str:
        return "ollama"

    async def is_available(self) -> bool:
        """Check if Ollama is running and reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False
        except Exception:
            return False

    @staticmethod
    def _format_tools(tools: list[dict]) -> list[dict]:
        """Convert TOOL_DEFINITIONS format to Ollama's tool format.

        Input (our format):
            {"name": "...", "description": "...", "input_schema": {...}}

        Output (Ollama format):
            {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            }
            for tool in tools
        ]

    @staticmethod
    def _parse_tool_response(data: dict) -> dict:
        """Parse Ollama's response into our standard format."""
        message = data.get("message", {})
        tool_calls = message.get("tool_calls")

        if tool_calls and len(tool_calls) > 0:
            call = tool_calls[0]
            function = call.get("function", {})
            return {
                "type": "tool_use",
                "content": None,
                "tool_name": function.get("name", ""),
                "tool_input": function.get("arguments", {}),
            }

        return {"type": "text", "content": message.get("content", "")}
