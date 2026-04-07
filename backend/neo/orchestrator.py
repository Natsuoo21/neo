"""Neo Orchestrator — Central nervous system.

Receives a command string, parses intent, selects skill,
routes to LLM, executes tool, logs action.

6-stage lifecycle: RECEIVE → PARSE → ROUTE → SKILL → EXECUTE → CONFIRM
"""

from __future__ import annotations

import importlib
import json
import logging
import sqlite3
import time
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from neo.plugins.mcp_host import MCPHost

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
                "output_path": {
                    "type": "string",
                    "description": "Full path where the file should be saved. If omitted, saves to default directory.",
                },
                "sheets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
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
                "output_path": {
                    "type": "string",
                    "description": "Full path where the file should be saved. If omitted, saves to default directory.",
                },
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
                "output_path": {
                    "type": "string",
                    "description": "Full path where the file should be saved. If omitted, saves to default directory.",
                },
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
    {
        "name": "browse_url",
        "description": "Navigate to a URL and extract text content from the page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to"},
                "extract_selector": {
                    "type": "string",
                    "description": "CSS selector for content extraction (default: 'body')",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "take_screenshot",
        "description": "Take a full-page screenshot of a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to screenshot"},
                "output_path": {"type": "string", "description": "Where to save the screenshot"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "list_calendar_events",
        "description": "List upcoming Google Calendar events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to look ahead (default: 7)"},
                "max_results": {"type": "integer", "description": "Max events to return (default: 20)"},
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Create a Google Calendar event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title"},
                "start_time": {"type": "string", "description": "ISO 8601 start time"},
                "end_time": {"type": "string", "description": "ISO 8601 end time"},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attendee email addresses",
                },
                "description": {"type": "string", "description": "Event description"},
            },
            "required": ["title", "start_time", "end_time"],
        },
    },
    {
        "name": "list_emails",
        "description": "List Gmail emails matching a search query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail search query (e.g., 'is:unread')"},
                "limit": {"type": "integer", "description": "Max emails to return (default: 10)"},
            },
        },
    },
    {
        "name": "read_email",
        "description": "Read a full email by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "The Gmail message ID"},
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an email via Gmail. This is a destructive action requiring confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body text"},
            },
            "required": ["to", "subject", "body"],
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
    "browse_url": ("neo.tools.browser", "browse_url"),
    "take_screenshot": ("neo.tools.browser", "take_screenshot"),
    "list_calendar_events": ("neo.tools.calendar", "list_events"),
    "create_calendar_event": ("neo.tools.calendar", "create_event"),
    "list_emails": ("neo.tools.gmail", "list_emails"),
    "read_email": ("neo.tools.gmail", "read_email"),
    "send_email": ("neo.tools.gmail", "send_email"),
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
    if not messages:
        return []

    budget = max_tokens - reserved_tokens
    if budget <= 0:
        return messages[-1:]

    # Always include the last message (current user command)
    last = messages[-1]
    remaining = messages[:-1]

    result: list[dict] = [last]
    total = _estimate_tokens(last.get("content", ""))

    # Add older messages from newest to oldest
    for msg in reversed(remaining):
        msg_tokens = _estimate_tokens(msg.get("content", ""))
        if total + msg_tokens > budget:
            break
        result.append(msg)
        total += msg_tokens

    # result is [last, second-to-last, ...] — reverse the prefix
    return list(reversed(result[1:])) + [result[0]]


# Default context budgets per model tier (in estimated tokens)
CONTEXT_BUDGETS: dict[str, int] = {
    "ollama": 4_000,
    "gemini": 30_000,
    "openai": 128_000,
    "claude": 100_000,
    "mock": 100_000,
}


_GEMINI_RESEARCH_PROMPT = (
    "\n## Research Mode\n"
    "You are optimised for research and information synthesis. Follow these guidelines:\n"
    "- Provide well-structured answers with clear sections and headings.\n"
    "- When comparing items, use tables or side-by-side analysis.\n"
    "- Cite sources or reasoning for factual claims.\n"
    "- Summarise key findings in an executive summary at the top.\n"
    "- If information is uncertain, say so explicitly rather than guessing.\n"
    "- Prefer depth over breadth — thorough analysis of fewer points beats shallow coverage of many."
)


