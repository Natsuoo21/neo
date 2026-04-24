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
        "description": (
            "Create a professional Excel spreadsheet (.xlsx) with formatting, formulas, "
            "and data validation. Professional defaults are applied automatically "
            "(borders, zebra striping, auto-filter, number alignment). "
            "Example: title='Budget', sheets=[{name:'Q1', headers:['Item','Cost'], "
            "rows:[['Rent',1200],['Food',400]], formulas:[{cell:'B3', formula:'=SUM(B2:B2)'}], "
            "column_formats:{'Cost':'#,##0.00'}}]"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Filename for the spreadsheet (without .xlsx extension)",
                },
                "output_path": {
                    "type": "string",
                    "description": "Directory where the file should be saved. If omitted, saves to default directory.",
                },
                "sheets": {
                    "type": "array",
                    "description": "List of sheets with data and optional formulas/formatting.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Sheet tab name (max 31 chars)"},
                            "headers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Column header names",
                            },
                            "rows": {
                                "type": "array",
                                "items": {"type": "array"},
                                "description": "Data rows — each row is an array of values matching the headers. Use numbers for numeric cells.",
                            },
                            "formulas": {
                                "type": "array",
                                "description": "Formulas to place in cells. E.g. [{cell:'B10', formula:'=SUM(B2:B9)'}]",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "cell": {"type": "string"},
                                        "formula": {"type": "string"},
                                    },
                                    "required": ["cell", "formula"],
                                },
                            },
                            "column_formats": {
                                "type": "object",
                                "description": "Number format per column header name. E.g. {'Cost':'#,##0.00', 'Date':'YYYY-MM-DD', 'Rate':'0.0%'}",
                            },
                            "conditional_formatting": {
                                "type": "array",
                                "description": "Conditional formatting rules. Types: color_scale, highlight, data_bar. Use 'column' for header name or 'range' for cell range.",
                                "items": {"type": "object"},
                            },
                            "data_validation": {
                                "type": "array",
                                "description": "Dropdown lists for columns. E.g. [{column:'Status', type:'list', values:['Done','In Progress','Not Started']}]",
                                "items": {"type": "object"},
                            },
                            "auto_filter": {
                                "type": "boolean",
                                "description": "Enable filter arrows on header row. Default: true.",
                            },
                        },
                        "required": ["name", "headers", "rows"],
                    },
                },
                "formatting": {
                    "type": "object",
                    "description": (
                        "Document-level style. Defaults: theme='professional', "
                        "alternate_row_shading=true, borders='thin', font='Calibri', font_size=11."
                    ),
                    "properties": {
                        "theme": {
                            "type": "string",
                            "enum": ["professional", "minimal", "corporate", "colorful"],
                            "description": "Color theme preset",
                        },
                        "alternate_row_shading": {"type": "boolean", "description": "Zebra stripes (default true)"},
                        "borders": {
                            "type": "string",
                            "enum": ["none", "thin", "medium", "all"],
                            "description": "Border style (default 'thin')",
                        },
                        "header_color": {"type": "string", "description": "Hex color for header fill (e.g. '2B5797')"},
                        "font": {"type": "string", "description": "Font name (default 'Calibri')"},
                        "font_size": {"type": "integer", "description": "Font size (default 11)"},
                    },
                },
            },
            "required": ["title", "sheets"],
        },
    },
    {
        "name": "create_presentation",
        "description": (
            "Create a professional PowerPoint presentation (.pptx) with formatted bullets, "
            "tables, speaker notes, and consistent theming. Use 'bullets' for slide content "
            "(not 'content'). Professional defaults: slide numbers, Calibri fonts, blue theme."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Filename for the presentation (without .pptx extension)",
                },
                "output_path": {
                    "type": "string",
                    "description": "Directory where the file should be saved. If omitted, saves to default directory.",
                },
                "slides": {
                    "type": "array",
                    "description": "List of slides with structured content.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Slide heading (state the takeaway)"},
                            "layout": {
                                "type": "string",
                                "enum": ["title", "content", "section_header", "two_column", "title_only", "blank"],
                                "description": "Slide layout. Default: auto-detect from content.",
                            },
                            "bullets": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Bullet points (max 6, max 8 words each). Preferred over body/content.",
                            },
                            "numbered_list": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Numbered list items",
                            },
                            "body": {"type": "string", "description": "Paragraph text (use bullets instead when possible)"},
                            "table": {
                                "type": "object",
                                "description": "Data table: {headers: [...], rows: [[...]]}",
                                "properties": {
                                    "headers": {"type": "array", "items": {"type": "string"}},
                                    "rows": {"type": "array", "items": {"type": "array"}},
                                },
                            },
                            "speaker_notes": {
                                "type": "string",
                                "description": "Presenter notes (1-2 key talking points). ALWAYS include these.",
                            },
                            "left_content": {
                                "type": "object",
                                "description": "Left column content for two_column layout: {bullets:[...]} or {body:'...'}",
                            },
                            "right_content": {
                                "type": "object",
                                "description": "Right column content for two_column layout",
                            },
                        },
                        "required": ["title"],
                    },
                },
                "theme": {
                    "type": "object",
                    "description": (
                        "Color and font settings. Defaults: primary_color='2B5797', "
                        "font_title='Calibri', font_size_title=28, font_size_bullets=16."
                    ),
                    "properties": {
                        "primary_color": {"type": "string", "description": "Hex color for titles/accents"},
                        "text_color": {"type": "string", "description": "Hex color for body text"},
                        "font_title": {"type": "string"},
                        "font_body": {"type": "string"},
                        "font_size_title": {"type": "integer"},
                        "font_size_bullets": {"type": "integer"},
                    },
                },
            },
            "required": ["title", "slides"],
        },
    },
    {
        "name": "create_document",
        "description": (
            "Create a professional Word document (.docx). Two modes: "
            "1) Simple: use 'content' string with markdown (# headings, - bullets, 1. numbered, "
            "**bold**, *italic*, __underline__, --- page break, |col|col| tables). "
            "2) Rich: use 'sections' array for complex docs with tables, mixed formatting. "
            "Professional defaults applied: Calibri 11pt, 1.15 spacing, auto page numbers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Filename for the document (without .docx extension)",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Document body with markdown formatting. Use # for headings, - for bullets, "
                        "1. for numbered lists, **bold**, *italic*, __underline__, --- for page breaks, "
                        "|H1|H2|/|---|---|/|d1|d2| for tables. Use this for simple documents."
                    ),
                },
                "sections": {
                    "type": "array",
                    "description": (
                        "Structured sections for complex documents. Each section can have: "
                        "heading (str), level (1-3), body (str with **bold**/*italic*), "
                        "bullets (list), numbered_list (list), "
                        "table ({headers:[...], rows:[[...]], style:'professional'}), "
                        "page_break (bool). Use this instead of content for documents with tables."
                    ),
                    "items": {"type": "object"},
                },
                "formatting": {
                    "type": "object",
                    "description": (
                        "Document style. Defaults: font='Calibri', font_size=11, line_spacing=1.15, "
                        "margins=1 inch. Set page_numbers=true, toc=true as needed."
                    ),
                    "properties": {
                        "font": {"type": "string"},
                        "font_size": {"type": "integer"},
                        "line_spacing": {"type": "number"},
                        "page_numbers": {"type": "boolean", "description": "Add page numbers (auto for 2+ sections)"},
                        "toc": {"type": "boolean", "description": "Add Table of Contents"},
                        "margins": {
                            "type": "object",
                            "description": "Margins in inches: {top, bottom, left, right}",
                        },
                    },
                },
                "headers_footers": {
                    "type": "object",
                    "description": (
                        "Header/footer content. Keys: header_left, header_right, footer_center, footer_right. "
                        "Supports {date}, {page}, {pages} placeholders. "
                        "E.g. {footer_center: 'Page {page} of {pages}'}"
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": "Directory where the file should be saved. If omitted, saves to default directory.",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "create_note",
        "description": (
            "Create an Obsidian note (.md) with YAML frontmatter in the user's configured vault. "
            "The vault path is set in the user profile — you do NOT need to connect or configure anything. "
            "Just call this tool with a title and content to create a note."
        ),
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
        "name": "read_note",
        "description": (
            "Read an Obsidian note from the vault by name. Supports fuzzy matching — "
            "the name does not need to be exact. You can pass the note title, filename, "
            "or even a partial/approximate name and it will find the best match. "
            "Returns the full note content, path, and title."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Note name or title to find (fuzzy matching supported)",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "search_notes",
        "description": (
            "Search notes in the Obsidian vault by keyword. Searches both filenames and "
            "file contents. Returns matching notes with relevance scores and context snippets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — a keyword or phrase to find in notes",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_notes",
        "description": (
            "List notes in the Obsidian vault. Optionally filter by subfolder. "
            "Returns note titles, paths, tags, and modification dates. "
            "Also returns the folder structure of the vault."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {
                    "type": "string",
                    "description": "Subfolder to list (e.g. 'projects', 'daily'). Empty for all notes.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum notes to return (default 50)",
                },
            },
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
        "name": "fill_form",
        "description": (
            "Fill form fields on a web page and optionally submit. Provide a mapping of CSS selectors to values."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL of the page with the form"},
                "fields": {
                    "type": "object",
                    "description": (
                        'Mapping of CSS selectors to values (e.g. {"#name": "John", "#email": "john@example.com"})'
                    ),
                },
                "submit_selector": {
                    "type": "string",
                    "description": "CSS selector for the submit button (optional — omit to fill without submitting)",
                },
            },
            "required": ["url", "fields"],
        },
    },
    {
        "name": "download_file",
        "description": "Download a file from a URL to the local filesystem.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL of the file to download"},
                "target_dir": {
                    "type": "string",
                    "description": "Directory to save the file in (default: ~/Downloads)",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "monitor_page",
        "description": (
            "Monitor a web page element and trigger when a condition is met. "
            "Useful for price tracking, stock availability, content changes, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to monitor"},
                "selector": {"type": "string", "description": "CSS selector for the element to watch"},
                "condition": {
                    "type": "string",
                    "enum": ["changed", "contains", "not_contains", "appeared", "disappeared"],
                    "description": "Condition to trigger on (default: changed)",
                },
                "reference_value": {
                    "type": "string",
                    "description": "Value to compare against (for contains/not_contains conditions)",
                },
                "check_interval_s": {
                    "type": "integer",
                    "description": "Seconds between checks (minimum 10, default 30)",
                },
                "max_checks": {
                    "type": "integer",
                    "description": "Maximum number of checks before giving up (default 60)",
                },
            },
            "required": ["url", "selector"],
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
        "description": (
            "Send a professional email via Gmail with optional HTML formatting, CC/BCC, "
            "and attachments. If body contains markdown (**bold**, - bullets), HTML is "
            "auto-generated. Destructive action requiring confirmation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject (under 60 chars, action-oriented)"},
                "body": {
                    "type": "string",
                    "description": (
                        "Email body. Supports markdown: **bold**, *italic*, - bullets, 1. numbered. "
                        "Auto-converted to HTML when formatting is detected."
                    ),
                },
                "cc": {"type": "string", "description": "CC recipients (comma-separated)"},
                "bcc": {"type": "string", "description": "BCC recipients (comma-separated)"},
                "html_body": {
                    "type": "string",
                    "description": "Explicit HTML body (overrides auto-conversion from body)",
                },
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths to attach (e.g. previously created documents)",
                },
                "signature": {"type": "string", "description": "Signature text to append"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "reply_to_email",
        "description": (
            "Reply to an existing email by ID. Preserves thread. "
            "Supports HTML formatting, CC, and attachments. Destructive action requiring confirmation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "The Gmail message ID to reply to"},
                "body": {
                    "type": "string",
                    "description": "Reply body text (supports markdown for auto HTML conversion)",
                },
                "cc": {"type": "string", "description": "CC recipients (comma-separated)"},
                "html_body": {"type": "string", "description": "Explicit HTML body"},
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths to attach",
                },
            },
            "required": ["email_id", "body"],
        },
    },
    {
        "name": "create_skill",
        "description": (
            "Create a new Neo skill that can be activated via slash command. "
            "Skills are reusable instruction sets that guide your behaviour for specific task types."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "snake_case skill name (e.g., 'meeting_agenda')",
                },
                "description": {
                    "type": "string",
                    "description": "One-line description of what the skill does",
                },
                "instructions": {
                    "type": "string",
                    "description": "Markdown body with LLM instructions for this skill",
                },
                "task_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords associated with this skill",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tools this skill may use (e.g., create_document)",
                },
            },
            "required": ["name", "description", "instructions"],
        },
    },
    {
        "name": "create_automation",
        "description": (
            "Create a new automation that runs a command automatically based on a trigger. "
            "Trigger types: 'schedule' (cron-based, e.g. every morning), "
            "'startup' (runs when Neo starts), "
            "'file_event' (runs when a file changes), "
            "'pattern' (runs when the user types a matching command). "
            "The command is the text that Neo will execute as if the user typed it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the automation (e.g., 'Morning briefing')",
                },
                "trigger_type": {
                    "type": "string",
                    "enum": ["schedule", "startup", "file_event", "pattern"],
                    "description": "What triggers this automation",
                },
                "command": {
                    "type": "string",
                    "description": (
                        "The command Neo will execute when triggered (e.g., 'open Obsidian and show my daily note')"
                    ),
                },
                "trigger_config": {
                    "type": "object",
                    "description": (
                        "Trigger-specific configuration. "
                        'For \'schedule\': {"cron": "0 9 * * *"} (cron expression). '
                        'For \'file_event\': {"path": "/path/to/watch", '
                        '"pattern": "*.md", '
                        '"event_types": ["created", "modified"]}. '
                        "For 'startup': {} (no config needed). "
                        'For \'pattern\': {"match": "keyword to match"}.'
                    ),
                },
            },
            "required": ["name", "trigger_type", "command"],
        },
    },
    {
        "name": "open_app",
        "description": (
            "Open an application on the user's computer. "
            "Use common app names like 'obsidian', 'vscode', 'chrome', 'notepad', 'explorer', 'firefox', 'terminal'. "
            "Also supports URI protocols like 'obsidian://open?vault=MyVault' or 'vscode://file/path'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": (
                        "Application name, alias, or URI protocol "
                        "(e.g., 'obsidian', 'chrome', 'vscode', 'obsidian://open?vault=MyVault')"
                    ),
                },
                "args": {
                    "type": "string",
                    "description": "Optional arguments to pass to the application (e.g., a file path to open)",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "manage_mcp",
        "description": (
            "Manage MCP (Model Context Protocol) remote servers ONLY. "
            "This is NOT for Obsidian, files, or any other tool — it is exclusively for MCP protocol servers "
            "that expose tools via HTTP/SSE (e.g. GitHub MCP, Slack MCP, weather MCP). "
            "Actions: 'list' (show all servers), 'connect' (start a server), 'disconnect' (stop a server), "
            "'add' (add a new remote MCP server with URL and optional auth), 'remove' (remove a remote server)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "connect", "disconnect", "add", "remove"],
                    "description": "Action to perform",
                },
                "name": {
                    "type": "string",
                    "description": "Server name (required for all actions except 'list')",
                },
                "url": {
                    "type": "string",
                    "description": "Server URL (required for 'add')",
                },
                "transport": {
                    "type": "string",
                    "enum": ["streamable_http", "sse"],
                    "description": "Transport type (default: streamable_http)",
                },
                "auth_type": {
                    "type": "string",
                    "enum": ["bearer", "api_key", ""],
                    "description": "Authentication type (empty for no auth)",
                },
                "token_env": {
                    "type": "string",
                    "description": "Environment variable name for the API key/token",
                },
                "token_value": {
                    "type": "string",
                    "description": "The actual API key or token value to save securely",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read and parse a file into structured text. Supports Excel (.xlsx), "
            "Word (.docx), PowerPoint (.pptx), PDF (.pdf), CSV/TSV, and plain text files. "
            "Use this when the user mentions a file path they want you to analyze, "
            "or when you need to read a document to complete a task."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to read",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "edit_excel",
        "description": (
            "Edit an existing Excel spreadsheet (.xlsx). Update individual cells, "
            "append or delete rows, add or remove sheets. Use this when the user wants to "
            "modify an existing spreadsheet rather than create a new one. "
            "Example: edit_excel(file_path='~/budget.xlsx', updates=[{cell:'B5', value:1500}])"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the existing .xlsx file to edit",
                },
                "updates": {
                    "type": "array",
                    "description": (
                        "Cell updates. Each: {cell:'B5' or 'Sheet1!B5', value:1500, "
                        "format:'#,##0.00' (optional), bold:true (optional)}"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "cell": {"type": "string", "description": "Cell reference (e.g. 'B5' or 'Sheet1!B5')"},
                            "value": {"description": "New cell value (string, number, or null)"},
                            "format": {"type": "string", "description": "Number format string"},
                            "bold": {"type": "boolean", "description": "Make cell bold"},
                        },
                        "required": ["cell"],
                    },
                },
                "add_rows": {
                    "type": "array",
                    "description": "Rows to append. Each: {sheet:'Sheet1' (optional), values:[1,'text',3]}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sheet": {"type": "string"},
                            "values": {"type": "array"},
                        },
                        "required": ["values"],
                    },
                },
                "delete_rows": {
                    "type": "array",
                    "description": "Rows to delete. Each: {sheet:'Sheet1' (optional), row:5} (1-based)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sheet": {"type": "string"},
                            "row": {"type": "integer"},
                        },
                        "required": ["row"],
                    },
                },
                "add_sheets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Sheet names to create",
                },
                "delete_sheets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Sheet names to delete",
                },
                "save_as": {
                    "type": "string",
                    "description": "Save to a different path instead of overwriting the original",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "edit_document",
        "description": (
            "Edit an existing Word document (.docx). Replace text, add or delete paragraphs, "
            "headings, bullets, and tables. Use this when the user wants to modify an existing "
            "document rather than create a new one. "
            "Example: edit_document(file_path='~/report.docx', operations=[{type:'replace_text', "
            "find:'Q3', replace:'Q4'}])"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the existing .docx file to edit",
                },
                "operations": {
                    "type": "array",
                    "description": (
                        "List of editing operations. Types: "
                        "'replace_text' ({find, replace}), "
                        "'add_paragraph' ({text}), "
                        "'add_heading' ({text, level}), "
                        "'add_bullet' ({text}), "
                        "'add_table' ({headers, rows}), "
                        "'delete_paragraph' ({index}), "
                        "'replace_paragraph' ({index, text})"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "replace_text", "add_paragraph", "add_heading",
                                    "add_bullet", "add_table",
                                    "delete_paragraph", "replace_paragraph",
                                ],
                            },
                            "find": {"type": "string"},
                            "replace": {"type": "string"},
                            "text": {"type": "string"},
                            "level": {"type": "integer"},
                            "index": {"type": "integer"},
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "array"}},
                        },
                        "required": ["type"],
                    },
                },
                "save_as": {
                    "type": "string",
                    "description": "Save to a different path instead of overwriting the original",
                },
            },
            "required": ["file_path", "operations"],
        },
    },
    {
        "name": "edit_presentation",
        "description": (
            "Edit an existing PowerPoint presentation (.pptx). Update slide content, "
            "add new slides, delete slides, or update speaker notes. Use this when the user "
            "wants to modify an existing presentation rather than create a new one. "
            "Example: edit_presentation(file_path='~/deck.pptx', operations=[{type:'update_slide', "
            "slide:2, title:'New Title', bullets:['Point 1','Point 2']}])"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the existing .pptx file to edit",
                },
                "operations": {
                    "type": "array",
                    "description": (
                        "List of editing operations. Types: "
                        "'update_slide' ({slide (1-based), title, bullets, body, notes}), "
                        "'add_slide' ({title, bullets, body, speaker_notes}), "
                        "'delete_slide' ({slide (1-based)}), "
                        "'update_notes' ({slide (1-based), notes})"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["update_slide", "add_slide", "delete_slide", "update_notes"],
                            },
                            "slide": {"type": "integer", "description": "Slide number (1-based)"},
                            "title": {"type": "string"},
                            "bullets": {"type": "array", "items": {"type": "string"}},
                            "body": {"type": "string"},
                            "notes": {"type": "string"},
                            "speaker_notes": {"type": "string"},
                        },
                        "required": ["type"],
                    },
                },
                "save_as": {
                    "type": "string",
                    "description": "Save to a different path instead of overwriting the original",
                },
            },
            "required": ["file_path", "operations"],
        },
    },
]

