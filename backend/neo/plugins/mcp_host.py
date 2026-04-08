"""MCP Plugin Host — Discover, manage, and execute MCP tool plugins.

Supports **two transport modes**:

* **stdio** — local subprocess plugins discovered from ``~/.neo/plugins/``
* **SSE / streamable HTTP** — remote MCP servers listed in ``~/.neo/remotes.json``

Both modes use the official ``mcp`` Python SDK ``ClientSession`` for the
underlying MCP protocol, providing a unified ``call_tool()`` interface.

Lifecycle:
    1. discover()       — scan local plugin dir + remotes.json
    2. start_plugin()   — connect via the appropriate transport
    3. call_tool()      — route tool invocations through MCP protocol
    4. stop_plugin()    — gracefully disconnect
"""

import asyncio
import json
import logging
import re
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from neo.plugins.remotes import load_remotes
from neo.plugins.transports import (
    RemoteConfig,
    StdioConfig,
    TransportType,
    connect,
)

logger = logging.getLogger(__name__)

# Default plugin directory
_DEFAULT_PLUGIN_DIR = Path.home() / ".neo" / "plugins"
_DEFAULT_REMOTES_PATH = Path.home() / ".neo" / "remotes.json"

# Allowed plugin commands for stdio (security: prevents arbitrary binary execution)
_ALLOWED_COMMANDS = frozenset({
    "python", "python3", "node", "deno", "bun", "npx",
    "ruby", "perl", "java", "dotnet",
})

# Plugin name validation (alphanumeric + hyphens only)
_PLUGIN_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _resolve_stdio_env(descriptor_env: dict[str, str]) -> dict[str, str]:
    """Build the environment for a stdio subprocess.

    1. Start with the parent process environment (so PATH, HOME, etc. are available).
    2. Overlay explicit env vars from the plugin descriptor.
    3. Resolve ``$SECRET_NAME`` references from ``~/.neo/secrets.json``.
    """
    import os

    env = os.environ.copy()

    if not descriptor_env:
        return env

    try:
        from neo.plugins.secrets import get_secret
    except ImportError:
        get_secret = None  # type: ignore[assignment]

    for key, value in descriptor_env.items():
        if isinstance(value, str) and value.startswith("$"):
            # Resolve from secrets.json, then fall back to existing env
            secret_name = value[1:]
            resolved = None
            if get_secret is not None:
                resolved = get_secret(secret_name)
            if not resolved:
                resolved = os.environ.get(secret_name, "")
            env[key] = resolved
        else:
            env[key] = value

    return env


# ---------------------------------------------------------------------------
# Plugin Descriptor
# ---------------------------------------------------------------------------


class PluginDescriptor:
    """Parsed plugin descriptor — supports both local and remote servers."""

    def __init__(self, path: Path | None, data: dict) -> None:
        self.path = path  # None for remote servers
        self.name: str = data["name"]
        self.version: str = data.get("version", "0.0.0")
        self.description: str = data.get("description", "")

        # Transport type (backward compatible: defaults to "stdio")
        self.transport: str = data.get("transport", "stdio")

        # Stdio-specific fields
        self.command: str | None = data.get("command")
        self.args: list[str] = data.get("args", [])
        self.env: dict[str, str] = data.get("env", {})

        # Remote-specific fields
        self.url: str | None = data.get("url")
        self.auth: dict | None = data.get("auth")

        # Tool cache (from descriptor or live query)
        self.tools: list[dict] = data.get("tools", [])

    def to_dict(self) -> dict:
        """Public-facing representation — excludes command/args for security."""
        d: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tools": self.tools,
            "transport": self.transport,
        }
        if self.url:
            d["url"] = self.url
        return d


# ---------------------------------------------------------------------------
# MCP Connection — wraps a ClientSession
# ---------------------------------------------------------------------------


