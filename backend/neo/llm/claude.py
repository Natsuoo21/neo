"""Claude Provider — Anthropic API integration."""

import asyncio
import logging
import os

from anthropic import APIError, APIStatusError, AsyncAnthropic
from anthropic.types import Message, Usage

from neo.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds, doubles each retry

# HTTP status codes that are permanent failures — retrying won't help
_NON_RETRYABLE_STATUSES = {400, 401, 403, 404}


class ClaudeProvider(LLMProvider):
    """Claude API provider via Anthropic SDK."""

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("CLAUDE_API_KEY", "")
        self._model = model
        self._client: AsyncAnthropic | None = None
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def _get_client(self) -> AsyncAnthropic:
        if self._client is None:
            if not self._api_key:
                raise ValueError("CLAUDE_API_KEY not set. Cannot use Claude provider.")
            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def complete(self, system: str, user: str) -> str:
        """Send a text completion request to Claude."""
        client = self._get_client()

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                self._track_usage(response.usage)
                if not response.content:
                    return ""
                return response.content[0].text  # type: ignore[union-attr]
            except APIError as e:
                # Don't retry permanent failures (billing, auth, bad request)
                if isinstance(e, APIStatusError) and e.status_code in _NON_RETRYABLE_STATUSES:
                    logger.error("Claude API permanent failure (HTTP %d): %s", e.status_code, e)
                    raise
                if attempt == _MAX_RETRIES:
                    logger.error("Claude API failed after %d attempts: %s", _MAX_RETRIES, e)
                    raise
                delay = _RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Claude API error (attempt %d/%d), retrying in %.1fs: %s", attempt, _MAX_RETRIES, delay, e
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
        """Send a completion request with tool definitions to Claude."""
        client = self._get_client()
        msg_list: list = messages if messages else [{"role": "user", "content": user}]

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    system=system,
                    messages=msg_list,
                    tools=tools,  # type: ignore[arg-type]
                )
                self._track_usage(response.usage)
                if not response.content:
                    return {"type": "text", "content": ""}
                return self._parse_tool_response(response)
            except APIError as e:
                # Don't retry permanent failures (billing, auth, bad request)
                if isinstance(e, APIStatusError) and e.status_code in _NON_RETRYABLE_STATUSES:
                    logger.error("Claude API permanent failure (HTTP %d): %s", e.status_code, e)
                    raise
                if attempt == _MAX_RETRIES:
                    logger.error("Claude API failed after %d attempts: %s", _MAX_RETRIES, e)
                    raise
                delay = _RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Claude API error (attempt %d/%d), retrying in %.1fs: %s", attempt, _MAX_RETRIES, delay, e
                )
                await asyncio.sleep(delay)

        return {"type": "text", "content": ""}  # unreachable

    def name(self) -> str:
        return "claude"

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_output_tokens

    def _track_usage(self, usage: Usage) -> None:
        self._total_input_tokens += usage.input_tokens
        self._total_output_tokens += usage.output_tokens

    @staticmethod
    def _parse_tool_response(response: Message) -> dict:
        """Parse Claude's response into a standardized format."""
        for block in response.content:
            if block.type == "tool_use":
                return {
                    "type": "tool_use",
                    "content": None,
                    "tool_name": block.name,  # type: ignore[union-attr]
                    "tool_input": block.input,  # type: ignore[union-attr]
                }

        # No tool use — return text
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text  # type: ignore[union-attr]
        return {"type": "text", "content": text}
