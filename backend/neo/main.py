"""Neo CLI — Interactive command interface."""

import asyncio
import os

from neo.memory.db import get_session, init_schema
from neo.memory.seed import seed_user_profile
from neo.orchestrator import process
from neo.skills.loader import route_skill, sync_skills_to_db


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


def main():
    """Start the Neo interactive CLI."""
    # Load .env.development if it exists
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env.development")
    if os.path.exists(env_path):
        _load_dotenv(env_path)

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
                skill_content = route_skill(command, conn)
                result = asyncio.run(process(command, provider, conn, skill_content))

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


def _load_dotenv(path: str) -> None:
    """Simple .env loader — no dependency on python-dotenv at runtime."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


if __name__ == "__main__":
    main()
