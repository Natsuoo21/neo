"""Neo Orchestrator — Central nervous system.

Receives a command string, parses intent, selects skill,
routes to LLM, executes tool, logs action.

6-stage lifecycle: RECEIVE → PARSE → ROUTE → SKILL → EXECUTE → CONFIRM
"""

import json
import logging
import sqlite3
import time

from neo.llm.provider import LLMProvider
from neo.memory.models import get_user_profile, log_action

logger = logging.getLogger(__name__)

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


def build_system_prompt(conn: sqlite3.Connection, skill_content: str = "") -> str:
    """Assemble the system prompt from user profile + skill.

    Components:
    1. Base Neo instructions
    2. User profile (name, role, preferences, tool paths)
    3. Skill instructions (if a matching skill was found)
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

    # Inject skill
    if skill_content:
        parts.append(f"\n## Skill Instructions\n{skill_content}")

    return "\n".join(parts)


async def process(
    command: str,
    provider: LLMProvider,
    conn: sqlite3.Connection,
    skill_content: str = "",
) -> dict:
    """Process a user command through the full 6-stage lifecycle.

    Returns:
        dict with keys: status, message, tool_used, model_used, duration_ms
    """
    start = time.time()
    result = {
        "status": "success",
        "message": "",
        "tool_used": "",
        "tool_result": None,
        "model_used": provider.name(),
        "duration_ms": 0,
    }

    try:
        # STAGE 1: RECEIVE (already done — command is the input)

        # STAGE 4: SKILL (loaded before calling process)
        system_prompt = build_system_prompt(conn, skill_content)

        # STAGE 3: ROUTE (for now, use the provider passed in; P1 adds router)

        # STAGE 2+5: PARSE + EXECUTE via tool use
        llm_response = await provider.complete_with_tools(
            system=system_prompt,
            user=command,
            tools=TOOL_DEFINITIONS,
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

    except Exception as e:
        logger.error("Orchestrator error: %s", e)
        result["status"] = "error"
        result["message"] = str(e)

    # STAGE 6: CONFIRM — log the action
    elapsed_ms = int((time.time() - start) * 1000)
    result["duration_ms"] = elapsed_ms

    try:
        log_action(
            conn,
            input_text=command,
            intent="",
            skill_used=skill_content[:50] if skill_content else "",
            tool_used=str(result["tool_used"]),
            model_used=str(result["model_used"]),
            result={"message": result["message"], "tool_result": result["tool_result"]},
            status=str(result["status"]),
            duration_ms=elapsed_ms,
        )
        conn.commit()
    except Exception as e:
        logger.error("Failed to log action: %s", e)

    return result


def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Dispatch a tool call to the correct module function.

    Returns a string describing the result.
    """
    if tool_name not in TOOL_REGISTRY:
        return f"Unknown tool: {tool_name}"

    module_path, func_name = TOOL_REGISTRY[tool_name]

    try:
        import importlib

        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        result = func(**tool_input)
        return str(result) if result else "Tool executed (no output path)"
    except Exception as e:
        logger.error("Tool dispatch error for %s: %s", tool_name, e)
        return f"Tool error: {e}"
