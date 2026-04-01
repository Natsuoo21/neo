"""Neo HTTP Server — JSON-RPC 2.0 over FastAPI.

Provides the IPC layer between the Tauri desktop frontend and the
Python backend.  Communication uses JSON-RPC 2.0 over ``POST /rpc``,
with a ``GET /health`` probe and ``GET /stream`` SSE endpoint reserved
for future streaming responses.

Usage (development)::

    python -m neo.server --port 9721
"""

import argparse
import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from neo.automations.safety import (
    get_pending_confirmations,
    resolve_confirmation,
    set_global_pause,
)
from neo.memory.db import get_session, init_schema
from neo.memory.models import (
    add_message,
    create_automation,
    delete_automation,
    disable_automation,
    enable_automation,
    get_all_automations,
    get_automation,
    get_conversation,
    get_recent_actions,
    get_user_profile,
    upsert_user_profile,
)
from neo.memory.seed import seed_user_profile
from neo.orchestrator import process
from neo.router import CLAUDE, GEMINI, LOCAL, OPENAI, route, strip_override
from neo.skills.loader import route_skill_with_name, sync_skills_to_db, toggle_skill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state (populated during lifespan)
# ---------------------------------------------------------------------------
_registry: dict = {}
_db_path: str = ""
_scheduler: Any = None
_file_watcher: Any = None

# SSE subscriber queues for broadcasting events to connected clients
_sse_subscribers: list[asyncio.Queue] = []

# Fallback order when the selected tier is unavailable
_FALLBACK_CHAIN = [LOCAL, GEMINI, OPENAI, CLAUDE]

# Max command length to prevent abuse
_MAX_COMMAND_LENGTH = 10_000

# Allowed CORS origins (Tauri dev + production)
_CORS_ORIGINS = [
    "http://localhost:1420",
    "https://localhost:1420",
    "http://tauri.localhost",
    "https://tauri.localhost",
]


# ---------------------------------------------------------------------------
# Bootstrap helpers (mirrors main.py logic)
# ---------------------------------------------------------------------------

def _build_provider_registry() -> dict:
    """Create a dict mapping tier -> provider instance (only if available)."""
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


async def _check_ollama(registry: dict) -> None:
    from neo.llm.ollama import OllamaProvider
    ollama = OllamaProvider()
    try:
        async with asyncio.timeout(5):
            if await ollama.is_available():
                registry[LOCAL] = ollama
    except TimeoutError:
        logger.warning("Ollama availability check timed out")


def _select_provider(registry: dict, tier: str):
    if tier in registry:
        return registry[tier]
    start = _FALLBACK_CHAIN.index(tier) if tier in _FALLBACK_CHAIN else 0
    for fallback_tier in _FALLBACK_CHAIN[start:]:
        if fallback_tier in registry:
            return registry[fallback_tier]
    return None


def _bootstrap(db_path: str | None = None) -> str:
    """Load env, init DB, seed data, sync skills. Returns db_path."""
    env_path = Path(__file__).resolve().parent.parent / ".env.development"
    load_dotenv(env_path, override=False)

    if db_path is None:
        db_path = os.environ.get("NEO_DB_PATH", "./data/neo.db")

    init_schema(db_path)
    with get_session(db_path) as conn:
        seed_user_profile(conn)
        sync_skills_to_db(conn)

    return db_path


