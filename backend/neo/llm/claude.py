"""Claude Provider — Anthropic API integration."""

import logging
import os
import time

from anthropic import APIError, AsyncAnthropic

from neo.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds, doubles each retry


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
                return response.content[0].text
            except APIError as e:
                if attempt == _MAX_RETRIES:
                    logger.error("Claude API failed after %d attempts: %s", _MAX_RETRIES, e)
                    raise
                delay = _RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Claude API error (attempt %d/%d), retrying in %.1fs: %s", attempt, _MAX_RETRIES, delay, e
                )
                time.sleep(delay)

        return ""  # unreachable, satisfies type checker

    async def complete_with_tools(self, system: str, user: str, tools: list[dict]) -> dict:
        """Send a completion request with tool definitions to Claude."""
        client = self._get_client()

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    tools=tools,
                )
                self._track_usage(response.usage)
                return self._parse_tool_response(response)
            except APIError as e:
                if attempt == _MAX_RETRIES:
                    logger.error("Claude API failed after %d attempts: %s", _MAX_RETRIES, e)
                    raise
                delay = _RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Claude API error (attempt %d/%d), retrying in %.1fs: %s", attempt, _MAX_RETRIES, delay, e
                )
                time.sleep(delay)

        return {"type": "text", "content": ""}  # unreachable

    def name(self) -> str:
        return "claude"

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_output_tokens

    def _track_usage(self, usage) -> None:
        self._total_input_tokens += usage.input_tokens
        self._total_output_tokens += usage.output_tokens

    @staticmethod
    def _parse_tool_response(response) -> dict:
        """Parse Claude's response into a standardized format."""
        for block in response.content:
            if block.type == "tool_use":
                return {
                    "type": "tool_use",
                    "content": None,
                    "tool_name": block.name,
                    "tool_input": block.input,
                }

        # No tool use — return text
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text
        return {"type": "text", "content": text}
