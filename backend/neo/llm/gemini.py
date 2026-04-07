"""Gemini Provider — Google AI free-tier integration.

Uses google-genai SDK for cost-free inference (up to 1M tokens/day).
Tracks daily usage and enforces rate limits.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from google import genai
from google.genai import types

from neo.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.0-flash"
_DAILY_TOKEN_WARN = 900_000
_DAILY_TOKEN_LIMIT = 950_000


class GeminiRateLimitError(Exception):
    """Raised when daily token limit is reached."""


class GeminiProvider(LLMProvider):
    """Google Gemini API provider via google-genai SDK."""

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model_name = model
        self._client: genai.Client | None = None
        self._daily_tokens_used = 0
        self._last_reset_date: str = ""

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if not self._api_key:
                raise ValueError("GEMINI_API_KEY not set. Cannot use Gemini provider.")
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def complete(self, system: str, user: str) -> str:
        """Send a completion request to Gemini."""
        self._check_rate_limit()
        client = self._get_client()
        config = types.GenerateContentConfig(system_instruction=system) if system else None
        response = await client.aio.models.generate_content(
            model=self._model_name,
            contents=user,
            config=config,
        )
        self._track_usage(response)
        try:
            if not response.text:
                return ""
            return response.text
        except ValueError:
            # Safety filter blocked the response — response.text raises ValueError
            logger.warning("Gemini response blocked by safety filter")
            return ""

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict],
        messages: list[dict] | None = None,
    ) -> dict:
        """Send a completion request with tool definitions to Gemini."""
        self._check_rate_limit()
        client = self._get_client()

        gemini_tools = self._convert_tools(tools)
        config_kwargs: dict[str, Any] = {}
        if system:
            config_kwargs["system_instruction"] = system
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools
            # Nudge Gemini to prefer tool calls over text responses
            config_kwargs["tool_config"] = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            )

        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        # Build content from messages or single user string
        if messages:
            contents = [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages]
        else:
            contents = user  # type: ignore[assignment]

        response = await client.aio.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=config,
        )
        self._track_usage(response)
        return self._parse_response(response)

    def name(self) -> str:
        return "gemini"

    @property
    def daily_tokens_used(self) -> int:
        return self._daily_tokens_used

    def _check_rate_limit(self) -> None:
        """Reset counter at midnight UTC; raise if over limit."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._daily_tokens_used = 0
            self._last_reset_date = today

        if self._daily_tokens_used >= _DAILY_TOKEN_LIMIT:
            raise GeminiRateLimitError(
                f"Daily token limit reached ({self._daily_tokens_used}/{_DAILY_TOKEN_LIMIT}). "
                "Try again tomorrow or use a different provider."
            )

    def _track_usage(self, response: Any) -> None:
        """Track token usage from response metadata."""
        try:
            usage = response.usage_metadata
            if usage:
                tokens = (usage.prompt_token_count or 0) + (usage.candidates_token_count or 0)
                self._daily_tokens_used += tokens
                if self._daily_tokens_used >= _DAILY_TOKEN_WARN:
                    logger.warning("Gemini daily usage high: %d/%d tokens", self._daily_tokens_used, _DAILY_TOKEN_LIMIT)
        except (AttributeError, TypeError):
            logger.debug("Could not track Gemini token usage from response")

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list | None:
        """Convert TOOL_DEFINITIONS format to Gemini Tool format."""
        if not tools:
            return None

        declarations = []
        for tool in tools:
            schema = tool.get("input_schema", {})
            decl: dict[str, Any] = {
                "name": tool["name"],
                "description": tool.get("description", ""),
            }
            if schema:
                decl["parameters"] = schema
            declarations.append(decl)
        return [types.Tool(function_declarations=declarations)]

    @staticmethod
    def _parse_response(response: Any) -> dict:
        """Parse Gemini's response into our standard format."""
        if not response.candidates:
            return {"type": "text", "content": ""}

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            return {"type": "text", "content": ""}

        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                return {
                    "type": "tool_use",
                    "content": None,
                    "tool_name": part.function_call.name,
                    "tool_input": dict(part.function_call.args) if part.function_call.args else {},
                }

        # Text-only response
        text = "".join(part.text for part in candidate.content.parts if hasattr(part, "text") and part.text)
        return {"type": "text", "content": text}