def _safe_json_loads(raw: Any, fallback: Any = None) -> Any:
    """Parse JSON safely, returning fallback on any error."""
    if fallback is None:
        fallback = {}
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _clamp_limit(value: Any, default: int = 50, maximum: int = 500) -> int:
    """Validate and clamp a limit parameter to a sane range."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, maximum))


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------

class RpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] | None = None
    id: int | str | None = None


def _rpc_ok(result: Any, rpc_id: int | str | None) -> dict:
    return {"jsonrpc": "2.0", "result": result, "id": rpc_id}


def _rpc_error(code: int, message: str, rpc_id: int | str | None, data: Any = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "error": err, "id": rpc_id}


# Standard JSON-RPC error codes
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


# ---------------------------------------------------------------------------
# FastAPI app with lifespan
# ---------------------------------------------------------------------------

def broadcast_sse_event(event_data: dict) -> None:
    """Push an event to all connected SSE subscribers (thread-safe).

    Snapshots the subscriber list and copies the event dict to avoid
    concurrent-modification and shared-mutation issues.
    """
    snapshot = list(_sse_subscribers)
    for queue in snapshot:
        try:
            queue.put_nowait(dict(event_data))
        except asyncio.QueueFull:
            logger.warning("SSE subscriber queue full, dropping event")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: bootstrap DB + providers + scheduler + watcher.  Shutdown: graceful stop."""
    global _registry, _db_path, _scheduler, _file_watcher
    _db_path = _bootstrap()
    _registry = _build_provider_registry()
    await _check_ollama(_registry)

    if not _registry:
        from neo.llm.mock import MockProvider
        logger.warning("No LLM providers available — running in offline/mock mode.")
        _registry[CLAUDE] = MockProvider(
            text_response="I'm running in offline mode. Set an API key to enable AI.",
            tool_response={"type": "text", "content": "Offline mode — no tool execution."},
        )

    # Start scheduler if available
    try:
        from neo.automations.scheduler import NeoScheduler
        _scheduler = NeoScheduler(_db_path, _registry)
        _scheduler.start()
        logger.info("Automation scheduler started")
    except Exception:
        logger.exception("Failed to start scheduler")

    # Start file watcher if available
    try:
        from neo.automations.watcher import NeoFileWatcher

        def _watcher_callback(automation_id: int, command: str) -> None:
            if _scheduler:
                _scheduler._execute_automation(automation_id, command)

        _file_watcher = NeoFileWatcher(_db_path, execute_callback=_watcher_callback)
        _file_watcher.start()
        logger.info("File watcher started")
    except Exception:
        logger.exception("Failed to start file watcher")

    logger.info("Neo server ready. Providers: %s", ", ".join(_registry.keys()))
    yield

    # Shutdown
    if _scheduler:
        try:
            _scheduler.shutdown(wait=True)
        except Exception:
            logger.exception("Error shutting down scheduler")

    if _file_watcher:
        try:
            _file_watcher.shutdown()
        except Exception:
            logger.exception("Error shutting down file watcher")