# Maps LLM tool names to (module_name, function_name)
TOOL_REGISTRY: dict[str, tuple[str, str]] = {
    "create_excel": ("neo.tools.excel", "create_workbook"),
    "create_presentation": ("neo.tools.powerpoint", "create_presentation"),
    "create_document": ("neo.tools.word", "create_document"),
    "create_note": ("neo.tools.obsidian", "create_note"),
    "read_note": ("neo.tools.obsidian", "read_note"),
    "search_notes": ("neo.tools.obsidian", "search_notes"),
    "list_notes": ("neo.tools.obsidian", "list_notes"),
    "manage_file": ("neo.tools.files", "manage_file"),
    "browse_url": ("neo.tools.browser", "browse_url"),
    "take_screenshot": ("neo.tools.browser", "take_screenshot"),
    "fill_form": ("neo.tools.browser", "fill_form"),
    "download_file": ("neo.tools.browser", "download_file"),
    "monitor_page": ("neo.tools.browser", "monitor_page"),
    "list_calendar_events": ("neo.tools.calendar", "list_events"),
    "create_calendar_event": ("neo.tools.calendar", "create_event"),
    "list_emails": ("neo.tools.gmail", "list_emails"),
    "read_email": ("neo.tools.gmail", "read_email"),
    "send_email": ("neo.tools.gmail", "send_email"),
    "reply_to_email": ("neo.tools.gmail", "reply_to"),
    "create_skill": ("neo.skills.loader", "create_user_skill_from_tool"),
    "create_automation": ("neo.automations.tool", "create_automation_from_tool"),
    "open_app": ("neo.tools.open_app", "open_app"),
    "manage_mcp": ("neo.tools.manage_mcp", "manage_mcp"),
    "read_file": ("neo.tools.file_reader", "parse_file"),
    "edit_excel": ("neo.tools.excel", "edit_workbook"),
    "edit_document": ("neo.tools.word", "edit_document"),
    "edit_presentation": ("neo.tools.powerpoint", "edit_presentation"),
}