def build_system_prompt(
    conn: sqlite3.Connection,
    skill_content: str = "",
    project_id: int | None = None,
    routed_tier: str = "",
) -> str:
    """Assemble the system prompt from user profile + skill + project.

    Components:
    1. Base Neo instructions
    2. User profile (name, role, preferences, tool paths)
    3. Active project context (if provided)
    4. Research mode instructions (if routed to Gemini)
    5. Skill instructions (if a matching skill was found)
    """
    parts = [
        "You are Neo, a personal intelligence agent. "
        "You execute real actions on the user's computer — creating files, "
        "managing documents, and automating tasks. You are NOT a chatbot. "
        "When the user asks you to create something, you MUST call the appropriate tool. "
        "NEVER simulate, describe, or pretend to execute a tool — always make a real tool_use call. "
        "If you cannot call a tool, say so explicitly instead of faking the output. "
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
            f"- Downloads directory: ~/Downloads\n"
            f"- Obsidian vault: {tools.get('obsidian_vault', 'not configured')}\n"
            f"- You can save files to any user directory. Use output_path when the user specifies a location.\n"
            f"- NEVER write to system directories (C:\\Windows, /etc, /usr, etc.) or sensitive dirs (.ssh, .gnupg)."
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

    # Inject research mode for Gemini
    if routed_tier == "GEMINI":
        parts.append(_GEMINI_RESEARCH_PROMPT)

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
        system_prompt = build_system_prompt(
            conn,
            skill_content,
            project_id=project_id,
            routed_tier=routed_tier,
        )

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
    except Exception as e:
        logger.exception("Orchestrator error")
        result["status"] = "error"
        err_msg = str(e)
        # Translate common API errors into user-friendly messages
        lower = err_msg.lower()
        if "credit balance" in lower or "billing" in lower:
            result["message"] = "API credits exhausted. Please top up your account or switch providers."
        elif "api key" in lower or "authentication" in lower or "unauthorized" in lower:
            result["message"] = "Invalid or missing API key. Check your configuration."
        elif "rate limit" in lower or "too many requests" in lower:
            result["message"] = "Rate limited by the AI provider. Please wait a moment and try again."
        elif err_msg and len(err_msg) < 200:
            result["message"] = err_msg
        else:
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
            routed_tier=result["routed_tier"],
            result={"message": result["message"], "tool_result": result["tool_result"]},
            status=result["status"],
            duration_ms=elapsed_ms,
        )
    except Exception:
        logger.exception("Failed to log action")

    return result


def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Dispatch a tool call to the correct module function.

    Supports both built-in tools (TOOL_REGISTRY) and MCP plugin tools
    (prefixed with ``plugin_``).  Plugin tools are routed through the
    global :data:`_mcp_host` if available.

    Raises ToolError on failure instead of returning error strings.
    Returns a string describing the result.
    """
    # Plugin tool dispatch: plugin::{plugin_name}::{tool_name}
    if tool_name.startswith("plugin::") and _mcp_host is not None:
        parts = tool_name.split("::", 2)  # ["plugin", plugin_name, tool_name]
        if len(parts) < 3 or not parts[1] or not parts[2]:
            raise ToolError(f"Invalid plugin tool name: {tool_name}")
        plugin_name, plugin_tool = parts[1], parts[2]
        try:
            return _mcp_host.call_tool(plugin_name, plugin_tool, tool_input)
        except Exception as e:
            raise ToolError(f"Plugin tool '{tool_name}' failed: {e}") from e

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


# MCP host reference — set by server.py during lifespan
_mcp_host: "MCPHost | None" = None


def set_mcp_host(host: "MCPHost | None") -> None:
    """Register the MCP host for plugin tool dispatch."""
    global _mcp_host
    _mcp_host = host
