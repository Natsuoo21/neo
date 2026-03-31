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

from neo.memory.db import get_session, init_schema
from neo.memory.models import (
    add_message,
    get_conversation,
    get_recent_actions,
    get_user_profile,
    upsert_user_profile,
)
from neo.memory.seed import seed_user_profile
from neo.orchestrator import process
from neo.router import CLAUDE, GEMINI, LOCAL, OPENAI, route, strip_override
from neo.skills.loader import list_skills, route_skill_with_name, sync_skills_to_db, toggle_skill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state (populated during lifespan)
# ---------------------------------------------------------------------------
_registry: dict = {}
_db_path: str = ""

# Fallback order when the selected tier is unavailable
_FALLBACK_CHAIN = [LOCAL, GEMINI, OPENAI, CLAUDE]


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
    if await ollama.is_available():
        registry[LOCAL] = ollama


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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: bootstrap DB + providers.  Shutdown: nothing special."""
    global _registry, _db_path
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

    logger.info("Neo server ready. Providers: %s", ", ".join(_registry.keys()))
    yield


app = FastAPI(title="Neo Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "providers": list(_registry.keys())}


@app.get("/stream")
async def stream(request: Request):
    """SSE endpoint — placeholder for future streaming LLM responses."""

    async def event_generator():
        yield {"event": "ping", "data": json.dumps({"status": "connected"})}
        while True:
            if await request.is_disconnected():
                break
            await asyncio.sleep(15)
            yield {"event": "ping", "data": json.dumps({"status": "alive"})}

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
    except Exception as e:
        return JSONResponse(_rpc_error(_INVALID_REQUEST, str(e), body.get("id")))

    handler = _RPC_METHODS.get(req.method)
    if handler is None:
        return JSONResponse(
            _rpc_error(_METHOD_NOT_FOUND, f"Method not found: {req.method}", req.id)
        )

    try:
        result = await handler(req.params or {})
        return JSONResponse(_rpc_ok(result, req.id))
    except TypeError as e:
        return JSONResponse(_rpc_error(_INVALID_PARAMS, str(e), req.id))
    except Exception as e:
        logger.exception("RPC handler error for %s", req.method)
        return JSONResponse(_rpc_error(_INTERNAL_ERROR, str(e), req.id))


# ---------------------------------------------------------------------------
# RPC method implementations
# ---------------------------------------------------------------------------

async def _rpc_health(_params: dict) -> dict:
    return {"status": "ok", "providers": list(_registry.keys())}


async def _rpc_execute(params: dict) -> dict:
    """Execute a command through the orchestrator."""
    command = params.get("command", "").strip()
    if not command:
        raise ValueError("Missing 'command' parameter")

    session_id = params.get("session_id", str(uuid.uuid4()))

    tier = route(command)
    clean_command = strip_override(command)
    provider = _select_provider(_registry, tier)

    if provider is None:
        return {"status": "error", "message": "No LLM provider available."}

    with get_session(_db_path) as conn:
        skill_name, skill_content = route_skill_with_name(clean_command, conn)

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


async def _rpc_conversation_new(_params: dict) -> dict:
    """Create a new conversation session."""
    session_id = str(uuid.uuid4())
    return {"session_id": session_id}


async def _rpc_conversation_list(_params: dict) -> dict:
    """List recent conversation sessions."""
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
        sessions = [dict(r) for r in rows]
    return {"sessions": sessions}


async def _rpc_conversation_load(params: dict) -> dict:
    """Load messages for a conversation session."""
    session_id = params.get("session_id", "")
    if not session_id:
        raise ValueError("Missing 'session_id' parameter")

    limit = params.get("limit", 50)
    with get_session(_db_path) as conn:
        messages = get_conversation(conn, session_id, limit=limit)
    return {"session_id": session_id, "messages": messages}


async def _rpc_skills_list(_params: dict) -> dict:
    """List all skills (enabled and disabled)."""
    with get_session(_db_path) as conn:
        # Get all skills, not just enabled
        rows = conn.execute("SELECT * FROM skills ORDER BY name").fetchall()
        skills = [dict(r) for r in rows]
    return {"skills": skills}


async def _rpc_skills_toggle(params: dict) -> dict:
    """Enable or disable a skill."""
    name = params.get("name", "")
    enabled = params.get("enabled", True)
    if not name:
        raise ValueError("Missing 'name' parameter")

    with get_session(_db_path) as conn:
        updated = toggle_skill(conn, name, enabled)
    return {"updated": updated, "name": name, "enabled": enabled}


async def _rpc_actions_recent(params: dict) -> dict:
    """Get recent action log entries."""
    limit = params.get("limit", 50)
    with get_session(_db_path) as conn:
        actions = get_recent_actions(conn, limit=limit)
    return {"actions": actions}


async def _rpc_settings_get(_params: dict) -> dict:
    """Get user profile and settings."""
    with get_session(_db_path) as conn:
        profile = get_user_profile(conn)
    if profile:
        # Parse JSON fields for the frontend
        profile["preferences"] = json.loads(profile.get("preferences", "{}") or "{}")
        profile["tool_paths"] = json.loads(profile.get("tool_paths", "{}") or "{}")
    return {"profile": profile}


async def _rpc_settings_update(params: dict) -> dict:
    """Update user profile settings."""
    with get_session(_db_path) as conn:
        profile = get_user_profile(conn)
        if not profile:
            raise ValueError("No user profile found")

        name = params.get("name", profile["name"])
        role = params.get("role", profile.get("role", ""))

        existing_prefs = json.loads(profile.get("preferences", "{}") or "{}")
        existing_paths = json.loads(profile.get("tool_paths", "{}") or "{}")

        preferences = {**existing_prefs, **params.get("preferences", {})}
        tool_paths = {**existing_paths, **params.get("tool_paths", {})}

        upsert_user_profile(conn, name, role, preferences, tool_paths)

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
