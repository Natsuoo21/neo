"""MCP Plugin Host — Discover, manage, and execute MCP tool plugins.

Scans ~/.neo/plugins/ for descriptor.json files that declare MCP-compatible
tool servers.  Each plugin runs as a subprocess communicating over stdio
using the Model Context Protocol (MCP).

Lifecycle:
    1. discover()   — scan plugin dir for descriptors
    2. start(name)  — launch subprocess, perform MCP initialize handshake
    3. call_tool()  — route tool invocations through MCP protocol
    4. stop(name)   — gracefully shut down a plugin subprocess
"""

import json
import logging
import os
import re
import select
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# Default plugin directory
_DEFAULT_PLUGIN_DIR = Path.home() / ".neo" / "plugins"

# Allowed plugin commands (security: prevents arbitrary binary execution)
_ALLOWED_COMMANDS = frozenset({
    "python", "python3", "node", "deno", "bun", "npx",
    "ruby", "perl", "java", "dotnet",
})

# Plugin name validation (alphanumeric + hyphens only)
_PLUGIN_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


class PluginDescriptor:
    """Parsed descriptor.json for an MCP plugin."""

    def __init__(self, path: Path, data: dict) -> None:
        self.path = path
        self.name: str = data["name"]
        self.version: str = data.get("version", "0.0.0")
        self.description: str = data.get("description", "")
        self.command: str = data["command"]
        self.args: list[str] = data.get("args", [])
        self.env: dict[str, str] = data.get("env", {})
        self.tools: list[dict] = data.get("tools", [])

    def to_dict(self) -> dict:
        """Public-facing representation — excludes command/args for security."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tools": self.tools,
        }


class PluginProcess:
    """Running MCP plugin subprocess."""

    def __init__(self, descriptor: PluginDescriptor) -> None:
        self.descriptor = descriptor
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._stderr_thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        """Launch the plugin subprocess and perform MCP initialize."""
        if self.running:
            return

        # S2: Only allow PLUGIN_* prefixed env vars from descriptor
        safe_env = {
            k: v for k, v in self.descriptor.env.items()
            if k.startswith("PLUGIN_")
        }
        env = {**os.environ, **safe_env}
        plugin_dir = str(self.descriptor.path.parent)

        # S1: Resolve command to absolute path via allowlist
        cmd = self.descriptor.command
        resolved = shutil.which(cmd)
        if resolved is None:
            raise FileNotFoundError(f"Plugin command not found in PATH: {cmd!r}")

        self.process = subprocess.Popen(
            [resolved, *self.descriptor.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=plugin_dir,
            env=env,
            text=True,
            bufsize=1,
        )

        # I3: Drain stderr in background to prevent 64KB pipe deadlock
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True,
        )
        self._stderr_thread.start()

        # MCP initialize handshake
        response = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "neo", "version": "0.1.0"},
        })

        if response and response.get("protocolVersion"):
            # Send initialized notification
            self._send_notification("notifications/initialized", {})
            logger.info("Plugin '%s' initialized (MCP %s)", self.descriptor.name, response["protocolVersion"])
        else:
            logger.warning("Plugin '%s' initialize handshake failed", self.descriptor.name)

    def stop(self) -> None:
        """Gracefully shut down the plugin subprocess."""
        if not self.running or self.process is None:
            return

        try:
            self._send_notification("notifications/cancelled", {"reason": "shutdown"})
            self.process.stdin.close()  # type: ignore[union-attr]
            self.process.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            self.process.kill()
        finally:
            self.process = None

    def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Execute a tool call via MCP protocol."""
        if not self.running:
            raise RuntimeError(f"Plugin '{self.descriptor.name}' is not running")

        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        if result is None:
            raise RuntimeError(f"No response from plugin '{self.descriptor.name}' for tool '{tool_name}'")

        # MCP returns content array
        content_items = result.get("content", [])
        texts = [item.get("text", "") for item in content_items if item.get("type") == "text"]
        return "\n".join(texts) if texts else json.dumps(result)

    def list_tools(self) -> list[dict]:
        """Query available tools from the running plugin."""
        if not self.running:
            return self.descriptor.tools

        result = self._send_request("tools/list", {})
        if result and "tools" in result:
            return result["tools"]
        return self.descriptor.tools

    def _send_request(self, method: str, params: dict, timeout: float = 30.0) -> dict | None:
        """Send a JSON-RPC request and read the response.

        Args:
            timeout: Max seconds to wait for a response (prevents blocking forever).
        """
        if not self.running or self.process is None:
            return None

        with self._lock:
            self._request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params,
            }

            try:
                line = json.dumps(request) + "\n"
                self.process.stdin.write(line)  # type: ignore[union-attr]
                self.process.stdin.flush()  # type: ignore[union-attr]

                # I2: Wait with timeout to prevent blocking forever
                stdout_fd = self.process.stdout.fileno()  # type: ignore[union-attr]
                ready, _, _ = select.select([stdout_fd], [], [], timeout)
                if not ready:
                    logger.warning("Plugin '%s' timed out after %.1fs", self.descriptor.name, timeout)
                    return None

                response_line = self.process.stdout.readline()  # type: ignore[union-attr]
                if not response_line:
                    return None

                response = json.loads(response_line.strip())
                return response.get("result")
            except (json.JSONDecodeError, OSError, BrokenPipeError):
                logger.exception("MCP communication error with plugin '%s'", self.descriptor.name)
                return None

    def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self.running or self.process is None:
            return

        with self._lock:
            notification = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
            try:
                line = json.dumps(notification) + "\n"
                self.process.stdin.write(line)  # type: ignore[union-attr]
                self.process.stdin.flush()  # type: ignore[union-attr]
            except (OSError, BrokenPipeError):
                pass

    def _drain_stderr(self) -> None:
        """Read and log stderr lines to prevent pipe buffer deadlock."""
        if self.process is None or self.process.stderr is None:
            return
        try:
            for line in self.process.stderr:
                line = line.rstrip()
                if line:
                    logger.debug("Plugin '%s' stderr: %s", self.descriptor.name, line)
        except (OSError, ValueError):
            pass


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


