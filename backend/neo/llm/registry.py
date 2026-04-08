"""LLM provider registry — shared bootstrap logic.

Consolidates provider creation and fallback chain used by
main.py, server.py, and scheduler.py.
"""

import asyncio
import logging
import os
from typing import Any

from neo.router import CLAUDE, GEMINI, LOCAL, OPENAI

logger = logging.getLogger(__name__)

# Fallback order when the selected tier is unavailable
FALLBACK_CHAIN = [LOCAL, GEMINI, OPENAI, CLAUDE]


def build_provider_registry() -> dict:
    """Create a dict mapping tier -> provider instance (only if API key is set)."""
    registry: dict = {}

    claude_key = os.environ.get("CLAUDE_API_KEY", "")
    if claude_key:
        from neo.llm.claude import ClaudeProvider

        registry[CLAUDE] = ClaudeProvider(api_key=claude_key)

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        from neo.llm.openai_provider import OpenAIProvider

        registry[OPENAI] = OpenAIProvider(api_key=openai_key)

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        from neo.llm.gemini import GeminiProvider

        registry[GEMINI] = GeminiProvider(api_key=gemini_key)

    return registry


async def check_ollama(registry: dict) -> None:
    """Async check if Ollama is running and add to registry."""
    from neo.llm.ollama import OllamaProvider

    ollama = OllamaProvider()
    try:
        async with asyncio.timeout(5):
            if await ollama.is_available():
                registry[LOCAL] = ollama
    except TimeoutError:
        logger.warning("Ollama availability check timed out")


def select_provider(registry: dict, tier: str) -> Any:
    """Select provider for the given tier, falling back if unavailable.

    Wraps around the fallback chain so every provider gets a chance.
    E.g. if CLAUDE is requested but unavailable, tries LOCAL → GEMINI → OPENAI.
    """
    if tier in registry:
        return registry[tier]

    if tier in FALLBACK_CHAIN:
        start = FALLBACK_CHAIN.index(tier) + 1
    else:
        start = 0
    # Wrap around: try providers after the requested tier, then those before it
    ordered = FALLBACK_CHAIN[start:] + FALLBACK_CHAIN[:start]
    for fallback_tier in ordered:
        if fallback_tier in registry and fallback_tier != tier:
            logger.info("Tier %s unavailable, falling back to %s", tier, fallback_tier)
            return registry[fallback_tier]

    return None


def get_fallback_providers(registry: dict, failed_tier: str) -> list[tuple[str, Any]]:
    """Get remaining providers after a runtime failure, in fallback order.

    Returns list of (tier, provider) tuples excluding the failed tier.
    Wraps around the chain so every other provider gets a chance.
    """
    if failed_tier in FALLBACK_CHAIN:
        start = FALLBACK_CHAIN.index(failed_tier) + 1
    else:
        start = 0
    # Wrap around: try providers after failed_tier, then those before it
    ordered = FALLBACK_CHAIN[start:] + FALLBACK_CHAIN[:start]
    result = []
    for tier in ordered:
        if tier in registry and tier != failed_tier:
            result.append((tier, registry[tier]))
    return result
