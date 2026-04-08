#!/usr/bin/env python3
"""OpenHands MCP plugin — stdio transport.

Bridges Neo to an OpenHands instance for sandboxed code execution,
shell commands, and file operations.  Communicates with the OpenHands
REST API over HTTP.

Config:
    PLUGIN_OPENHANDS_URL  — Base URL of the OpenHands server (default: http://localhost:3000)
"""

import json
import os
import sys
import urllib.error
import urllib.request

# OpenHands server URL from environment
_OPENHANDS_URL = os.environ.get("PLUGIN_OPENHANDS_URL", "http://localhost:3000")

# Conversation ID — created on first tool call, reused within session
_conversation_id: str | None = None


# ── Tools exposed via MCP ──

TOOLS = [
    {
        "name": "execute_code",
        "description": "Execute code in a sandboxed environment. Returns stdout/stderr.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The code to execute"},
                "language": {
                    "type": "string",
                    "description": "Programming language (default: python)",
                    "enum": ["python", "javascript", "bash"],
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "execute_shell",
        "description": "Execute a shell command in the sandbox. Returns stdout/stderr.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the sandbox workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path within the sandbox workspace"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file in the sandbox workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path within the sandbox workspace"},
                "content": {"type": "string", "description": "File content to write"},
            },
            "required": ["path", "content"],
        },
    },
]


# ── HTTP helpers ──


def _http_request(method: str, path: str, body: dict | None = None) -> dict:
    """Make an HTTP request to the OpenHands API.

    Raises RuntimeError with a clear message on connection failure.
    """
    url = f"{_OPENHANDS_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"OpenHands is not running at {_OPENHANDS_URL}. "
            f"Start it first. (error: {e.reason})"
        ) from e
    except json.JSONDecodeError:
        return {}


def _ensure_conversation() -> str:
    """Create a conversation if one doesn't exist yet, return its ID."""
    global _conversation_id
    if _conversation_id is not None:
        return _conversation_id

    result = _http_request("POST", "/api/conversations", {})
    _conversation_id = result.get("conversation_id", result.get("id", "default"))
    return _conversation_id


# ── Tool implementations ──


def _execute_code(arguments: dict) -> str:
    code = arguments.get("code", "")
    language = arguments.get("language", "python")
    cid = _ensure_conversation()

    if language == "python":
        cmd = f"python3 -c {json.dumps(code)}"
    elif language == "javascript":
        cmd = f"node -e {json.dumps(code)}"
    elif language == "bash":
        cmd = code
    else:
        cmd = f"python3 -c {json.dumps(code)}"

    result = _http_request("POST", f"/api/conversations/{cid}/actions", {
        "action": "CmdRunAction",
        "args": {"command": cmd},
    })

    output = result.get("observation", {}).get("content", "")
    exit_code = result.get("observation", {}).get("exit_code", -1)
    if exit_code != 0:
        stderr = result.get("observation", {}).get("stderr", "")
        return f"Exit code {exit_code}\n{output}\n{stderr}".strip()
    return output if output else "(no output)"


def _execute_shell(arguments: dict) -> str:
    command = arguments.get("command", "")
    cid = _ensure_conversation()

    result = _http_request("POST", f"/api/conversations/{cid}/actions", {
        "action": "CmdRunAction",
        "args": {"command": command},
    })

    output = result.get("observation", {}).get("content", "")
    exit_code = result.get("observation", {}).get("exit_code", -1)
    if exit_code != 0:
        stderr = result.get("observation", {}).get("stderr", "")
        return f"Exit code {exit_code}\n{output}\n{stderr}".strip()
    return output if output else "(no output)"


def _read_file(arguments: dict) -> str:
    path = arguments.get("path", "")
    cid = _ensure_conversation()

    result = _http_request("GET", f"/api/conversations/{cid}/files?path={path}")
    return result.get("content", result.get("data", ""))


def _write_file(arguments: dict) -> str:
    path = arguments.get("path", "")
    content = arguments.get("content", "")
    cid = _ensure_conversation()

    _http_request("PUT", f"/api/conversations/{cid}/files", {
        "path": path,
        "content": content,
    })
    return f"Written to {path}"


_TOOL_HANDLERS = {
    "execute_code": _execute_code,
    "execute_shell": _execute_shell,
    "read_file": _read_file,
    "write_file": _write_file,
}


# ── MCP JSON-RPC handler ──


def handle_request(request: dict) -> dict | None:
    """Process a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "openhands", "version": "1.0.0"},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        handler = _TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }

        try:
            result_text = handler(arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(result_text)}],
                },
            }
        except RuntimeError as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True,
                },
            }

    # Notifications (no id) — no response needed
    if req_id is None:
        return None

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    """Main loop — read stdin line by line, respond to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
