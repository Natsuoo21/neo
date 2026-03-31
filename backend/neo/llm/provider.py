"""LLM Provider — Abstract interface for all AI model integrations.

Rule: NO business logic here. Only API translation.
Every provider implements the same interface so the orchestrator
can swap models without changing any calling code.
"""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base for all LLM providers (Claude, Gemini, Ollama)."""

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Send a completion request and return the text response."""
        ...

    @abstractmethod
    async def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict],
        messages: list[dict] | None = None,
    ) -> dict:
        """Send a completion request with tool definitions.

        Args:
            system: System prompt.
            user: Current user message (used if messages is None).
            tools: Tool definitions.
            messages: Optional conversation history. If provided, use these
                      instead of building a single-user-message list.
                      Each dict has "role" and "content" keys.

        Returns a dict with:
          - "type": "text" | "tool_use"
          - "content": str (if text) or None
          - "tool_name": str (if tool_use)
          - "tool_input": dict (if tool_use)
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Return the provider name (e.g., 'claude', 'gemini', 'ollama')."""
        ...
