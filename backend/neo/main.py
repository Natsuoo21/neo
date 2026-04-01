"""Neo CLI — Interactive command interface."""

import asyncio
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

from neo.llm.registry import build_provider_registry, check_ollama, select_provider
from neo.memory.db import get_session, init_schema
from neo.memory.models import (
    add_message,
    detect_patterns,
    get_active_projects,
    get_conversation,
    get_recent_actions,
    get_stats,
)
from neo.memory.seed import seed_user_profile
from neo.orchestrator import process
from neo.router import CLAUDE, route, strip_override
from neo.skills.loader import list_skills, route_skill_with_name, sync_skills_to_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI slash commands
# ---------------------------------------------------------------------------

def _cmd_history(db_path: str, session_id: str) -> None:
    """Show conversation history for the current session."""
    with get_session(db_path) as conn:
        messages = get_conversation(conn, session_id, limit=50)
    if not messages:
        print("\n  No messages in current session.\n")
        return
    print(f"\n  Session: {session_id[:8]}... ({len(messages)} messages)\n")
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"][:120] + ("..." if len(msg["content"]) > 120 else "")
        print(f"  [{role}] {content}")
    print()


def _cmd_clear(db_path: str, session_id: str) -> str:
    """Clear current session and start a new one. Returns new session_id."""
    new_id = str(uuid.uuid4())
    print(f"\n  Session cleared. New session: {new_id[:8]}...\n")
    return new_id


def _cmd_stats(db_path: str) -> None:
    """Show telemetry stats."""
    with get_session(db_path) as conn:
        stats = get_stats(conn, days=30)
    total = stats.get("total_requests", 0)
    if total == 0:
        print("\n  No actions recorded yet.\n")
        return

    success = stats.get("success_count", 0)
    errors = stats.get("error_count", 0)
    tokens = stats.get("total_tokens", 0)
    cost = stats.get("total_cost", 0)
    duration = stats.get("total_duration_ms", 0)

    print("\n  === Neo Stats (last 30 days) ===\n")
    print(f"  Requests:  {total} ({success} success, {errors} errors)")
    print(f"  Tokens:    {tokens:,}")
    print(f"  Cost:      R${cost:.2f}")
    print(f"  Duration:  {duration:,}ms total ({duration // max(total, 1)}ms avg)")

    if stats.get("tier_breakdown"):
        print("\n  Routing:")
        for t in stats["tier_breakdown"]:
            print(f"    {t['routed_tier']:10s} {t['count']} requests")

    if stats.get("model_breakdown"):
        print("\n  Models:")
        for m in stats["model_breakdown"]:
            print(f"    {m['model_used']:20s} {m['count']} calls, {m.get('tokens', 0):,} tokens")

    if stats.get("tool_breakdown"):
        print("\n  Tools:")
        for t in stats["tool_breakdown"]:
            print(f"    {t['tool_used']:20s} {t['count']} uses")
    print()


def _cmd_costs(db_path: str) -> None:
    """Show cost breakdown per model."""
    with get_session(db_path) as conn:
        stats = get_stats(conn, days=30)
    models = stats.get("model_breakdown", [])
    if not models:
        print("\n  No cost data recorded yet.\n")
        return
    print("\n  === Cost Breakdown (last 30 days) ===\n")
    print(f"  {'Model':<20s} {'Calls':>6s} {'Tokens':>10s} {'Cost':>10s}")
    print(f"  {'-'*20} {'-'*6} {'-'*10} {'-'*10}")
    for m in models:
        print(f"  {m['model_used']:<20s} {m['count']:>6d} {m.get('tokens', 0):>10,} R${m.get('cost', 0):>8.2f}")
    print(f"\n  Total: R${stats.get('total_cost', 0):.2f}\n")


def _cmd_project(db_path: str) -> None:
    """Show active projects."""
    with get_session(db_path) as conn:
        projects = get_active_projects(conn)
    if not projects:
        print("\n  No active projects.\n")
        return
    print("\n  === Active Projects ===\n")
    for p in projects:
        print(f"  [{p['id']}] {p['name']}: {p.get('description', '')[:80]}")
    print()


