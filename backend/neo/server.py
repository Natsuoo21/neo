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
from datetime import datetime, timedelta
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
from neo.automations.suggestions import generate_suggestions, get_pending_suggestions
from neo.llm.registry import build_provider_registry, check_ollama, get_fallback_providers, select_provider
from neo.memory.db import get_session, init_schema
from neo.memory.models import (
    accept_suggestion,
    add_message,
    create_automation,
    delete_automation,
    detect_patterns,
    disable_automation,
    dismiss_suggestion,
    enable_automation,
    get_all_automations,
    get_automation,
    get_conversation,
    get_recent_actions,
    get_stats,
    get_user_profile,
    upsert_user_profile,
)
from neo.memory.seed import seed_user_profile
from neo.orchestrator import process, set_mcp_host
from neo.plugins.mcp_host import MCPHost
from neo.router import CLAUDE, GEMINI, LOCAL, OPENAI, route, strip_override
from neo.skills.loader import route_skill_with_name, sync_skills_to_db, toggle_skill
from neo.updater import UpdateChecker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state (populated during lifespan)
# ---------------------------------------------------------------------------
_registry: dict = {}
_db_path: str = ""
_scheduler: Any = None
_file_watcher: Any = None
_mcp_host: MCPHost | None = None
_stt: Any = None
_tts: Any = None

# SSE subscriber queues for broadcasting events to connected clients
_sse_subscribers: list[asyncio.Queue] = []

# Max command length to prevent abuse
_MAX_COMMAND_LENGTH = 10_000

# Module-level update checker instance (populated during lifespan)
_update_checker: UpdateChecker | None = None


class _SharedLoop:
    """A single persistent event loop running in a background thread.

    Async LLM clients (AsyncAnthropic, genai.Client, httpx.AsyncClient) bind
    to the loop where they were created.  If we create + close a loop per
    request, the cached client references a dead loop on the next call
    (→ "Event loop is closed").  This class keeps one loop alive for the
    lifetime of the server.
    """

    def __init__(self) -> None:
        import threading
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def run(self, coro):  # type: ignore[no-untyped-def]
        """Submit a coroutine to the shared loop and block until it completes."""
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


_shared_loop = _SharedLoop()


def _suggestion_job() -> None:
    """Module-level target for APScheduler — generate suggestions."""
    if _db_path:
        generate_suggestions(_db_path, broadcast_fn=broadcast_sse_event)


