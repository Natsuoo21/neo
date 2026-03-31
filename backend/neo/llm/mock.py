"""Mock LLM Provider — Deterministic responses for testing."""

from neo.llm.provider import LLMProvider


class MockProvider(LLMProvider):
    """Returns pre-configured responses. Used in all tests."""

    def __init__(self, text_response: str = "Mock response", tool_response: dict | None = None):
        self._text_response = text_response
        self._tool_response = tool_response or {
            "type": "text",
            "content": "Mock tool response",
        }
        self.last_system: str = ""
        self.last_user: str = ""
        self.last_tools: list[dict] = []
        self.last_messages: list[dict] | None = None
        self.call_count: int = 0

    async def complete(self, system: str, user: str) -> str:
        self.last_system = system
        self.last_user = user
        self.call_count += 1
        return self._text_response

    async def complete_with_tools(
        self,
        system: str,
        user: str,
        tools: list[dict],
        messages: list[dict] | None = None,
    ) -> dict:
        self.last_system = system
        self.last_user = user
        self.last_tools = tools
        self.last_messages = messages
        self.call_count += 1
        return self._tool_response

    def name(self) -> str:
        return "mock"