def _cmd_skills(db_path: str) -> None:
    """List available skills."""
    with get_session(db_path) as conn:
        skills = list_skills(conn)
    if not skills:
        print("\n  No skills loaded.\n")
        return
    enabled = [s for s in skills if s.get("is_enabled")]
    disabled = [s for s in skills if not s.get("is_enabled")]
    print(f"\n  === Skills ({len(enabled)} enabled, {len(disabled)} disabled) ===\n")
    for s in skills:
        status = "ON " if s.get("is_enabled") else "OFF"
        print(f"  [{status}] {s['name']:<25s} {s.get('skill_type', ''):<8s} {s.get('description', '')[:50]}")
    print()


def _cmd_patterns(db_path: str) -> None:
    """Show detected command patterns."""
    with get_session(db_path) as conn:
        patterns = detect_patterns(conn)
    if not patterns:
        print("\n  No repeated patterns detected yet.\n")
        return
    print("\n  === Detected Patterns (potential automations) ===\n")
    for p in patterns:
        print(f"  \"{p['pattern']}\" — {p['count']} times (last: {p['last_run'][:10]})")
        print(f"    Example: {p['sample_input'][:80]}")
    print()


def _cmd_recent(db_path: str) -> None:
    """Show recent actions."""
    with get_session(db_path) as conn:
        actions = get_recent_actions(conn, limit=10)
    if not actions:
        print("\n  No actions recorded yet.\n")
        return
    print("\n  === Recent Actions ===\n")
    for a in actions:
        status = "OK" if a["status"] == "success" else "ERR"
        tool = a.get("tool_used", "") or "-"
        model = a.get("model_used", "") or "-"
        cmd = a["input_text"][:50] + ("..." if len(a["input_text"]) > 50 else "")
        print(f"  [{status}] {cmd:<55s} {tool:<15s} {model:<10s} {a.get('duration_ms', 0)}ms")
    print()


def _cmd_help() -> None:
    """Show available slash commands."""
    print("\n  === Neo Commands ===\n")
    print("  /history   — Show conversation history for current session")
    print("  /clear     — Clear session and start fresh")
    print("  /stats     — Show telemetry dashboard (requests, costs, models)")
    print("  /costs     — Show cost breakdown per model")
    print("  /project   — Show active projects")
    print("  /skills    — List available skills (enabled/disabled)")
    print("  /patterns  — Show detected command patterns")
    print("  /recent    — Show recent actions")
    print("  /help      — Show this help")
    print("  quit       — Exit Neo\n")


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

    registry = build_provider_registry()
    return registry, db_path


async def _async_main() -> None:
    """Async main loop — single event loop for the entire session."""
    registry, db_path = bootstrap()

    # Check Ollama availability
    await check_ollama(registry)

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
    print("    Type a command, /help for commands, or 'quit' to exit.\n")

    while True:
        try:
            command = input("Neo> ").strip()
            if not command:
                continue
            if command.lower() in ("quit", "exit", "q"):
                print("Goodbye.")
                break

            # Handle slash commands
            if command.startswith("/"):
                cmd = command.lower().split()[0]
                if cmd == "/history":
                    _cmd_history(db_path, session_id)
                elif cmd == "/clear":
                    session_id = _cmd_clear(db_path, session_id)
                elif cmd == "/stats":
                    _cmd_stats(db_path)
                elif cmd == "/costs":
                    _cmd_costs(db_path)
                elif cmd == "/project":
                    _cmd_project(db_path)
                elif cmd == "/skills":
                    _cmd_skills(db_path)
                elif cmd == "/patterns":
                    _cmd_patterns(db_path)
                elif cmd == "/recent":
                    _cmd_recent(db_path)
                elif cmd == "/help":
                    _cmd_help()
                else:
                    print(f"\n  Unknown command: {cmd}. Type /help for available commands.\n")
                continue

            # Route to tier, strip override prefix
            tier = route(command)
            clean_command = strip_override(command)
            provider = select_provider(registry, tier)

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