class MCPHost:
    """Central plugin host — discovers, starts, stops, and routes tool calls.

    Usage::

        host = MCPHost()
        host.discover()
        host.start_plugin("weather")
        result = host.call_tool("weather", "get_weather", {"city": "NYC"})
        host.stop_plugin("weather")
    """

    def __init__(self, plugin_dir: Path | None = None) -> None:
        self._plugin_dir = plugin_dir or _DEFAULT_PLUGIN_DIR
        self._descriptors: dict[str, PluginDescriptor] = {}
        self._processes: dict[str, PluginProcess] = {}
        self._lock = threading.Lock()
        self._observer: Observer | None = None

    @property
    def plugin_dir(self) -> Path:
        return self._plugin_dir

    def discover(self) -> list[PluginDescriptor]:
        """Scan plugin directory for descriptor.json files.

        Returns list of discovered plugin descriptors.
        """
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

                # Validate plugin name (BP9: alphanumeric + hyphens)
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

                desc = PluginDescriptor(descriptor_path, data)
                self._descriptors[desc.name] = desc
                discovered.append(desc)
                logger.info("Discovered plugin: %s v%s", desc.name, desc.version)
            except (json.JSONDecodeError, KeyError):
                logger.exception("Failed to parse descriptor at %s", descriptor_path)

        return discovered

    def list_plugins(self) -> list[dict]:
        """Return all known plugins with their status."""
        plugins = []
        for name, desc in self._descriptors.items():
            proc = self._processes.get(name)
            plugins.append({
                **desc.to_dict(),
                "status": "running" if (proc and proc.running) else "stopped",
            })
        return plugins

    def start_plugin(self, name: str) -> bool:
        """Start a plugin by name. Returns True on success."""
        desc = self._descriptors.get(name)
        if desc is None:
            logger.error("Plugin not found: %s", name)
            return False

        with self._lock:
            if name in self._processes and self._processes[name].running:
                return True  # Already running

            proc = PluginProcess(desc)
            try:
                proc.start()
                self._processes[name] = proc
                return True
            except (OSError, FileNotFoundError):
                logger.exception("Failed to start plugin '%s'", name)
                return False

    def stop_plugin(self, name: str) -> bool:
        """Stop a running plugin. Returns True if stopped."""
        with self._lock:
            proc = self._processes.get(name)
            if proc is None or not proc.running:
                return False

            proc.stop()
            return True

    def remove_plugin(self, name: str) -> bool:
        """Stop and unregister a plugin."""
        self.stop_plugin(name)
        with self._lock:
            if name in self._descriptors:
                del self._descriptors[name]
                self._processes.pop(name, None)
                return True
            return False

    def call_tool(self, plugin_name: str, tool_name: str, arguments: dict) -> str:
        """Execute a tool on a specific plugin."""
        proc = self._processes.get(plugin_name)
        if proc is None or not proc.running:
            raise RuntimeError(f"Plugin '{plugin_name}' is not running")

        result = proc.call_tool(tool_name, arguments)
        return str(result)

    def get_plugin_tools(self, name: str) -> list[dict]:
        """Get tool definitions from a plugin."""
        proc = self._processes.get(name)
        if proc and proc.running:
            return proc.list_tools()

        desc = self._descriptors.get(name)
        if desc:
            return desc.tools
        return []

    def get_all_tool_names(self) -> list[str]:
        """Get all tool names across all running plugins, prefixed with plugin name."""
        tools = []
        for name, proc in self._processes.items():
            if proc.running:
                for tool in proc.list_tools():
                    tool_name = tool.get("name", "")
                    if tool_name:
                        tools.append(f"plugin::{name}::{tool_name}")
        return tools

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
        """Re-scan plugin directory and register any new plugins."""
        self._plugin_dir.mkdir(parents=True, exist_ok=True)

        for entry in self._plugin_dir.iterdir():
            if not entry.is_dir():
                continue

            descriptor_path = entry / "descriptor.json"
            if not descriptor_path.exists():
                continue

            # Skip already-known plugins
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

            desc = PluginDescriptor(descriptor_path, data)
            self._descriptors[desc.name] = desc
            logger.info("Hot-reload: discovered new plugin %s v%s", desc.name, desc.version)

    def shutdown(self) -> None:
        """Stop all running plugins and the file watcher."""
        self.stop_watching()
        for name in list(self._processes.keys()):
            self.stop_plugin(name)
        logger.info("All plugins shut down")