app = FastAPI(title="Neo Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "providers": list(_registry.keys())}


@app.get("/stream")
async def stream(request: Request):
    """SSE endpoint — broadcasts automation events + keepalive pings."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_subscribers.append(queue)

    async def event_generator():
        try:
            yield {"event": "ping", "data": json.dumps({"status": "connected"})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=15)
                    event_type = event_data.get("type", "message")
                    payload = {k: v for k, v in event_data.items() if k != "type"}
                    yield {"event": event_type, "data": json.dumps(payload)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"status": "alive"})}
        finally:
            if queue in _sse_subscribers:
                _sse_subscribers.remove(queue)

    return EventSourceResponse(event_generator())


@app.post("/rpc")
async def rpc_endpoint(request: Request):
    """JSON-RPC 2.0 dispatcher."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(_PARSE_ERROR, "Parse error", None))

    try:
        req = RpcRequest(**body)
    except Exception:
        return JSONResponse(_rpc_error(_INVALID_REQUEST, "Invalid request", body.get("id")))

    handler = _RPC_METHODS.get(req.method)
    if handler is None:
        return JSONResponse(
            _rpc_error(_METHOD_NOT_FOUND, f"Method not found: {req.method}", req.id)
        )

    try:
        result = await handler(req.params or {})
        return JSONResponse(_rpc_ok(result, req.id))
    except (TypeError, ValueError) as e:
        return JSONResponse(_rpc_error(_INVALID_PARAMS, str(e), req.id))
    except Exception:
        logger.exception("RPC handler error for %s", req.method)
        return JSONResponse(_rpc_error(_INTERNAL_ERROR, "Internal server error", req.id))


# ---------------------------------------------------------------------------
# RPC method implementations
#
# All DB operations use asyncio.to_thread() to avoid blocking the event loop,
# since sqlite3 is synchronous and not thread-safe with async.
# ---------------------------------------------------------------------------

async def _rpc_health(_params: dict) -> dict:
    return {"status": "ok", "providers": list(_registry.keys())}


def _execute_sync(command: str, session_id: str, db_path: str, registry: dict) -> dict:
    """Synchronous execute logic — runs in a thread via asyncio.to_thread()."""
    tier = route(command)
    clean_command = strip_override(command)
    provider = _select_provider(registry, tier)

    if provider is None:
        return {
            "status": "error", "message": "No LLM provider available.",
            "tool_used": "", "tool_result": None, "model_used": "",
            "routed_tier": tier, "duration_ms": 0, "session_id": session_id,
        }

    # We need an event loop for the async process() call inside the thread.
    # Create a new loop since we're in a thread.
    loop = asyncio.new_event_loop()
    try:
        with get_session(db_path) as conn:
            skill_name, skill_content = route_skill_with_name(clean_command, conn)

            history = get_conversation(conn, session_id, limit=20)
            messages = [{"role": h["role"], "content": h["content"]} for h in history]
            messages.append({"role": "user", "content": clean_command})

            result = loop.run_until_complete(process(
                clean_command,
                provider,
                conn,
                skill_content,
                skill_name=skill_name,
                routed_tier=tier,
                messages=messages,
            ))

            add_message(conn, session_id, "user", clean_command)
            if result["status"] == "success":
                add_message(
                    conn,
                    session_id,
                    "assistant",
                    result["message"],
                    model_used=result["model_used"],
                )
    finally:
        loop.close()

    return {
        "status": result["status"],
        "message": result["message"],
        "tool_used": result["tool_used"],
        "tool_result": result["tool_result"],
        "model_used": result["model_used"],
        "routed_tier": result["routed_tier"],
        "duration_ms": result["duration_ms"],
        "session_id": session_id,
    }


async def _rpc_execute(params: dict) -> dict:
    """Execute a command through the orchestrator."""
    command = params.get("command", "").strip()
    if not command:
        raise ValueError("Missing 'command' parameter")
    if len(command) > _MAX_COMMAND_LENGTH:
        raise ValueError(f"Command too long (max {_MAX_COMMAND_LENGTH} chars)")

    session_id = params.get("session_id") or str(uuid.uuid4())

    return await asyncio.to_thread(
        _execute_sync, command, session_id, _db_path, _registry,
    )


async def _rpc_conversation_new(_params: dict) -> dict:
    """Create a new conversation session."""
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}


async def _rpc_conversation_list(_params: dict) -> dict:
    """List recent conversation sessions."""
    def _query():
        with get_session(_db_path) as conn:
            rows = conn.execute(
                """SELECT session_id,
                          MIN(created_at) AS started_at,
                          MAX(created_at) AS last_message_at,
                          COUNT(*) AS message_count
                   FROM conversations
                   GROUP BY session_id
                   ORDER BY MAX(created_at) DESC
                   LIMIT 50"""
            ).fetchall()
            return [dict(r) for r in rows]

    sessions = await asyncio.to_thread(_query)
    return {"sessions": sessions}


async def _rpc_conversation_load(params: dict) -> dict:
    """Load messages for a conversation session."""
    session_id = params.get("session_id", "")
    if not session_id:
        raise ValueError("Missing 'session_id' parameter")

    limit = _clamp_limit(params.get("limit", 50))

    def _query():
        with get_session(_db_path) as conn:
            return get_conversation(conn, session_id, limit=limit)

    messages = await asyncio.to_thread(_query)
    return {"session_id": session_id, "messages": messages}


async def _rpc_skills_list(_params: dict) -> dict:
    """List all skills (enabled and disabled)."""
    def _query():
        with get_session(_db_path) as conn:
            rows = conn.execute("SELECT * FROM skills ORDER BY name").fetchall()
            return [dict(r) for r in rows]

    skills = await asyncio.to_thread(_query)
    return {"skills": skills}


