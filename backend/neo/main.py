"""Neo CLI — Interactive command interface."""

import asyncio
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

from neo.memory.db import get_session, init_schema
from neo.memory.models import add_message, get_conversation
from neo.memory.seed import seed_user_profile
from neo.orchestrator import process
from neo.router import CLAUDE, GEMINI, LOCAL, OPENAI, route, strip_override
from neo.skills.loader import route_skill_with_name, sync_skills_to_db

logger = logging.getLogger(__name__)

# Fallback order when the selected tier is unavailable
_FALLBACK_CHAIN = [LOCAL, GEMINI, OPENAI, CLAUDE]


def _build_provider_registry() -> dict:
    """Create a dict mapping tier → provider instance (only if available)."""
    registry: dict = {}

    # Claude (requires API key)
    claude_key = os.environ.get("CLAUDE_API_KEY", "")
    if claude_key:
        from neo.llm.claude import ClaudeProvider

        registry[CLAUDE] = ClaudeProvider(api_key=claude_key)

    # OpenAI (requires API key)
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        from neo.llm.openai_provider import OpenAIProvider

        registry[OPENAI] = OpenAIProvider(api_key=openai_key)

    # Gemini (requires API key)
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        from neo.llm.gemini import GeminiProvider

        registry[GEMINI] = GeminiProvider(api_key=gemini_key)

    # Ollama is checked async — add a placeholder, verify later
    return registry


async def _check_ollama(registry: dict) -> None:
    """Async check if Ollama is running and add to registry."""
    from neo.llm.ollama import OllamaProvider

    ollama = OllamaProvider()
    if await ollama.is_available():
        registry[LOCAL] = ollama


def _select_provider(registry: dict, tier: str):
    """Select provider for the given tier, falling back if unavailable."""
    if tier in registry:
        return registry[tier]

    # Fallback chain
    start = _FALLBACK_CHAIN.index(tier) if tier in _FALLBACK_CHAIN else 0
    for fallback_tier in _FALLBACK_CHAIN[start:]:
        if fallback_tier in registry:
            logger.info("Tier %s unavailable, falling back to %s", tier, fallback_tier)
            return registry[fallback_tier]

    return None


def bootstrap(db_path: str | None = None) -> tuple:
    """Initialize Neo components: load env, init DB, seed data, sync skills.

    Returns:
        (registry, db_path) tuple ready for use.
    """
    # Load .env.development if it exists (relative to backend dir)
    env_path = Path(__file__).resolve().parent.parent / ".env.development"
    load_dotenv(env_path, override=False)

    if db_path is None:
        db_path = os.environ.get("NEO_DB_PATH", "./data/neo.db")

    # Initialize database on first run
    init_schema(db_path)
    with get_session(db_path) as conn:
        created = seed_user_profile(conn)
        if created:
            print("[+] User profile initialized from seed data.")

        # Sync skill files to DB
        skill_count = sync_skills_to_db(conn)
        print(f"[+] {skill_count} skills loaded.\n")

    registry = _build_provider_registry()
    return registry, db_path


async def _async_main() -> None:
    """Async main loop — single event loop for the entire session."""
    registry, db_path = bootstrap()

    # Check Ollama availability
    await _check_ollama(registry)

    if not registry:
        from neo.llm.mock import MockProvider

        print("[!] No providers available. Running in offline mode (mock responses).")
        print("    Set CLAUDE_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY, or install Ollama.\n")
        registry[CLAUDE] = MockProvider(
            text_response="I'm running in offline mode. Set an API key to enable AI.",
            tool_response={"type": "text", "content": "Offline mode — no tool execution."},
        )

    # Generate session ID for conversation history
    session_id = str(uuid.uuid4())

    available = ", ".join(registry.keys())
    print("Neo — Personal Intelligence Agent")
    print(f"    Providers: {available} | DB: {db_path}")
    print("    Type a command or 'quit' to exit.\n")

    while True:
        try:
            command = input("Neo> ").strip()
            if not command:
                continue
            if command.lower() in ("quit", "exit", "q"):
                print("Goodbye.")
                break

            # Route to tier, strip override prefix
            tier = route(command)
            clean_command = strip_override(command)
            provider = _select_provider(registry, tier)

            if provider is None:
                print("\n  [error] No LLM provider available.\n")
                continue

            # Route to matching skill, then process through orchestrator
            with get_session(db_path) as conn:
                skill_name, skill_content = route_skill_with_name(clean_command, conn)

                # Load conversation history
                history = get_conversation(conn, session_id, limit=20)
                messages = [{"role": h["role"], "content": h["content"]} for h in history]
                messages.append({"role": "user", "content": clean_command})

                result = await process(
                    clean_command,
                    provider,
                    conn,
                    skill_content,
                    skill_name=skill_name,
                    routed_tier=tier,
                    messages=messages,
                )

                # Store conversation messages (skip errors to avoid polluting history)
                add_message(conn, session_id, "user", clean_command)
                if result["status"] == "success":
                    add_message(
                        conn,
                        session_id,
                        "assistant",
                        result["message"],
                        model_used=result["model_used"],
                    )

            # Display result
            if result["status"] == "success":
                print(f"\n  {result['message']}\n")
                if result["tool_used"]:
                    tool_info = f"{result['tool_used']} | {tier}→{result['model_used']} | {result['duration_ms']}ms"
                    print(f"  [tool: {tool_info}]\n")
            else:
                print(f"\n  [error] {result['message']}\n")

        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break


def main():
    """Start the Neo interactive CLI."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
