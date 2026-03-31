"""Neo Orchestrator — Central nervous system.

Receives a command string, parses intent, selects skill,
routes to LLM, executes tool, logs action.

6-stage lifecycle: RECEIVE → PARSE → ROUTE → SKILL → EXECUTE → CONFIRM
"""

import importlib
import json
import logging
import sqlite3
import time
from typing import TypedDict

from neo.llm.provider import LLMProvider
from neo.memory.models import get_project, get_user_profile, log_action

logger = logging.getLogger(__name__)


class ProcessResult(TypedDict):
    """Typed result from the orchestrator's process() function."""

    status: str
    message: str
    tool_used: str
    tool_result: str | None
    model_used: str
    routed_tier: str
    duration_ms: int


class ToolError(Exception):
    """Raised when a tool dispatch fails."""


# Tool definitions exposed to the LLM for tool-use calls
TOOL_DEFINITIONS = [
    {
        "name": "create_excel",
        "description": "Create an Excel spreadsheet (.xlsx) with specified structure and formatting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The spreadsheet title / filename"},
                "sheets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "array"}},
                        },
                        "required": ["name"],
                    },
                    "description": "List of sheets to create",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "create_presentation",
        "description": "Create a PowerPoint presentation (.pptx) with slides.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Presentation title / filename"},
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["title"],
                    },
                    "description": "List of slides",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "create_document",
        "description": "Create a Word document (.docx) with content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title / filename"},
                "content": {"type": "string", "description": "Document body text (supports markdown-style headings)"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "create_note",
        "description": "Create an Obsidian note (.md) with frontmatter and content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Note title"},
                "content": {"type": "string", "description": "Note body in markdown"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for the note"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "manage_file",
        "description": "Move, rename, copy, or delete a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["move", "rename", "copy", "delete"],
                    "description": "The file operation to perform",
                },
                "source": {"type": "string", "description": "Source file path"},
                "destination": {"type": "string", "description": "Destination path (not needed for delete)"},
            },
            "required": ["action", "source"],
        },
    },
]

# Maps LLM tool names to (module_name, function_name)
TOOL_REGISTRY: dict[str, tuple[str, str]] = {
    "create_excel": ("neo.tools.excel", "create_workbook"),
    "create_presentation": ("neo.tools.powerpoint", "create_presentation"),
    "create_document": ("neo.tools.word", "create_document"),
    "create_note": ("neo.tools.obsidian", "create_note"),
    "manage_file": ("neo.tools.files", "manage_file"),
}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def _truncate_history(
    messages: list[dict],
    max_tokens: int,
    reserved_tokens: int,
) -> list[dict]:
    """Drop oldest messages to fit within budget.

    Always keeps the last message (current user command).
    """
    budget = max_tokens - reserved_tokens
    if budget <= 0:
        return messages[-1:] if messages else []

    result: list[dict] = []
    total = 0
    for msg in reversed(messages):
        msg_tokens = _estimate_tokens(msg.get("content", ""))
        if total + msg_tokens > budget:
            break
        result.append(msg)
        total += msg_tokens

    return list(reversed(result))


# Default context budgets per model tier (in estimated tokens)
CONTEXT_BUDGETS: dict[str, int] = {
    "ollama": 4_000,
    "gemini": 30_000,
    "claude": 100_000,
    "mock": 100_000,
}


def build_system_prompt(
    conn: sqlite3.Connection,
    skill_content: str = "",
    project_id: int | None = None,
) -> str:
    """Assemble the system prompt from user profile + skill + project.

    Components:
    1. Base Neo instructions
    2. User profile (name, role, preferences, tool paths)
    3. Active project context (if provided)
    4. Skill instructions (if a matching skill was found)
    """
    parts = [
        "You are Neo, a personal intelligence agent. "
        "You execute real actions on the user's computer — creating files, "
        "managing documents, and automating tasks. You are NOT a chatbot. "
        "When the user asks you to create something, use the appropriate tool. "
        "Always confirm what you did after executing.",
    ]

    # Inject user profile
    profile = get_user_profile(conn)
    if profile:
        prefs = json.loads(profile.get("preferences", "{}") or "{}")
        tools = json.loads(profile.get("tool_paths", "{}") or "{}")
        parts.append(
            f"\n## User Profile\n"
            f"- Name: {profile['name']}\n"
            f"- Role: {profile.get('role', '')}\n"
            f"- Language: {prefs.get('language', 'en')}\n"
            f"- Timezone: {prefs.get('timezone', 'UTC')}\n"
            f"- Default save directory: {tools.get('default_save_dir', '~/Documents/Neo')}\n"
            f"- Obsidian vault: {tools.get('obsidian_vault', 'not configured')}"
        )

    # Inject project context
    if project_id is not None:
        project = get_project(conn, project_id)
        if project:
            goals = json.loads(project.get("goals", "[]") or "[]")
            conventions = json.loads(project.get("conventions", "{}") or "{}")
            goals_str = ", ".join(goals) if goals else "none"
            conv_str = json.dumps(conventions) if conventions else "none"
            parts.append(
                f"\n## Active Project\n"
                f"- Name: {project['name']}\n"
                f"- Description: {project.get('description', '')}\n"
                f"- Goals: {goals_str}\n"
                f"- Conventions: {conv_str}"
            )

    # Inject skill
    if skill_content:
        parts.append(f"\n## Skill Instructions\n{skill_content}")

    return "\n".join(parts)