async def _rpc_skills_toggle(params: dict) -> dict:
    """Enable or disable a skill."""
    name = params.get("name", "")
    enabled = params.get("enabled", True)
    if not name:
        raise ValueError("Missing 'name' parameter")

    def _update():
        with get_session(_db_path) as conn:
            return toggle_skill(conn, name, enabled)

    updated = await asyncio.to_thread(_update)
    return {"updated": updated, "name": name, "enabled": enabled}


async def _rpc_actions_recent(params: dict) -> dict:
    """Get recent action log entries."""
    limit = _clamp_limit(params.get("limit", 50))

    def _query():
        with get_session(_db_path) as conn:
            return get_recent_actions(conn, limit=limit)

    actions = await asyncio.to_thread(_query)
    return {"actions": actions}


async def _rpc_settings_get(_params: dict) -> dict:
    """Get user profile and settings."""
    def _query():
        with get_session(_db_path) as conn:
            return get_user_profile(conn)

    profile = await asyncio.to_thread(_query)
    if profile:
        profile["preferences"] = _safe_json_loads(profile.get("preferences"))
        profile["tool_paths"] = _safe_json_loads(profile.get("tool_paths"))
    return {"profile": profile}


async def _rpc_settings_update(params: dict) -> dict:
    """Update user profile settings."""
    def _update():
        with get_session(_db_path) as conn:
            profile = get_user_profile(conn)
            if not profile:
                raise ValueError("No user profile found")

            name = params.get("name", profile["name"])
            role = params.get("role", profile.get("role", ""))

            existing_prefs = _safe_json_loads(profile.get("preferences"))
            existing_paths = _safe_json_loads(profile.get("tool_paths"))

            preferences = {**existing_prefs, **params.get("preferences", {})}
            tool_paths = {**existing_paths, **params.get("tool_paths", {})}

            upsert_user_profile(conn, name, role, preferences, tool_paths)

    await asyncio.to_thread(_update)
    return {"updated": True}


async def _rpc_providers_list(_params: dict) -> dict:
    """List available LLM providers."""
    providers = []
    for tier, provider in _registry.items():
        providers.append({
            "tier": tier,
            "name": provider.name(),
        })
    return {"providers": providers}


# ---------------------------------------------------------------------------
# Automation RPC methods
# ---------------------------------------------------------------------------


async def _rpc_automation_list(_params: dict) -> dict:
    """List all automations."""
    def _query():
        with get_session(_db_path) as conn:
            return get_all_automations(conn)

    automations = await asyncio.to_thread(_query)
    return {"automations": automations}


async def _rpc_automation_create(params: dict) -> dict:
    """Create a new automation."""
    name = params.get("name", "").strip()
    trigger_type = params.get("trigger_type", "").strip()
    command = params.get("command", "").strip()
    trigger_config = params.get("trigger_config", {})

    if not name:
        raise ValueError("Missing 'name' parameter")
    if trigger_type not in ("schedule", "file_event", "startup", "pattern"):
        raise ValueError(f"Invalid trigger_type: {trigger_type}")
    if not command:
        raise ValueError("Missing 'command' parameter")

    def _create():
        with get_session(_db_path) as conn:
            auto_id = create_automation(conn, name, trigger_type, command, trigger_config)
            return get_automation(conn, auto_id)

    automation = await asyncio.to_thread(_create)

    # Register with scheduler/watcher if applicable
    if _scheduler and trigger_type == "schedule" and automation:
        cron_expr = trigger_config.get("cron", "")
        if cron_expr:
            _scheduler.add_automation(automation["id"], name, cron_expr, command)

    if _file_watcher and trigger_type == "file_event" and automation:
        path = trigger_config.get("path", "")
        pattern = trigger_config.get("pattern", "*")
        event_types = trigger_config.get("event_types", ["created", "modified"])
        if path:
            _file_watcher.add_watcher(automation["id"], path, pattern, event_types)

    return {"automation": automation}