class MCPConnection:
    """A live connection to an MCP server (local or remote)."""

    def __init__(self, descriptor: PluginDescriptor) -> None:
        self.descriptor = descriptor
        self._session: Any = None  # ClientSession
        self._exit_stack: AsyncExitStack | None = None
        self._status: str = "disconnected"
        self._cached_tools: list[dict] = list(descriptor.tools)

    @property
    def connected(self) -> bool:
        return self._status == "connected"

    @property
    def status(self) -> str:
        return self._status

    async def connect(self) -> None:
        """Connect using the transport defined in the descriptor."""
        self._status = "connecting"
        self._exit_stack = AsyncExitStack()

        try:
            transport_type = TransportType(self.descriptor.transport)
        except ValueError:
            self._status = "error"
            raise ValueError(f"Unknown transport: {self.descriptor.transport}")

        try:
            if transport_type == TransportType.STDIO:
                if not self.descriptor.command:
                    raise ValueError("stdio plugins require a 'command' field")
                resolved_env = _resolve_stdio_env(self.descriptor.env)
                stdio_config = StdioConfig(
                    command=self.descriptor.command,
                    args=self.descriptor.args,
                    env=resolved_env,
                    cwd=str(self.descriptor.path.parent) if self.descriptor.path else None,
                )
                self._session = await connect(
                    transport_type,
                    stdio_config=stdio_config,
                    exit_stack=self._exit_stack,
                )
            else:
                if not self.descriptor.url:
                    raise ValueError("Remote plugins require a 'url' field")
                auth = self.descriptor.auth or {}
                remote_config = RemoteConfig(
                    url=self.descriptor.url,
                    auth_type=auth.get("type"),
                    token_env=auth.get("token_env"),
                    headers=auth.get("headers", {}),
                )
                self._session = await connect(
                    transport_type,
                    remote_config=remote_config,
                    exit_stack=self._exit_stack,
                )

            # Fetch tools from the live session
            tools_result = await self._session.list_tools()
            self._cached_tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
                }
                for t in tools_result.tools
            ]
            self.descriptor.tools = self._cached_tools
            self._status = "connected"
            logger.info(
                "Connected to '%s' via %s (%d tools)",
                self.descriptor.name, self.descriptor.transport, len(self._cached_tools),
            )

        except Exception:
            self._status = "error"
            if self._exit_stack:
                await self._exit_stack.aclose()
                self._exit_stack = None
            raise

    async def disconnect(self) -> None:
        """Gracefully close the connection."""
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                logger.debug("Error closing connection to '%s'", self.descriptor.name, exc_info=True)
            finally:
                self._exit_stack = None
                self._session = None
                self._status = "disconnected"

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool via the MCP session.

        Attempts one reconnect on connection failure before raising.
        """
        if not self.connected or self._session is None:
            raise RuntimeError(f"Plugin '{self.descriptor.name}' is not connected")

        try:
            result = await self._session.call_tool(tool_name, arguments)
        except Exception as first_err:
            # Attempt one reconnect
            logger.warning(
                "Tool call failed for '%s::%s', attempting reconnect: %s",
                self.descriptor.name, tool_name, first_err,
            )
            try:
                await self.disconnect()
                await self.connect()
                result = await self._session.call_tool(tool_name, arguments)
            except Exception as retry_err:
                self._status = "error"
                raise RuntimeError(
                    f"Plugin '{self.descriptor.name}' tool '{tool_name}' failed after reconnect: {retry_err}"
                ) from retry_err

        # Extract text from content items
        texts = []
        for item in result.content:
            if hasattr(item, "text"):
                texts.append(item.text)
        return "\n".join(texts) if texts else json.dumps({"isError": result.isError})

    async def refresh_tools(self) -> list[dict]:
        """Re-query tools from the server."""
        if not self.connected or self._session is None:
            return self._cached_tools

        tools_result = await self._session.list_tools()
        self._cached_tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
            }
            for t in tools_result.tools
        ]
        self.descriptor.tools = self._cached_tools
        return self._cached_tools

    def get_tools(self) -> list[dict]:
        """Return cached tools (synchronous)."""
        return self._cached_tools


# ---------------------------------------------------------------------------
# Watchdog handler for hot-reload
# ---------------------------------------------------------------------------


class _PluginDirHandler(FileSystemEventHandler):
    """Watchdog handler that triggers plugin re-discovery on new files."""

    def __init__(self, host: "MCPHost") -> None:
        super().__init__()
        self._host = host

    def on_created(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        if Path(event.src_path).name == "descriptor.json":
            logger.info("New plugin descriptor detected: %s", event.src_path)
            try:
                self._host._rediscover()
            except Exception:
                logger.exception("Error during plugin re-discovery")


# ---------------------------------------------------------------------------
# MCP Host
# ---------------------------------------------------------------------------


class MCPHost:
    """Central plugin host — discovers, starts, stops, and routes tool calls.

    Supports both local stdio plugins and remote MCP servers.

    Usage::

        host = MCPHost()
        host.discover()
        await host.start_plugin("weather")
        result = await host.call_tool("weather", "get_weather", {"city": "NYC"})
        await host.stop_plugin("weather")
    """

    def __init__(
        self,
        plugin_dir: Path | None = None,
        remotes_path: Path | None = None,
    ) -> None:
        self._plugin_dir = plugin_dir or _DEFAULT_PLUGIN_DIR
        self._remotes_path = remotes_path or _DEFAULT_REMOTES_PATH
        self._descriptors: dict[str, PluginDescriptor] = {}
        self._connections: dict[str, MCPConnection] = {}
        self._lock = asyncio.Lock()
        self._observer: Observer | None = None
        self._health_task: asyncio.Task | None = None

    @property
    def plugin_dir(self) -> Path:
        return self._plugin_dir

    # ------------------------------------------------------------------
    # Discovery (synchronous — file I/O only)
    # ------------------------------------------------------------------

    def discover(self) -> list[PluginDescriptor]:
        """Scan local plugin directory + remotes.json for all servers.

        Returns list of all discovered plugin descriptors.
        """
        discovered: list[PluginDescriptor] = []

        # 1. Local stdio plugins
        discovered.extend(self._discover_local())

        # 2. Remote servers from remotes.json
        discovered.extend(self._discover_remotes())

        return discovered

    def _discover_local(self) -> list[PluginDescriptor]:
        """Scan ``~/.neo/plugins/`` for local stdio plugin descriptors."""
        self._plugin_dir.mkdir(parents=True, exist_ok=True)
        discovered: list[PluginDescriptor] = []

        for entry in self._plugin_dir.iterdir():
            if not entry.is_dir():
                continue

            descriptor_path = entry / "descriptor.json"
            if not descriptor_path.exists():
                continue

            try:
                data = json.loads(descriptor_path.read_text())
                if "name" not in data or "command" not in data:
                    logger.warning("Invalid descriptor at %s: missing name or command", descriptor_path)
                    continue

                if not _PLUGIN_NAME_RE.match(data["name"]):
                    logger.warning("Invalid plugin name %r at %s", data["name"], descriptor_path)
                    continue

                # S1: Validate command against allowlist
                base_cmd = Path(data["command"]).name
                if base_cmd not in _ALLOWED_COMMANDS:
                    logger.warning(
                        "Plugin %r uses disallowed command %r (allowed: %s)",
                        data["name"], data["command"], ", ".join(sorted(_ALLOWED_COMMANDS)),
                    )
                    continue

                # Default transport to stdio for local plugins
                data.setdefault("transport", "stdio")

                desc = PluginDescriptor(descriptor_path, data)
                self._descriptors[desc.name] = desc
                discovered.append(desc)
                logger.info("Discovered local plugin: %s v%s", desc.name, desc.version)
            except (json.JSONDecodeError, KeyError):
                logger.exception("Failed to parse descriptor at %s", descriptor_path)

        return discovered

    def _discover_remotes(self) -> list[PluginDescriptor]:
        """Load remote server descriptors from ``~/.neo/remotes.json``."""
        discovered: list[PluginDescriptor] = []
        remotes = load_remotes(self._remotes_path)

        for remote in remotes:
            name = remote.get("name", "")
            if not name:
                continue

            if not _PLUGIN_NAME_RE.match(name):
                logger.warning("Invalid remote server name: %r", name)
                continue

            if name in self._descriptors:
                logger.debug("Skipping duplicate remote '%s' (already discovered)", name)
                continue

            desc = PluginDescriptor(None, remote)
            self._descriptors[desc.name] = desc
            discovered.append(desc)
            logger.info("Discovered remote server: %s (%s)", desc.name, desc.transport)

        return discovered

    # ------------------------------------------------------------------
    # Plugin lifecycle (async)
    # ------------------------------------------------------------------

    def list_plugins(self) -> list[dict]:
        """Return all known plugins with their status."""
        plugins = []
        for name, desc in self._descriptors.items():
            conn = self._connections.get(name)
            plugins.append({
                **desc.to_dict(),
                "status": conn.status if conn else "stopped",
            })
        return plugins

    async def start_plugin(self, name: str) -> bool:
        """Connect to a plugin by name. Returns True on success."""
        desc = self._descriptors.get(name)
        if desc is None:
            logger.error("Plugin not found: %s", name)
            return False

        async with self._lock:
            existing = self._connections.get(name)
            if existing and existing.connected:
                return True  # Already connected

            conn = MCPConnection(desc)
            try:
                await conn.connect()
                self._connections[name] = conn
                return True
            except Exception:
                logger.exception("Failed to start plugin '%s'", name)
                return False

    async def stop_plugin(self, name: str) -> bool:
        """Disconnect from a plugin. Returns True if stopped."""
        async with self._lock:
            conn = self._connections.get(name)
            if conn is None or not conn.connected:
                return False

            await conn.disconnect()
            return True

    async def remove_plugin(self, name: str) -> bool:
        """Disconnect and unregister a plugin."""
        await self.stop_plugin(name)
        async with self._lock:
            if name in self._descriptors:
                del self._descriptors[name]
                self._connections.pop(name, None)
                return True
            return False

    async def call_tool(self, plugin_name: str, tool_name: str, arguments: dict) -> str:
        """Execute a tool on a specific plugin."""
        conn = self._connections.get(plugin_name)
        if conn is None or not conn.connected:
            raise RuntimeError(f"Plugin '{plugin_name}' is not connected")

        return await conn.call_tool(tool_name, arguments)

    async def refresh_tools(self, name: str) -> list[dict]:
        """Re-query tools from a running plugin."""
        conn = self._connections.get(name)
        if conn is None or not conn.connected:
            raise RuntimeError(f"Plugin '{name}' is not connected")
        return await conn.refresh_tools()

    def get_plugin_tools(self, name: str) -> list[dict]:
        """Get tool definitions from a plugin (synchronous)."""
        conn = self._connections.get(name)
        if conn and conn.connected:
            return conn.get_tools()

        desc = self._descriptors.get(name)
        if desc:
            return desc.tools
        return []

    def get_all_tool_names(self) -> list[str]:
        """Get all tool names across all connected plugins, prefixed."""
        tools = []
        for name, conn in self._connections.items():
            if conn.connected:
                for tool in conn.get_tools():
                    tool_name = tool.get("name", "")
                    if tool_name:
                        tools.append(f"plugin::{name}::{tool_name}")
        return tools

    # ------------------------------------------------------------------
    # Auto-connect remotes on startup
    # ------------------------------------------------------------------

    async def auto_connect_remotes(self) -> int:
        """Connect to all remote servers that have auth configured.

        Called during server startup. Errors are logged per-server but
        do not prevent other servers from connecting.

        Returns the number of successfully connected servers.
        """
        connected_count = 0
        for name, desc in list(self._descriptors.items()):
            if desc.transport == "stdio":
                continue
            # Only auto-connect if auth is configured (has a token_env)
            auth = desc.auth or {}
            if not auth.get("token_env"):
                continue
            try:
                ok = await self.start_plugin(name)
                if ok:
                    connected_count += 1
                    logger.info("Auto-connected remote server: %s", name)
                else:
                    logger.warning("Auto-connect failed for '%s'", name)
            except Exception:
                logger.warning("Auto-connect error for '%s'", name, exc_info=True)

        if connected_count:
            logger.info("Auto-connected %d remote server(s)", connected_count)
        return connected_count

    # ------------------------------------------------------------------
    # Remote server management
    # ------------------------------------------------------------------

    async def add_remote(
        self,
        name: str,
        url: str,
        transport: str = "streamable_http",
        auth: dict | None = None,
        description: str = "",
    ) -> bool:
        """Add a new remote MCP server and connect to it.

        Also persists the configuration to ``~/.neo/remotes.json``.
        """
        from neo.plugins.remotes import add_remote as _add_remote

        config = {
            "name": name,
            "transport": transport,
            "url": url,
            "description": description,
        }
        if auth:
            config["auth"] = auth

        _add_remote(config, self._remotes_path)

        # Register and connect
        desc = PluginDescriptor(None, config)
        self._descriptors[desc.name] = desc
        return await self.start_plugin(name)

    async def remove_remote(self, name: str) -> bool:
        """Disconnect from and remove a remote server."""
        from neo.plugins.remotes import remove_remote as _remove_remote

        await self.stop_plugin(name)
        async with self._lock:
            self._descriptors.pop(name, None)
            self._connections.pop(name, None)
        return _remove_remote(name, self._remotes_path)

    # ------------------------------------------------------------------
    # Health check for remote connections
    # ------------------------------------------------------------------

    async def start_health_checker(self) -> None:
        """Start a background task that checks remote connections."""
        self._health_task = asyncio.create_task(self._health_check_loop())

    async def _health_check_loop(self) -> None:
        """Background health check — every 60s, reconnect dropped remotes."""
        while True:
            await asyncio.sleep(60)
            for name, conn in list(self._connections.items()):
                if conn.descriptor.transport != "stdio" and conn.status == "error":
                    logger.info("Health check: reconnecting '%s'", name)
                    try:
                        await conn.disconnect()
                        await conn.connect()
                    except Exception:
                        logger.debug("Health check reconnect failed for '%s'", name, exc_info=True)

    # ------------------------------------------------------------------
    # Hot-reload: file watcher for plugin directory
    # ------------------------------------------------------------------

    def start_watching(self) -> None:
        """Start watching the plugin directory for new plugins."""
        if self._observer is not None:
            return

        self._plugin_dir.mkdir(parents=True, exist_ok=True)

        handler = _PluginDirHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._plugin_dir), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        logger.info("Plugin directory watcher started: %s", self._plugin_dir)

    def stop_watching(self) -> None:
        """Stop the plugin directory watcher."""
        if self._observer is None:
            return

        self._observer.stop()
        self._observer.join(timeout=5)
        self._observer = None
        logger.info("Plugin directory watcher stopped")

    def _rediscover(self) -> None:
        """Re-scan plugin directory and register any new local plugins."""
        self._plugin_dir.mkdir(parents=True, exist_ok=True)

        for entry in self._plugin_dir.iterdir():
            if not entry.is_dir():
                continue

            descriptor_path = entry / "descriptor.json"
            if not descriptor_path.exists():
                continue

            try:
                data = json.loads(descriptor_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            name = data.get("name", "")
            if not name or name in self._descriptors:
                continue

            if "command" not in data:
                continue

            if not _PLUGIN_NAME_RE.match(name):
                continue

            base_cmd = Path(data["command"]).name
            if base_cmd not in _ALLOWED_COMMANDS:
                continue

            data.setdefault("transport", "stdio")
            desc = PluginDescriptor(descriptor_path, data)
            self._descriptors[desc.name] = desc
            logger.info("Hot-reload: discovered new plugin %s v%s", desc.name, desc.version)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Stop all connections, health checker, and file watcher."""
        # Cancel health check
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        # Stop file watcher
        self.stop_watching()

        # Disconnect all plugins
        for name in list(self._connections.keys()):
            try:
                await self.stop_plugin(name)
            except Exception:
                logger.debug("Error stopping plugin '%s'", name, exc_info=True)

        logger.info("All plugins shut down")