def _inject_tool_paths(conn) -> None:
    """Set tool-specific paths from the user profile before dispatch.

    Reads ``tool_paths`` from the user profile and injects them into the
    relevant tool modules so they use the correct configured paths.
    """
    profile = get_user_profile(conn)
    if not profile:
        return

    tools = json.loads(profile.get("tool_paths", "{}") or "{}")

    # Obsidian vault path
    vault = tools.get("obsidian_vault", "")
    if vault:
        from neo.tools.obsidian import set_vault_path

        set_vault_path(vault)


def _estimate_tokens(content: str | list) -> int:
    """Rough token estimate: ~4 chars per token, ~1000 tokens per image."""
    if isinstance(content, str):
        return len(content) // 4
    # Multimodal content (list of blocks)
    total = 0
    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                total += len(block.get("text", "")) // 4
            elif block.get("type") == "image":
                total += 1000  # approximate tokens per image
        elif isinstance(block, str):
            total += len(block) // 4
    return total


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
    available_skills: list[dict] | None = None,
) -> str:
    """Assemble the system prompt from user profile + skill + project.

    Components:
    1. Base Neo instructions
    2. User profile (name, role, preferences, tool paths)
    3. Active project context (if provided)
    4. Research mode instructions (if routed to Gemini)
    5. Available skill commands listing
    6. Skill instructions (if a matching skill was found)
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
            f"- NEVER write to system directories (C:\\Windows, /etc, /usr, etc.) or sensitive dirs (.ssh, .gnupg).\n"
            f"\n## Tool Guidance\n"
            f"- **Obsidian notes**: The vault is already configured — do NOT use `manage_mcp` for Obsidian.\n"
            f"  - `read_note` — Read a note by name (fuzzy matching: partial names, approximate spelling all work).\n"
            f"  - `search_notes` — Search notes by keyword in titles and content.\n"
            f"  - `list_notes` — List all notes or notes in a subfolder. Shows vault folder structure.\n"
            f"  - `create_note` — Create a new note with frontmatter.\n"
            f"  - `append_to_note` — Add content to an existing note.\n"
            f"  - When the user asks about a note, ALWAYS use `read_note` first. "
            f"If the name is ambiguous, use `search_notes` or `list_notes` to find it.\n"
            f"- **MCP servers**: Use `manage_mcp` ONLY for MCP protocol servers "
            f"(remote APIs that expose tools via HTTP/SSE).\n"
            f"- When the user mentions their vault, Obsidian, or notes, use the Obsidian tools, never manage_mcp."
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

    # Inject available skill commands
    if available_skills:
        lines = ["\n## Available Skill Commands"]
        lines.append("The user can activate skills with slash commands:")
        for s in available_skills:
            lines.append(f"- /{s['name']} \u2014 {s.get('description', '')}")
        parts.append("\n".join(lines))

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
    available_skills: list[dict] | None = None,
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
        available_skills: List of enabled skill commands for system prompt.

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
            available_skills=available_skills,
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
            tools=get_all_tool_definitions(),
            messages=truncated_messages,
        )

        if llm_response["type"] == "tool_use":
            tool_name = llm_response["tool_name"]
            tool_input = llm_response["tool_input"]
            result["tool_used"] = tool_name

            # Inject user profile paths into tools that need them
            _inject_tool_paths(conn)

            # Execute the tool
            tool_output = await dispatch_tool(tool_name, tool_input)
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


async def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """Dispatch a tool call to the correct module function.

    Supports both built-in tools (TOOL_REGISTRY) and MCP plugin tools
    (prefixed with ``plugin::``).  Plugin tools are routed through the
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
            return await _mcp_host.call_tool(plugin_name, plugin_tool, tool_input)
        except Exception as e:
            raise ToolError(f"Plugin tool '{tool_name}' failed: {e}") from e

    # manage_mcp: async tool that needs the MCPHost instance injected
    if tool_name == "manage_mcp":
        if _mcp_host is None:
            raise ToolError("MCP host is not available.")
        try:
            from neo.tools.manage_mcp import manage_mcp

            return await manage_mcp(host=_mcp_host, **tool_input)
        except Exception as e:
            raise ToolError(f"Tool 'manage_mcp' failed: {e}") from e

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


def get_all_tool_definitions() -> list[dict]:
    """Return built-in tool definitions plus tools from running MCP plugins.

    Plugin tools are converted to the same format as TOOL_DEFINITIONS with
    names prefixed as ``plugin::{plugin_name}::{tool_name}``.
    """
    tools = list(TOOL_DEFINITIONS)

    if _mcp_host is None:
        return tools

    for plugin in _mcp_host.list_plugins():
        if plugin.get("status") != "running":
            continue

        plugin_name = plugin["name"]
        for tool in _mcp_host.get_plugin_tools(plugin_name):
            tools.append(
                {
                    "name": f"plugin::{plugin_name}::{tool['name']}",
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("inputSchema", {"type": "object", "properties": {}}),
                }
            )

    return tools