async def _rpc_automation_toggle(params: dict) -> dict:
    """Enable or disable an automation."""
    automation_id = params.get("id")
    enabled = params.get("enabled", True)
    if automation_id is None:
        raise ValueError("Missing 'id' parameter")

    def _toggle():
        with get_session(_db_path) as conn:
            if enabled:
                enable_automation(conn, int(automation_id))
            else:
                disable_automation(conn, int(automation_id))
            return get_automation(conn, int(automation_id))

    automation = await asyncio.to_thread(_toggle)

    # Update scheduler/watcher
    aid = int(automation_id)
    if automation:
        trigger_type = automation.get("trigger_type", "")
        if _scheduler and trigger_type == "schedule":
            if enabled:
                config = _safe_json_loads(automation.get("trigger_config"))
                cron_expr = config.get("cron", "")
                if cron_expr:
                    _scheduler.add_automation(aid, automation["name"], cron_expr, automation["command"])
            else:
                _scheduler.remove_automation(aid)

        if _file_watcher and trigger_type == "file_event":
            if enabled:
                config = _safe_json_loads(automation.get("trigger_config"))
                path = config.get("path", "")
                pattern = config.get("pattern", "*")
                event_types = config.get("event_types", ["created", "modified"])
                if path:
                    _file_watcher.add_watcher(aid, path, pattern, event_types)
            else:
                _file_watcher.remove_watcher(aid)

    return {"updated": True, "id": automation_id, "enabled": enabled}


async def _rpc_automation_delete(params: dict) -> dict:
    """Delete an automation."""
    automation_id = params.get("id")
    if automation_id is None:
        raise ValueError("Missing 'id' parameter")

    aid = int(automation_id)

    # Remove from scheduler/watcher first
    if _scheduler:
        _scheduler.remove_automation(aid)
    if _file_watcher:
        _file_watcher.remove_watcher(aid)

    def _delete():
        with get_session(_db_path) as conn:
            return delete_automation(conn, aid)

    deleted = await asyncio.to_thread(_delete)
    return {"deleted": deleted, "id": automation_id}


async def _rpc_automation_confirm(params: dict) -> dict:
    """Resolve a pending confirmation."""
    confirmation_id = params.get("confirmation_id", "")
    approved = params.get("approved", False)
    if not confirmation_id:
        raise ValueError("Missing 'confirmation_id' parameter")

    resolved = resolve_confirmation(confirmation_id, approved)
    return {"resolved": resolved, "confirmation_id": confirmation_id}


async def _rpc_automation_pause_all(_params: dict) -> dict:
    """Pause all automations globally."""
    set_global_pause(True)
    broadcast_sse_event({"type": "automation_status", "paused": True})
    return {"paused": True}


async def _rpc_automation_resume_all(_params: dict) -> dict:
    """Resume all automations globally."""
    set_global_pause(False)
    broadcast_sse_event({"type": "automation_status", "paused": False})
    return {"paused": False}


async def _rpc_automation_pending_confirmations(_params: dict) -> dict:
    """Get pending confirmations."""
    return {"confirmations": get_pending_confirmations()}


# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------

_RPC_METHODS: dict[str, Any] = {
    "neo.health": _rpc_health,
    "neo.execute": _rpc_execute,
    "neo.conversation.new": _rpc_conversation_new,
    "neo.conversation.list": _rpc_conversation_list,
    "neo.conversation.load": _rpc_conversation_load,
    "neo.skills.list": _rpc_skills_list,
    "neo.skills.toggle": _rpc_skills_toggle,
    "neo.actions.recent": _rpc_actions_recent,
    "neo.settings.get": _rpc_settings_get,
    "neo.settings.update": _rpc_settings_update,
    "neo.providers.list": _rpc_providers_list,
    "neo.automation.list": _rpc_automation_list,
    "neo.automation.create": _rpc_automation_create,
    "neo.automation.toggle": _rpc_automation_toggle,
    "neo.automation.delete": _rpc_automation_delete,
    "neo.automation.confirm": _rpc_automation_confirm,
    "neo.automation.pause_all": _rpc_automation_pause_all,
    "neo.automation.resume_all": _rpc_automation_resume_all,
    "neo.automation.pending_confirmations": _rpc_automation_pending_confirmations,
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(description="Neo HTTP Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9721, help="Port (default: 9721)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes")
    return parser.parse_args()


def main():
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        "neo.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
