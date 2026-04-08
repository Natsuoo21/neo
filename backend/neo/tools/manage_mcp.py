"""Manage MCP servers — list, connect, disconnect, add, and remove via chat.

This tool is dispatched specially by the orchestrator because it requires
async access to the global ``MCPHost`` instance.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neo.plugins.mcp_host import MCPHost

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"list", "connect", "disconnect", "add", "remove"}


async def manage_mcp(
    host: "MCPHost",
    action: str,
    name: str = "",
    url: str = "",
    transport: str = "streamable_http",
    auth_type: str = "",
    token_env: str = "",
    token_value: str = "",
) -> str:
    """Manage MCP servers.

    Args:
        host: The active MCPHost instance (injected by the orchestrator).
        action: One of ``list``, ``connect``, ``disconnect``, ``add``, ``remove``.
        name: Server name (required for all actions except ``list``).
        url: Server URL (required for ``add``).
        transport: Transport type — ``streamable_http`` or ``sse`` (for ``add``).
        auth_type: Auth type — ``bearer`` or ``api_key`` (for ``add``).
        token_env: Environment variable name for the token (for ``add``).
        token_value: Actual token/API key value to save (for ``add``).

    Returns:
        Human-readable result string.
    """
    action = action.strip().lower()
    if action not in _VALID_ACTIONS:
        raise ValueError(
            f"Invalid action '{action}'. Must be one of: {', '.join(sorted(_VALID_ACTIONS))}"
        )

    if action == "list":
        return _format_list(host)

    if not name:
        raise ValueError(f"'name' is required for action '{action}'.")

    if action == "connect":
        return await _connect(host, name)

    if action == "disconnect":
        return await _disconnect(host, name)

    if action == "add":
        return await _add(host, name, url, transport, auth_type, token_env, token_value)

    if action == "remove":
        return await _remove(host, name)

    raise ValueError(f"Unhandled action: {action}")


# ---------------------------------------------------------------------------
# Action implementations
# ---------------------------------------------------------------------------


def _format_list(host: "MCPHost") -> str:
    """List all known MCP servers with their status."""
    plugins = host.list_plugins()
    if not plugins:
        return "No MCP servers or plugins discovered. Add a remote server or place plugins in ~/.neo/plugins/."

    lines = []
    for p in plugins:
        status = p.get("status", "stopped")
        transport = p.get("transport", "stdio")
        name = p.get("name", "?")
        tool_count = len(p.get("tools", []))
        url = p.get("url", "")

        icon = "🌐" if transport != "stdio" else "💻"
        status_icon = {"running": "✅", "connected": "✅", "connecting": "🔄", "error": "❌"}.get(status, "⏹️")

        line = f"{icon} **{name}** — {status_icon} {status} | {transport}"
        if url:
            line += f" | {url}"
        if tool_count:
            line += f" | {tool_count} tools"
        lines.append(line)

    return f"**MCP Servers ({len(plugins)}):**\n" + "\n".join(lines)


async def _connect(host: "MCPHost", name: str) -> str:
    """Connect to an existing server by name."""
    # Check if it exists
    plugins = {p["name"]: p for p in host.list_plugins()}
    if name not in plugins:
        available = ", ".join(sorted(plugins.keys())) if plugins else "none"
        raise ValueError(f"Server '{name}' not found. Available: {available}")

    plugin = plugins[name]
    if plugin["status"] in ("running", "connected"):
        return f"Server '{name}' is already connected."

    ok = await host.start_plugin(name)
    if ok:
        return f"Successfully connected to '{name}'."
    else:
        raise RuntimeError(f"Failed to connect to '{name}'. Check the server URL and credentials.")


async def _disconnect(host: "MCPHost", name: str) -> str:
    """Disconnect from a server."""
    ok = await host.stop_plugin(name)
    if ok:
        return f"Disconnected from '{name}'."
    else:
        return f"Server '{name}' was not connected."


async def _add(
    host: "MCPHost",
    name: str,
    url: str,
    transport: str,
    auth_type: str,
    token_env: str,
    token_value: str,
) -> str:
    """Add a new remote MCP server and connect to it."""
    if not url:
        raise ValueError("'url' is required to add a remote MCP server.")

    if transport not in ("streamable_http", "sse"):
        raise ValueError(f"Invalid transport '{transport}'. Use 'streamable_http' or 'sse'.")

    # Save token if provided
    if token_value and token_env:
        from neo.plugins.secrets import set_secret
        set_secret(token_env, token_value)

    auth = None
    if auth_type:
        auth = {"type": auth_type}
        if token_env:
            auth["token_env"] = token_env

    ok = await host.add_remote(
        name=name,
        url=url,
        transport=transport,
        auth=auth,
    )

    if ok:
        tools = host.get_plugin_tools(name)
        return (
            f"Added and connected to '{name}' ({transport}).\n"
            f"URL: {url}\n"
            f"Tools available: {len(tools)}"
        )
    else:
        return f"Added '{name}' but failed to connect. You can try connecting later."


async def _remove(host: "MCPHost", name: str) -> str:
    """Remove a remote MCP server."""
    ok = await host.remove_remote(name)
    if ok:
        return f"Removed remote server '{name}'."
    else:
        raise ValueError(f"Remote server '{name}' not found.")