def _update_check_job() -> None:
    """Module-level target for APScheduler — check for updates."""
    if _update_checker:
        info = _update_checker.check()
        if info:
            broadcast_sse_event({"type": "update_available", **info})

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

    Uses call_soon_threadsafe to safely enqueue from background threads
    (voice transcription, suggestions engine, etc.).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    snapshot = list(_sse_subscribers)
    data_copy = dict(event_data)

    def _enqueue() -> None:
        for q in snapshot:
            try:
                q.put_nowait(data_copy)
            except asyncio.QueueFull:
                logger.warning("SSE subscriber queue full, dropping event")

    if loop is not None and loop.is_running():
        # Already in the event loop thread — safe to call directly
        _enqueue()
    else:
        # Called from a background thread — schedule on the event loop
        try:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(_enqueue)
        except RuntimeError:
            # No event loop at all (e.g. during shutdown) — drop silently
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: bootstrap DB + providers + scheduler + watcher + plugins.  Shutdown: graceful stop."""
    global _registry, _db_path, _scheduler, _file_watcher, _mcp_host
    _db_path = _bootstrap()
    _registry = build_provider_registry()
    await check_ollama(_registry)

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
        _scheduler = NeoScheduler(_db_path, _registry, broadcast_fn=broadcast_sse_event)
        _scheduler.start()
        logger.info("Automation scheduler started")

        # Background job: generate suggestions every 6 hours
        try:
            _scheduler._scheduler.add_job(
                "neo.server:_suggestion_job", "interval", hours=6,
                id="__neo_suggestions", replace_existing=True,
                misfire_grace_time=3600,
            )
            _scheduler._scheduler.add_job(
                "neo.server:_suggestion_job", "date",
                run_date=datetime.now() + timedelta(seconds=30),
                id="__neo_suggestions_initial", replace_existing=True,
            )
            logger.info("Suggestion generation job registered (every 6h)")
        except Exception:
            logger.exception("Failed to register suggestion job")

        # Background job: check for updates weekly
        try:
            _update_checker = UpdateChecker()

            _scheduler._scheduler.add_job(
                "neo.server:_update_check_job", "interval", hours=168,
                id="__neo_update_check", replace_existing=True,
                misfire_grace_time=86400,
            )
            _scheduler._scheduler.add_job(
                "neo.server:_update_check_job", "date",
                run_date=datetime.now() + timedelta(seconds=60),
                id="__neo_update_check_initial", replace_existing=True,
            )
            logger.info("Update checker job registered (weekly)")
        except Exception:
            logger.exception("Failed to register update checker job")

    except (ImportError, OSError, RuntimeError):
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
    except (ImportError, OSError, RuntimeError):
        logger.exception("Failed to start file watcher")

    # Start MCP plugin host
    try:
        _mcp_host = MCPHost()
        _mcp_host.discover()
        set_mcp_host(_mcp_host)
        logger.info("MCP host started, %d plugins discovered", len(_mcp_host.list_plugins()))
    except (ImportError, OSError, RuntimeError):
        logger.exception("Failed to start MCP host")

    logger.info("Neo server ready. Providers: %s", ", ".join(_registry.keys()))
    yield

    # Shutdown
    if _scheduler:
        try:
            _scheduler.shutdown(wait=True)
        except (RuntimeError, OSError):
            logger.exception("Error shutting down scheduler")

    if _file_watcher:
        try:
            _file_watcher.shutdown()
        except (RuntimeError, OSError):
            logger.exception("Error shutting down file watcher")

    if _mcp_host:
        try:
            _mcp_host.shutdown()
            set_mcp_host(None)
        except (RuntimeError, OSError):
            logger.exception("Error shutting down MCP host")

    # I8: Graceful STT/TTS shutdown
    if _stt:
        try:
            _stt.stop_recording()
            _stt.stop_wake_word()
        except Exception:
            logger.exception("Error shutting down STT")

    if _tts:
        try:
            _tts.stop()
        except Exception:
            logger.exception("Error shutting down TTS")


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
    # Read default provider preference from user profile
    default_tier = CLAUDE
    with get_session(db_path) as conn:
        profile = get_user_profile(conn)
        if profile:
            prefs = _safe_json_loads(profile.get("preferences"))
            pref = prefs.get("default_provider", "")
            if pref in (LOCAL, GEMINI, OPENAI, CLAUDE):
                default_tier = pref

    tier = route(command, default_tier=default_tier)
    clean_command = strip_override(command)
    provider = select_provider(registry, tier)

    if provider is None:
        return {
            "status": "error", "message": "No LLM provider available.",
            "tool_used": "", "tool_result": None, "model_used": "",
            "routed_tier": tier, "duration_ms": 0, "session_id": session_id,
        }

    # Run async process() on the shared background loop so that LLM provider
    # clients (AsyncAnthropic, genai.Client, httpx.AsyncClient) stay bound to
    # a single long-lived loop instead of a per-request loop that gets closed.
    with get_session(db_path) as conn:
        skill_name, skill_content = route_skill_with_name(clean_command, conn)

        history = get_conversation(conn, session_id, limit=20)
        messages = [{"role": h["role"], "content": h["content"]} for h in history]
        messages.append({"role": "user", "content": clean_command})

        # Try primary provider, then fallback on runtime errors
        providers_to_try = [(tier, provider)]
        providers_to_try.extend(get_fallback_providers(registry, tier))

        result = None
        for attempt_tier, attempt_provider in providers_to_try:
            result = _shared_loop.run(process(
                clean_command,
                attempt_provider,
                conn,
                skill_content,
                skill_name=skill_name,
                routed_tier=attempt_tier,
                messages=messages,
            ))
            if result["status"] == "success":
                break
            logger.warning(
                "Provider %s failed, trying next fallback...",
                attempt_provider.name(),
            )

        add_message(conn, session_id, "user", clean_command)
        if result["status"] == "success":
            add_message(
                conn,
                session_id,
                "assistant",
                result["message"],
                model_used=result["model_used"],
            )

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


async def _rpc_stats(params: dict) -> dict:
    """Get telemetry stats."""
    days = _clamp_limit(params.get("days", 30), default=30, maximum=365)

    def _query():
        with get_session(_db_path) as conn:
            return get_stats(conn, days=days)

    stats = await asyncio.to_thread(_query)
    return {"stats": stats}


async def _rpc_patterns(params: dict) -> dict:
    """Get detected command patterns."""
    days = _clamp_limit(params.get("days", 14), default=14, maximum=365)

    def _query():
        with get_session(_db_path) as conn:
            return detect_patterns(conn, days=days)

    patterns = await asyncio.to_thread(_query)
    return {"patterns": patterns}


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


async def _rpc_automation_run(params: dict) -> dict:
    """Manually trigger an automation now."""
    automation_id = params.get("id")
    if automation_id is None:
        raise ValueError("Missing 'id' parameter")

    aid = int(automation_id)

    def _get_auto():
        with get_session(_db_path) as conn:
            return get_automation(conn, aid)

    automation = await asyncio.to_thread(_get_auto)
    if not automation:
        raise ValueError(f"Automation not found: {aid}")

    command = automation["command"]

    # Execute via scheduler if available
    if _scheduler:
        _scheduler._execute_automation(aid, command)
        return {"triggered": True, "id": aid}

    # Fallback: execute directly through orchestrator
    result = await asyncio.to_thread(
        _execute_sync, command, str(uuid.uuid4()), _db_path, _registry,
    )
    return {"triggered": True, "id": aid, "result": result}


# ---------------------------------------------------------------------------
# Suggestion RPC methods
# ---------------------------------------------------------------------------


async def _rpc_suggestions_list(_params: dict) -> dict:
    """List active (non-dismissed) suggestions."""
    suggestions = await asyncio.to_thread(get_pending_suggestions, _db_path)
    return {"suggestions": suggestions}


async def _rpc_suggestions_dismiss(params: dict) -> dict:
    """Dismiss a suggestion by ID."""
    suggestion_id = params.get("id")
    if suggestion_id is None:
        raise ValueError("Missing 'id' parameter")

    def _dismiss():
        with get_session(_db_path) as conn:
            return dismiss_suggestion(conn, int(suggestion_id))

    dismissed = await asyncio.to_thread(_dismiss)
    return {"dismissed": dismissed, "id": suggestion_id}


async def _rpc_suggestions_accept(params: dict) -> dict:
    """Accept a suggestion — creates an automation from the pattern."""
    suggestion_id = params.get("id")
    if suggestion_id is None:
        raise ValueError("Missing 'id' parameter")

    def _accept():
        with get_session(_db_path) as conn:
            suggestion = accept_suggestion(conn, int(suggestion_id))
            if not suggestion:
                return None, None

            # Create a pattern-triggered automation from the suggestion
            auto_id = create_automation(
                conn,
                name=f"Auto: {suggestion['pattern']}",
                trigger_type="pattern",
                command=suggestion["sample_input"],
                trigger_config={"pattern": suggestion["pattern"]},
            )
            automation = get_automation(conn, auto_id)
            return suggestion, automation

    suggestion, automation = await asyncio.to_thread(_accept)
    return {
        "accepted": suggestion is not None,
        "suggestion": suggestion,
        "automation": automation,
    }


async def _rpc_suggestions_generate(_params: dict) -> dict:
    """Manually trigger suggestion generation."""
    created = await asyncio.to_thread(
        generate_suggestions, _db_path, broadcast_sse_event,
    )
    return {"created": len(created), "suggestions": created}


# ---------------------------------------------------------------------------
# Update RPC methods
# ---------------------------------------------------------------------------


async def _rpc_update_check(_params: dict) -> dict:
    """Check for new releases on GitHub."""
    checker = UpdateChecker()
    info = await asyncio.to_thread(checker.check)
    if info:
        broadcast_sse_event({"type": "update_available", **info})
        return {"available": True, **info}
    return {"available": False}


# ---------------------------------------------------------------------------
# Plugin RPC methods
# ---------------------------------------------------------------------------


async def _rpc_plugin_list(_params: dict) -> dict:
    """List all discovered plugins and their status."""
    if _mcp_host is None:
        return {"plugins": []}
    plugins = _mcp_host.list_plugins()
    return {"plugins": plugins}


async def _rpc_plugin_install(params: dict) -> dict:
    """Start (install/enable) a plugin by name."""
    name = params.get("name", "").strip()
    if not name:
        raise ValueError("Missing 'name' parameter")
    if _mcp_host is None:
        raise RuntimeError("MCP host not available")

    started = _mcp_host.start_plugin(name)
    return {"started": started, "name": name}


async def _rpc_plugin_stop(params: dict) -> dict:
    """Stop a plugin without unregistering it."""
    name = params.get("name", "").strip()
    if not name:
        raise ValueError("Missing 'name' parameter")
    if _mcp_host is None:
        raise RuntimeError("MCP host not available")

    stopped = _mcp_host.stop_plugin(name)
    return {"stopped": stopped, "name": name}


async def _rpc_plugin_remove(params: dict) -> dict:
    """Stop and unregister a plugin by name."""
    name = params.get("name", "").strip()
    if not name:
        raise ValueError("Missing 'name' parameter")
    if _mcp_host is None:
        raise RuntimeError("MCP host not available")

    removed = _mcp_host.remove_plugin(name)
    return {"removed": removed, "name": name}


async def _rpc_plugin_status(params: dict) -> dict:
    """Get status and tools for a specific plugin."""
    name = params.get("name", "").strip()
    if not name:
        raise ValueError("Missing 'name' parameter")
    if _mcp_host is None:
        return {"name": name, "status": "unavailable", "tools": []}

    plugins = _mcp_host.list_plugins()
    for p in plugins:
        if p["name"] == name:
            tools = _mcp_host.get_plugin_tools(name)
            return {"name": name, "status": p["status"], "tools": tools}

    return {"name": name, "status": "not_found", "tools": []}


# ---------------------------------------------------------------------------
# Voice RPC methods
# ---------------------------------------------------------------------------


async def _rpc_voice_start(params: dict) -> dict:
    """Start voice input (recording from microphone)."""
    global _stt

    model = params.get("model", "base")
    language = params.get("language", "en")

    if _stt is None:
        try:
            from neo.voice.stt import WhisperSTT
            _stt = WhisperSTT(model_name=model, language=language)
        except ImportError as e:
            raise RuntimeError(str(e))
    else:
        # I7: Update config if params changed
        if _stt.model_name != model or _stt.language != language:
            _stt.model_name = model
            _stt.language = language
            _stt._model = None  # Force model reload

    execute = params.get("execute", True)  # Auto-execute transcribed commands

    def _on_transcription(text: str) -> None:
        broadcast_sse_event({"type": "voice_transcription", "text": text})
        if not execute or not text.strip():
            return
        # Execute the transcribed command through the orchestrator
        try:
            session_id = str(uuid.uuid4())
            result = _execute_sync(text, session_id, _db_path, _registry)
            broadcast_sse_event({
                "type": "voice_result",
                "text": text,
                "result": result,
            })
            # Speak the result via TTS if available
            if _tts and result.get("status") == "success" and result.get("message"):
                _tts.speak(result["message"][:500])
        except Exception:
            logger.exception("Voice command execution failed")

    mode = params.get("mode", "record")  # "record" or "wake_word"

    if mode == "wake_word":
        _stt.start_wake_word(_on_transcription)
    else:
        _stt.start_recording(_on_transcription)

    return {"started": True, "mode": mode}


async def _rpc_voice_stop(_params: dict) -> dict:
    """Stop voice input."""
    if _stt is None:
        return {"stopped": False}

    _stt.stop_recording()
    _stt.stop_wake_word()
    return {"stopped": True}


async def _rpc_voice_status(_params: dict) -> dict:
    """Get voice input/output status."""
    stt_status = _stt.get_status() if _stt else {
        "model_loaded": False, "recording": False, "wake_word_active": False,
    }
    tts_status = _tts.get_status() if _tts and hasattr(_tts, "get_status") else {
        "enabled": False, "speaking": False,
    }
    return {
        "stt": stt_status,
        "tts": tts_status,
        "stt_active": stt_status.get("recording", False) or stt_status.get("wake_word_active", False),
        "tts_enabled": tts_status.get("enabled", False),
        "wake_word_active": stt_status.get("wake_word_active", False),
    }


async def _rpc_voice_speak(params: dict) -> dict:
    """Speak text using TTS."""
    global _tts

    text = params.get("text", "").strip()
    if not text:
        raise ValueError("Missing 'text' parameter")

    if _tts is None:
        try:
            from neo.voice.tts import NeoTTS
            _tts = NeoTTS()
        except ImportError as e:
            raise RuntimeError(str(e))

    await asyncio.to_thread(_tts.speak, text)
    return {"spoken": True}


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
    "neo.stats": _rpc_stats,
    "neo.patterns": _rpc_patterns,
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
    "neo.automation.run": _rpc_automation_run,
    "neo.suggestions.list": _rpc_suggestions_list,
    "neo.suggestions.dismiss": _rpc_suggestions_dismiss,
    "neo.suggestions.accept": _rpc_suggestions_accept,
    "neo.suggestions.generate": _rpc_suggestions_generate,
    "neo.update.check": _rpc_update_check,
    "neo.plugin.list": _rpc_plugin_list,
    "neo.plugin.install": _rpc_plugin_install,
    "neo.plugin.stop": _rpc_plugin_stop,
    "neo.plugin.remove": _rpc_plugin_remove,
    "neo.plugin.status": _rpc_plugin_status,
    "neo.voice.start": _rpc_voice_start,
    "neo.voice.stop": _rpc_voice_stop,
    "neo.voice.status": _rpc_voice_status,
    "neo.voice.speak": _rpc_voice_speak,
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
