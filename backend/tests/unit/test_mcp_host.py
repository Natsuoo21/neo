"""Tests for neo.plugins.mcp_host — MCP plugin host (async, SDK-based)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from neo.plugins.mcp_host import (
    _ALLOWED_COMMANDS,
    _PLUGIN_NAME_RE,
    MCPConnection,
    MCPHost,
    PluginDescriptor,
)

# ---------------------------------------------------------------------------
# PluginDescriptor
# ---------------------------------------------------------------------------


class TestPluginDescriptor:
    def test_parse_minimal_stdio(self):
        data = {"name": "test", "command": "python", "args": ["main.py"]}
        desc = PluginDescriptor(Path("/tmp/test/descriptor.json"), data)
        assert desc.name == "test"
        assert desc.command == "python"
        assert desc.args == ["main.py"]
        assert desc.version == "0.0.0"
        assert desc.description == ""
        assert desc.tools == []
        assert desc.env == {}
        assert desc.transport == "stdio"

    def test_parse_remote(self):
        data = {
            "name": "remote-server",
            "transport": "streamable_http",
            "url": "https://api.example.com/mcp",
            "auth": {"type": "bearer", "token_env": "MY_TOKEN"},
        }
        desc = PluginDescriptor(None, data)
        assert desc.name == "remote-server"
        assert desc.transport == "streamable_http"
        assert desc.url == "https://api.example.com/mcp"
        assert desc.auth == {"type": "bearer", "token_env": "MY_TOKEN"}
        assert desc.path is None
        assert desc.command is None

    def test_to_dict_hides_command(self):
        data = {"name": "test", "command": "python", "args": ["server.py"]}
        desc = PluginDescriptor(Path("/p"), data)
        d = desc.to_dict()
        assert d["name"] == "test"
        assert "command" not in d
        assert "args" not in d
        assert d["transport"] == "stdio"

    def test_to_dict_includes_url_for_remote(self):
        data = {
            "name": "remote",
            "transport": "sse",
            "url": "https://example.com/sse",
        }
        desc = PluginDescriptor(None, data)
        d = desc.to_dict()
        assert d["url"] == "https://example.com/sse"
        assert d["transport"] == "sse"

    def test_backward_compat_defaults_to_stdio(self):
        data = {"name": "old-plugin", "command": "python"}
        desc = PluginDescriptor(Path("/p"), data)
        assert desc.transport == "stdio"


# ---------------------------------------------------------------------------
# MCPConnection
# ---------------------------------------------------------------------------


class TestMCPConnection:
    def _make_descriptor(self, **overrides) -> PluginDescriptor:
        data = {"name": "test", "command": "python", "transport": "stdio", **overrides}
        return PluginDescriptor(Path("/tmp/test/descriptor.json"), data)

    def test_initial_status(self):
        conn = MCPConnection(self._make_descriptor())
        assert conn.status == "disconnected"
        assert conn.connected is False

    def test_get_tools_from_cache(self):
        desc = self._make_descriptor(tools=[{"name": "tool1"}])
        conn = MCPConnection(desc)
        assert conn.get_tools() == [{"name": "tool1"}]

    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self):
        conn = MCPConnection(self._make_descriptor())
        with pytest.raises(RuntimeError, match="not connected"):
            await conn.call_tool("test", {})

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        conn = MCPConnection(self._make_descriptor())
        await conn.disconnect()  # Should not raise
        assert conn.status == "disconnected"


# ---------------------------------------------------------------------------
# MCPHost — discover local
# ---------------------------------------------------------------------------


class TestMCPHostDiscover:
    def test_discover_empty_dir(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        plugins = host.discover()
        assert plugins == []

    def test_discover_valid_plugin(self, tmp_path: Path):
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        desc = {
            "name": "myplugin",
            "command": "python",
            "args": ["server.py"],
            "description": "Test plugin",
        }
        (plugin_dir / "descriptor.json").write_text(json.dumps(desc))

        host = MCPHost(plugin_dir=tmp_path)
        plugins = host.discover()

        assert len(plugins) == 1
        assert plugins[0].name == "myplugin"
        assert plugins[0].transport == "stdio"

    def test_discover_skips_invalid_descriptor(self, tmp_path: Path):
        plugin_dir = tmp_path / "bad"
        plugin_dir.mkdir()
        (plugin_dir / "descriptor.json").write_text("not json")

        host = MCPHost(plugin_dir=tmp_path)
        plugins = host.discover()
        assert plugins == []

    def test_discover_skips_missing_required_fields(self, tmp_path: Path):
        plugin_dir = tmp_path / "incomplete"
        plugin_dir.mkdir()
        (plugin_dir / "descriptor.json").write_text(json.dumps({"name": "test"}))

        host = MCPHost(plugin_dir=tmp_path)
        plugins = host.discover()
        assert plugins == []

    def test_discover_creates_dir_if_missing(self, tmp_path: Path):
        plugin_dir = tmp_path / "nonexistent"
        host = MCPHost(plugin_dir=plugin_dir)
        host.discover()
        assert plugin_dir.exists()

    def test_discover_ignores_files(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("hello")
        host = MCPHost(plugin_dir=tmp_path)
        plugins = host.discover()
        assert plugins == []


# ---------------------------------------------------------------------------
# MCPHost — discover remote
# ---------------------------------------------------------------------------


class TestMCPHostDiscoverRemote:
    def test_discover_loads_remotes(self, tmp_path: Path):
        remotes_path = tmp_path / "remotes.json"
        remotes_path.write_text(json.dumps([
            {
                "name": "remote1",
                "transport": "streamable_http",
                "url": "https://example.com/mcp",
            },
        ]))

        host = MCPHost(plugin_dir=tmp_path / "plugins", remotes_path=remotes_path)
        plugins = host.discover()

        assert len(plugins) == 1
        assert plugins[0].name == "remote1"
        assert plugins[0].transport == "streamable_http"
        assert plugins[0].url == "https://example.com/mcp"

    def test_discover_skips_invalid_remote_name(self, tmp_path: Path):
        remotes_path = tmp_path / "remotes.json"
        remotes_path.write_text(json.dumps([
            {"name": "../escape", "transport": "sse", "url": "https://example.com"},
        ]))

        host = MCPHost(plugin_dir=tmp_path / "plugins", remotes_path=remotes_path)
        plugins = host.discover()
        assert plugins == []

    def test_discover_no_remotes_file(self, tmp_path: Path):
        host = MCPHost(
            plugin_dir=tmp_path / "plugins",
            remotes_path=tmp_path / "nonexistent.json",
        )
        plugins = host.discover()
        assert plugins == []

    def test_discover_both_local_and_remote(self, tmp_path: Path):
        # Local
        plugin_dir = tmp_path / "plugins" / "local1"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "descriptor.json").write_text(json.dumps({
            "name": "local1", "command": "python",
        }))

        # Remote
        remotes_path = tmp_path / "remotes.json"
        remotes_path.write_text(json.dumps([
            {"name": "remote1", "transport": "sse", "url": "https://example.com"},
        ]))

        host = MCPHost(plugin_dir=tmp_path / "plugins", remotes_path=remotes_path)
        plugins = host.discover()
        assert len(plugins) == 2
        names = {p.name for p in plugins}
        assert names == {"local1", "remote1"}


# ---------------------------------------------------------------------------
# MCPHost — lifecycle (async)
# ---------------------------------------------------------------------------


class TestMCPHostLifecycle:
    def _setup_host(self, tmp_path: Path) -> MCPHost:
        plugin_dir = tmp_path / "weather"
        plugin_dir.mkdir()
        desc = {"name": "weather", "command": "python", "args": ["server.py"]}
        (plugin_dir / "descriptor.json").write_text(json.dumps(desc))
        host = MCPHost(plugin_dir=tmp_path)
        host.discover()
        return host

    def test_list_plugins_stopped(self, tmp_path: Path):
        host = self._setup_host(tmp_path)
        plugins = host.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "weather"
        assert plugins[0]["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_start_unknown_plugin(self, tmp_path: Path):
        host = self._setup_host(tmp_path)
        assert await host.start_plugin("nonexistent") is False

    @pytest.mark.asyncio
    async def test_stop_not_running(self, tmp_path: Path):
        host = self._setup_host(tmp_path)
        assert await host.stop_plugin("weather") is False

    @pytest.mark.asyncio
    async def test_remove_plugin(self, tmp_path: Path):
        host = self._setup_host(tmp_path)
        assert await host.remove_plugin("weather") is True
        assert host.list_plugins() == []

    @pytest.mark.asyncio
    async def test_remove_unknown(self, tmp_path: Path):
        host = self._setup_host(tmp_path)
        assert await host.remove_plugin("nonexistent") is False

    def test_get_plugin_tools_from_descriptor(self, tmp_path: Path):
        plugin_dir = tmp_path / "test"
        plugin_dir.mkdir()
        desc = {
            "name": "test",
            "command": "python",
            "tools": [{"name": "do_thing", "description": "Does a thing"}],
        }
        (plugin_dir / "descriptor.json").write_text(json.dumps(desc))
        host = MCPHost(plugin_dir=tmp_path)
        host.discover()
        tools = host.get_plugin_tools("test")
        assert len(tools) == 1
        assert tools[0]["name"] == "do_thing"

    def test_get_all_tool_names_empty(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        assert host.get_all_tool_names() == []

    @pytest.mark.asyncio
    async def test_shutdown_no_plugins(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        await host.shutdown()  # Should not raise


# ---------------------------------------------------------------------------
# MCPHost — call_tool routing
# ---------------------------------------------------------------------------


class TestMCPHostCallTool:
    @pytest.mark.asyncio
    async def test_call_tool_not_connected(self, tmp_path: Path):
        plugin_dir = tmp_path / "test"
        plugin_dir.mkdir()
        desc = {"name": "test", "command": "python"}
        (plugin_dir / "descriptor.json").write_text(json.dumps(desc))
        host = MCPHost(plugin_dir=tmp_path)
        host.discover()

        with pytest.raises(RuntimeError, match="not connected"):
            await host.call_tool("test", "do_thing", {})

    @pytest.mark.asyncio
    async def test_call_tool_unknown_plugin(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        with pytest.raises(RuntimeError, match="not connected"):
            await host.call_tool("nonexistent", "tool", {})


# ---------------------------------------------------------------------------
# MCPHost — remote management
# ---------------------------------------------------------------------------


class TestMCPHostRemoteManagement:
    @pytest.mark.asyncio
    async def test_add_remote_persists(self, tmp_path: Path):
        remotes_path = tmp_path / "remotes.json"

        host = MCPHost(
            plugin_dir=tmp_path / "plugins",
            remotes_path=remotes_path,
        )

        # Mock the actual connection since there's no real server
        with patch.object(MCPConnection, "connect", new_callable=AsyncMock):
            result = await host.add_remote(
                name="test-server",
                url="https://example.com/mcp",
                transport="streamable_http",
            )
            assert result is True

        # Verify persisted
        data = json.loads(remotes_path.read_text())
        assert len(data) == 1
        assert data[0]["name"] == "test-server"

    @pytest.mark.asyncio
    async def test_remove_remote(self, tmp_path: Path):
        remotes_path = tmp_path / "remotes.json"
        remotes_path.write_text(json.dumps([
            {"name": "s1", "transport": "sse", "url": "https://example.com"},
        ]))

        host = MCPHost(
            plugin_dir=tmp_path / "plugins",
            remotes_path=remotes_path,
        )
        host.discover()

        assert await host.remove_remote("s1") is True
        data = json.loads(remotes_path.read_text())
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_auto_connect_remotes_with_auth(self, tmp_path: Path):
        """Remote servers with auth.token_env should auto-connect."""
        remotes_path = tmp_path / "remotes.json"
        remotes_path.write_text(json.dumps([
            {
                "name": "s1",
                "transport": "streamable_http",
                "url": "https://example.com/mcp",
                "auth": {"type": "bearer", "token_env": "S1_TOKEN"},
            },
        ]))

        host = MCPHost(
            plugin_dir=tmp_path / "plugins",
            remotes_path=remotes_path,
        )
        host.discover()

        with patch.object(MCPConnection, "connect", new_callable=AsyncMock):
            count = await host.auto_connect_remotes()
            assert count == 1

    @pytest.mark.asyncio
    async def test_auto_connect_skips_no_auth(self, tmp_path: Path):
        """Remote servers without auth.token_env should not auto-connect."""
        remotes_path = tmp_path / "remotes.json"
        remotes_path.write_text(json.dumps([
            {"name": "s2", "transport": "sse", "url": "https://example.com"},
        ]))

        host = MCPHost(
            plugin_dir=tmp_path / "plugins",
            remotes_path=remotes_path,
        )
        host.discover()

        count = await host.auto_connect_remotes()
        assert count == 0

    @pytest.mark.asyncio
    async def test_auto_connect_handles_errors(self, tmp_path: Path):
        """Auto-connect should not fail entirely if one server errors."""
        remotes_path = tmp_path / "remotes.json"
        remotes_path.write_text(json.dumps([
            {
                "name": "good",
                "transport": "streamable_http",
                "url": "https://good.com/mcp",
                "auth": {"type": "bearer", "token_env": "GOOD_TOKEN"},
            },
            {
                "name": "bad",
                "transport": "streamable_http",
                "url": "https://bad.com/mcp",
                "auth": {"type": "bearer", "token_env": "BAD_TOKEN"},
            },
        ]))

        host = MCPHost(
            plugin_dir=tmp_path / "plugins",
            remotes_path=remotes_path,
        )
        host.discover()

        call_count = 0

        async def mock_connect(self):
            nonlocal call_count
            call_count += 1
            if self.descriptor.name == "bad":
                raise ConnectionError("connection refused")
            self._status = "connected"

        with patch.object(MCPConnection, "connect", mock_connect):
            count = await host.auto_connect_remotes()
            # "good" connects, "bad" fails — count should be 1
            assert count == 1
            assert call_count == 2


# ---------------------------------------------------------------------------
# Security tests
# ---------------------------------------------------------------------------


class TestSecurityValidation:
    def test_allowed_commands_contains_common_runtimes(self):
        assert "python" in _ALLOWED_COMMANDS
        assert "python3" in _ALLOWED_COMMANDS
        assert "node" in _ALLOWED_COMMANDS
        assert "deno" in _ALLOWED_COMMANDS

    def test_disallowed_command_rejected(self, tmp_path: Path):
        plugin_dir = tmp_path / "evil"
        plugin_dir.mkdir()
        desc = {"name": "evil", "command": "bash", "args": ["-c", "rm -rf /"]}
        (plugin_dir / "descriptor.json").write_text(json.dumps(desc))

        host = MCPHost(plugin_dir=tmp_path)
        plugins = host.discover()
        assert len(plugins) == 0

    def test_valid_plugin_name_regex(self):
        assert _PLUGIN_NAME_RE.match("weather") is not None
        assert _PLUGIN_NAME_RE.match("my-plugin") is not None
        assert _PLUGIN_NAME_RE.match("plugin_v2") is not None
        assert _PLUGIN_NAME_RE.match("A1") is not None

    def test_invalid_plugin_name_regex(self):
        assert _PLUGIN_NAME_RE.match("") is None
        assert _PLUGIN_NAME_RE.match("-bad") is None
        assert _PLUGIN_NAME_RE.match("../escape") is None
        assert _PLUGIN_NAME_RE.match("name with spaces") is None
        assert _PLUGIN_NAME_RE.match("a" * 65) is None

    def test_invalid_name_rejected_at_discover(self, tmp_path: Path):
        plugin_dir = tmp_path / "badname"
        plugin_dir.mkdir()
        desc = {"name": "../escape", "command": "python"}
        (plugin_dir / "descriptor.json").write_text(json.dumps(desc))

        host = MCPHost(plugin_dir=tmp_path)
        plugins = host.discover()
        assert len(plugins) == 0

    def test_to_dict_hides_command(self):
        data = {"name": "test", "command": "python", "args": ["server.py"]}
        desc = PluginDescriptor(Path("/p"), data)
        d = desc.to_dict()
        assert "command" not in d
        assert "args" not in d

    def test_env_var_filtering_logic(self):
        """PLUGIN_* env var filtering still works in descriptor."""
        data = {
            "name": "test",
            "command": "python",
            "env": {
                "PLUGIN_API_KEY": "safe",
                "PATH": "/evil/path",
                "HOME": "/evil/home",
            },
        }
        desc = PluginDescriptor(Path("/p"), data)
        safe_env = {k: v for k, v in desc.env.items() if k.startswith("PLUGIN_")}
        assert "PLUGIN_API_KEY" in safe_env
        assert "PATH" not in safe_env
        assert "HOME" not in safe_env


# ---------------------------------------------------------------------------
# Hot-reload watcher tests
# ---------------------------------------------------------------------------


class TestMCPHostWatching:
    def test_start_stop_watching(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        host.start_watching()
        assert host._observer is not None
        assert host._observer.is_alive()

        host.stop_watching()
        assert host._observer is None

    def test_start_watching_idempotent(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        host.start_watching()
        observer1 = host._observer
        host.start_watching()
        assert host._observer is observer1
        host.stop_watching()

    def test_stop_watching_when_not_started(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        host.stop_watching()  # Should not raise

    def test_rediscover_finds_new_plugin(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        host.discover()
        assert len(host.list_plugins()) == 0

        plugin_dir = tmp_path / "newplugin"
        plugin_dir.mkdir()
        desc = {"name": "newplugin", "command": "python", "args": ["server.py"]}
        (plugin_dir / "descriptor.json").write_text(json.dumps(desc))

        host._rediscover()
        plugins = host.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "newplugin"

    def test_rediscover_skips_already_known(self, tmp_path: Path):
        plugin_dir = tmp_path / "existing"
        plugin_dir.mkdir()
        desc = {"name": "existing", "command": "python"}
        (plugin_dir / "descriptor.json").write_text(json.dumps(desc))

        host = MCPHost(plugin_dir=tmp_path)
        host.discover()
        assert len(host.list_plugins()) == 1

        host._rediscover()
        assert len(host.list_plugins()) == 1

    @pytest.mark.asyncio
    async def test_shutdown_stops_watcher(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        host.start_watching()
        assert host._observer is not None

        await host.shutdown()
        assert host._observer is None
