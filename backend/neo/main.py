"""Neo CLI — Interactive command interface."""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from neo.memory.db import get_session, init_schema
from neo.memory.seed import seed_user_profile
from neo.orchestrator import process
from neo.skills.loader import route_skill_with_name, sync_skills_to_db


def _get_provider():
    """Create the LLM provider based on available API keys."""
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if api_key:
        from neo.llm.claude import ClaudeProvider

        return ClaudeProvider(api_key=api_key)

    # No API key — use a stub that tells the user
    from neo.llm.mock import MockProvider

    print("[!] No CLAUDE_API_KEY set. Running in offline mode (mock responses).")
    print("    Set CLAUDE_API_KEY in .env.development to enable real AI.\n")
    return MockProvider(
        text_response="I'm running in offline mode. Set CLAUDE_API_KEY to enable AI.",
        tool_response={"type": "text", "content": "Offline mode — no tool execution."},
    )


def bootstrap(db_path: str | None = None) -> tuple:
    """Initialize Neo components: load env, init DB, seed data, sync skills.

    Returns:
        (provider, db_path) tuple ready for use.
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

    provider = _get_provider()
    return provider, db_path


async def _async_main() -> None:
    """Async main loop — single event loop for the entire session."""
    provider, db_path = bootstrap()

    print("Neo — Personal Intelligence Agent")
    print(f"    Model: {provider.name()} | DB: {db_path}")
    print("    Type a command or 'quit' to exit.\n")

    while True:
        try:
            command = input("Neo> ").strip()
            if not command:
                continue
            if command.lower() in ("quit", "exit", "q"):
                print("Goodbye.")
                break

            # Route to matching skill, then process through orchestrator
            with get_session(db_path) as conn:
                skill_name, skill_content = route_skill_with_name(command, conn)
                result = await process(command, provider, conn, skill_content, skill_name=skill_name)

            # Display result
            if result["status"] == "success":
                print(f"\n  {result['message']}\n")
                if result["tool_used"]:
                    print(f"  [tool: {result['tool_used']} | {result['duration_ms']}ms]\n")
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
