"""OpenAI Provider — GPT API integration."""

import asyncio
import logging
import os

from openai import APIError, APIStatusError, AsyncOpenAI

from neo.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o"
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds, doubles each retry

# HTTP status codes that are permanent failures — retrying won't help
_NON_RETRYABLE_STATUSES = {400, 401, 403, 404}

# Error strings in 429 responses that indicate permanent quota exhaustion
_QUOTA_EXHAUSTED_MARKERS = ["insufficient_quota", "exceeded your current quota"]


class OpenAIProvider(LLMProvider):
    """OpenAI GPT API provider via openai SDK."""

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model
        self._client: AsyncOpenAI | None = None
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            if not self._api_key:
                raise ValueError("OPENAI_API_KEY not set. Cannot use OpenAI provider.")
            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    @staticmethod
    def _is_quota_exhausted(error: APIError) -> bool:
        """Check if the error indicates permanent quota exhaustion."""
        if not isinstance(error, APIStatusError) or error.status_code != 429:
            return False
        err_str = str(error).lower()
        return any(marker in err_str for marker in _QUOTA_EXHAUSTED_MARKERS)

    async def complete(self, system: str, user: str) -> str:
        """Send a text completion request to OpenAI."""
        client = self._get_client()

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                self._track_usage(response)
                choice = response.choices[0] if response.choices else None
                if not choice or not choice.message.content:
                    return ""
                return choice.message.content
            except APIError as e:
                if isinstance(e, APIStatusError) and e.status_code in _NON_RETRYABLE_STATUSES:
                    logger.error("OpenAI API permanent failure (HTTP %d): %s", e.status_code, e)
                    raise
                if self._is_quota_exhausted(e):
                    logger.error("OpenAI quota exhausted — not retrying: %s", e)
                    raise
                if attempt == _MAX_RETRIES:
                    logger.error("OpenAI API failed after %d attempts: %s", _MAX_RETRIES, e)
                    raise
                delay = _RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "OpenAI API error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt,
                    _MAX_RETRIES,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)

        return ""  # unreachable, satisfies type checker

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict],
        messages: list[dict] | None = None,
    ) -> dict:
        """Send a completion request with tool definitions to OpenAI."""
        client = self._get_client()
        msg_list: list = [{"role": "system", "content": system}]
        if messages:
            msg_list.extend(messages)
        else:
            msg_list.append({"role": "user", "content": user})

        kwargs: dict = {"model": self._model, "messages": msg_list}
        openai_tools = self._convert_tools(tools)
        if openai_tools:
            kwargs["tools"] = openai_tools

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await client.chat.completions.create(**kwargs)
                self._track_usage(response)
                choice = response.choices[0] if response.choices else None
                if not choice:
                    return {"type": "text", "content": ""}
                return self._parse_tool_response(choice)
            except APIError as e:
                if isinstance(e, APIStatusError) and e.status_code in _NON_RETRYABLE_STATUSES:
                    logger.error("OpenAI API permanent failure (HTTP %d): %s", e.status_code, e)
                    raise
                if self._is_quota_exhausted(e):
                    logger.error("OpenAI quota exhausted — not retrying: %s", e)
                    raise
                if attempt == _MAX_RETRIES:
                    logger.error("OpenAI API failed after %d attempts: %s", _MAX_RETRIES, e)
                    raise
                delay = _RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "OpenAI API error (attempt %d/%d), retrying in %.1fs: %s",
                    attempt,
                    _MAX_RETRIES,
                    delay,
                    e,
                )
                await asyncio.sleep(delay)

        return {"type": "text", "content": ""}  # unreachable

    def name(self) -> str:
        return "openai"

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_output_tokens

    def _track_usage(self, response: object) -> None:
        """Track token usage from response."""
        try:
            usage = getattr(response, "usage", None)
            if usage:
                self._total_input_tokens += getattr(usage, "prompt_tokens", 0) or 0
                self._total_output_tokens += getattr(usage, "completion_tokens", 0) or 0
        except Exception:
            pass  # Don't fail on tracking errors

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict] | None:
        """Convert TOOL_DEFINITIONS format to OpenAI function-calling format.

        Input (our format):
            {"name": "...", "description": "...", "input_schema": {...}}

        Output (OpenAI format):
            {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
        """
        if not tools:
            return None
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
    def _parse_tool_response(choice: object) -> dict:
        """Parse OpenAI's choice into our standard format."""
        message = getattr(choice, "message", None)
        if not message:
            return {"type": "text", "content": ""}

        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls and len(tool_calls) > 0:
            call = tool_calls[0]
            import json

            try:
                args = json.loads(call.function.arguments) if call.function.arguments else {}
            except (json.JSONDecodeError, TypeError):
                args = {}

            return {
                "type": "tool_use",
                "content": None,
                "tool_name": call.function.name,
                "tool_input": args,
            }

        return {"type": "text", "content": message.content or ""}
