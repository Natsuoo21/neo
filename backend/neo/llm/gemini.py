"""Gemini Provider — Google AI free-tier integration.

Uses google-generativeai SDK for cost-free inference (up to 1M tokens/day).
Tracks daily usage and enforces rate limits.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import google.generativeai as genai

from neo.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.0-flash"
_DAILY_TOKEN_WARN = 900_000
_DAILY_TOKEN_LIMIT = 950_000


class GeminiRateLimitError(Exception):
    """Raised when daily token limit is reached."""


class GeminiProvider(LLMProvider):
    """Google Gemini API provider via google-generativeai SDK."""

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model_name = model
        self._configured = False
        self._daily_tokens_used = 0
        self._last_reset_date: str = ""

    def _ensure_configured(self) -> None:
        if not self._configured:
            if not self._api_key:
                raise ValueError("GEMINI_API_KEY not set. Cannot use Gemini provider.")
            genai.configure(api_key=self._api_key)
            self._configured = True

    def _get_model(self, system: str = "") -> genai.GenerativeModel:
        self._ensure_configured()
        kwargs: dict = {"model_name": self._model_name}
        if system:
            kwargs["system_instruction"] = system
        return genai.GenerativeModel(**kwargs)

    async def complete(self, system: str, user: str) -> str:
        """Send a completion request to Gemini."""
        self._check_rate_limit()
        model = self._get_model(system)
        response = await model.generate_content_async(user)
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
        model = self._get_model(system)

        gemini_tools = self._convert_tools(tools)
        kwargs: dict = {}
        if gemini_tools:
            kwargs["tools"] = gemini_tools

        # Build content from messages or single user string
        if messages:
            contents = [{"role": m["role"], "parts": [m["content"]]} for m in messages]
        else:
            contents = user  # type: ignore[assignment]

        response = await model.generate_content_async(contents, **kwargs)
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
    def _json_schema_to_proto(schema: dict) -> genai.protos.Schema:
        """Convert a JSON Schema dict to a Gemini protobuf Schema."""
        type_map = {
            "string": genai.protos.Type.STRING,
            "number": genai.protos.Type.NUMBER,
            "integer": genai.protos.Type.INTEGER,
            "boolean": genai.protos.Type.BOOLEAN,
            "array": genai.protos.Type.ARRAY,
            "object": genai.protos.Type.OBJECT,
        }

        kwargs: dict[str, Any] = {}

        json_type = schema.get("type", "object")
        kwargs["type_"] = type_map.get(json_type, genai.protos.Type.OBJECT)

        if "description" in schema:
            kwargs["description"] = schema["description"]

        if "properties" in schema:
            kwargs["properties"] = {
                k: GeminiProvider._json_schema_to_proto(v)
                for k, v in schema["properties"].items()
            }

        if "items" in schema:
            kwargs["items"] = GeminiProvider._json_schema_to_proto(schema["items"])

        if "enum" in schema:
            kwargs["enum"] = schema["enum"]

        if "required" in schema:
            kwargs["required"] = schema["required"]

        return genai.protos.Schema(**kwargs)

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list | None:
        """Convert TOOL_DEFINITIONS format to Gemini FunctionDeclaration format."""
        if not tools:
            return None

        declarations = []
        for tool in tools:
            schema = tool.get("input_schema", {})
            params = GeminiProvider._json_schema_to_proto(schema) if schema else None
            declarations.append(
                genai.protos.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters=params,
                )
            )
        return [genai.protos.Tool(function_declarations=declarations)]

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