async def process(
    command: str,
    provider: LLMProvider,
    conn: sqlite3.Connection,
    skill_content: str = "",
    skill_name: str = "",
    routed_tier: str = "",
    messages: list[dict] | None = None,
    project_id: int | None = None,
) -> ProcessResult:
    """Process a user command through the full 6-stage lifecycle.

    Args:
        command: The user's raw command.
        provider: LLM provider to use.
        conn: SQLite connection (caller owns transaction).
        skill_content: Matched skill instructions.
        skill_name: Matched skill name for logging.
        routed_tier: Which tier was selected (LOCAL/GEMINI/CLAUDE).
        messages: Conversation history (list of role/content dicts).
        project_id: Active project ID for context injection.

    Returns:
        ProcessResult with status, message, tool_used, model_used, duration_ms
    """
    start = time.time()
    result: ProcessResult = {
        "status": "success",
        "message": "",
        "tool_used": "",
        "tool_result": None,
        "model_used": provider.name(),
        "routed_tier": routed_tier,
        "duration_ms": 0,
    }

    try:
        # STAGE 1: RECEIVE (already done — command is the input)

        # STAGE 4: SKILL (loaded before calling process)
        system_prompt = build_system_prompt(conn, skill_content, project_id=project_id)

        # Truncate history to fit within context budget
        provider_name = provider.name()
        max_tokens = CONTEXT_BUDGETS.get(provider_name, 100_000)
        reserved = _estimate_tokens(system_prompt)

        truncated_messages: list[dict] | None = None
        if messages:
            truncated_messages = _truncate_history(messages, max_tokens, reserved)

        # STAGE 2+5: PARSE + EXECUTE via tool use
        llm_response = await provider.complete_with_tools(
            system=system_prompt,
            user=command,
            tools=TOOL_DEFINITIONS,
            messages=truncated_messages,
        )

        if llm_response["type"] == "tool_use":
            tool_name = llm_response["tool_name"]
            tool_input = llm_response["tool_input"]
            result["tool_used"] = tool_name

            # Execute the tool
            tool_output = dispatch_tool(tool_name, tool_input)
            result["tool_result"] = tool_output
            result["message"] = f"Executed {tool_name}: {tool_output}"
        else:
            # Text-only response (question, clarification, etc.)
            result["message"] = llm_response.get("content", "")

    except ToolError as e:
        logger.exception("Tool dispatch error")
        result["status"] = "error"
        result["message"] = str(e)
    except Exception:
        logger.exception("Orchestrator error")
        result["status"] = "error"
        result["message"] = "An internal error occurred. Check logs for details."

    # STAGE 6: CONFIRM — log the action (caller owns commit)
    elapsed_ms = int((time.time() - start) * 1000)
    result["duration_ms"] = elapsed_ms

    try:
        log_action(
            conn,
            input_text=command,
            intent="",
            skill_used=skill_name,
            tool_used=result["tool_used"],
            model_used=result["model_used"],
            result={"message": result["message"], "tool_result": result["tool_result"]},
            status=result["status"],
            duration_ms=elapsed_ms,
        )
    except Exception:
        logger.exception("Failed to log action")

    return result


def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Dispatch a tool call to the correct module function.

    Raises ToolError on failure instead of returning error strings.
    Returns a string describing the result.
    """
    if tool_name not in TOOL_REGISTRY:
        raise ToolError(f"Unknown tool: {tool_name}")

    module_path, func_name = TOOL_REGISTRY[tool_name]

    try:
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        result = func(**tool_input)
        return str(result) if result else "Tool executed (no output path)"
    except Exception as e:
        raise ToolError(f"Tool '{tool_name}' failed: {e}") from e
