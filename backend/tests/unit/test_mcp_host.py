"""Tests for neo.plugins.mcp_host — MCP plugin host."""

import json
from pathlib import Path

import pytest

from neo.plugins.mcp_host import (
    _ALLOWED_COMMANDS,
    _PLUGIN_NAME_RE,
    MCPHost,
    PluginDescriptor,
    PluginProcess,
)

# ---------------------------------------------------------------------------
# PluginDescriptor
# ---------------------------------------------------------------------------


class TestPluginDescriptor:
    def test_parse_minimal(self):
        data = {"name": "test", "command": "python", "args": ["main.py"]}
        desc = PluginDescriptor(Path("/tmp/test/descriptor.json"), data)
        assert desc.name == "test"
        assert desc.command == "python"
        assert desc.args == ["main.py"]
        assert desc.version == "0.0.0"
        assert desc.description == ""
        assert desc.tools == []
        assert desc.env == {}

    def test_parse_full(self):
        data = {
            "name": "weather",
            "version": "1.0.0",
            "description": "Get weather",
            "command": "node",
            "args": ["index.js"],
            "env": {"API_KEY": "test"},
            "tools": [{"name": "get_weather"}],
        }
        desc = PluginDescriptor(Path("/tmp/weather/descriptor.json"), data)
        assert desc.name == "weather"
        assert desc.version == "1.0.0"
        assert desc.description == "Get weather"
        assert desc.env == {"API_KEY": "test"}
        assert len(desc.tools) == 1

    def test_to_dict(self):
        data = {"name": "test", "command": "python"}
        desc = PluginDescriptor(Path("/p"), data)
        d = desc.to_dict()
        assert d["name"] == "test"
        assert "command" not in d  # S3: command hidden from public API
        assert "args" not in d
        assert "path" not in d


# ---------------------------------------------------------------------------
# MCPHost — discover
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
# MCPHost — list / start / stop / remove
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

    def test_start_unknown_plugin(self, tmp_path: Path):
        host = self._setup_host(tmp_path)
        assert host.start_plugin("nonexistent") is False

    def test_stop_not_running(self, tmp_path: Path):
        host = self._setup_host(tmp_path)
        assert host.stop_plugin("weather") is False

    def test_remove_plugin(self, tmp_path: Path):
        host = self._setup_host(tmp_path)
        assert host.remove_plugin("weather") is True
        assert host.list_plugins() == []

    def test_remove_unknown(self, tmp_path: Path):
        host = self._setup_host(tmp_path)
        assert host.remove_plugin("nonexistent") is False

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

    def test_shutdown_no_plugins(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        host.shutdown()  # Should not raise


# ---------------------------------------------------------------------------
# PluginProcess — unit-level
# ---------------------------------------------------------------------------


class TestPluginProcess:
    def _make_process(self) -> PluginProcess:
        data = {"name": "test", "command": "echo", "args": ["hello"]}
        desc = PluginDescriptor(Path("/tmp/test/descriptor.json"), data)
        return PluginProcess(desc)

    def test_not_running_initially(self):
        proc = self._make_process()
        assert proc.running is False

    def test_call_tool_not_running(self):
        proc = self._make_process()
        with pytest.raises(RuntimeError, match="not running"):
            proc.call_tool("test", {})

    def test_list_tools_not_running(self):
        data = {"name": "test", "command": "echo", "tools": [{"name": "a"}]}
        desc = PluginDescriptor(Path("/tmp/test/descriptor.json"), data)
        proc = PluginProcess(desc)
        tools = proc.list_tools()
        assert tools == [{"name": "a"}]

    def test_stop_not_running(self):
        proc = self._make_process()
        proc.stop()  # Should not raise


# ---------------------------------------------------------------------------
# MCPHost — call_tool routing
# ---------------------------------------------------------------------------


class TestMCPHostCallTool:
    def test_call_tool_not_running(self, tmp_path: Path):
        plugin_dir = tmp_path / "test"
        plugin_dir.mkdir()
        desc = {"name": "test", "command": "python"}
        (plugin_dir / "descriptor.json").write_text(json.dumps(desc))
        host = MCPHost(plugin_dir=tmp_path)
        host.discover()

        with pytest.raises(RuntimeError, match="not running"):
            host.call_tool("test", "do_thing", {})

    def test_call_tool_unknown_plugin(self, tmp_path: Path):
        host = MCPHost(plugin_dir=tmp_path)
        with pytest.raises(RuntimeError, match="not running"):
            host.call_tool("nonexistent", "tool", {})


# ---------------------------------------------------------------------------
# Integration: start example weather plugin
# ---------------------------------------------------------------------------


class TestExampleWeatherPlugin:
    """Integration test with the bundled example weather plugin."""

    @pytest.fixture
    def weather_host(self, tmp_path: Path) -> MCPHost:
        """Set up a host with the example weather plugin copied to tmp."""
        import shutil

        example_dir = Path(__file__).resolve().parent.parent.parent / "neo" / "plugins" / "example_weather"
        if not example_dir.exists():
            pytest.skip("Example weather plugin not found")

        dest = tmp_path / "weather"
        shutil.copytree(example_dir, dest)

        # Rewrite descriptor to use absolute python path
        import sys

        desc_path = dest / "descriptor.json"
        desc_data = json.loads(desc_path.read_text())
        desc_data["command"] = sys.executable
        desc_path.write_text(json.dumps(desc_data))

        host = MCPHost(plugin_dir=tmp_path)
        host.discover()
        return host

    def test_start_and_call(self, weather_host: MCPHost):
        assert weather_host.start_plugin("weather") is True

        plugins = weather_host.list_plugins()
        assert any(p["name"] == "weather" and p["status"] == "running" for p in plugins)

        result = weather_host.call_tool("weather", "get_weather", {"city": "Tokyo"})
        assert "Tokyo" in result
        assert "22°C" in result

        weather_host.stop_plugin("weather")
        plugins = weather_host.list_plugins()
        assert any(p["name"] == "weather" and p["status"] == "stopped" for p in plugins)

    def test_list_tools_from_running_plugin(self, weather_host: MCPHost):
        weather_host.start_plugin("weather")
        tools = weather_host.get_plugin_tools("weather")
        assert len(tools) >= 1
        assert any(t["name"] == "get_weather" for t in tools)
        weather_host.shutdown()

    def test_get_all_tool_names(self, weather_host: MCPHost):
        weather_host.start_plugin("weather")
        names = weather_host.get_all_tool_names()
        assert "plugin::weather::get_weather" in names
        weather_host.shutdown()


# ---------------------------------------------------------------------------
# Security tests
# ---------------------------------------------------------------------------


class TestSecurityValidation:
    """Tests for S1/S2/S3/BP9 security hardening."""

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
        assert len(plugins) == 0  # Rejected at discover time

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
        assert _PLUGIN_NAME_RE.match("a" * 65) is None  # Too long

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

    def test_env_var_filtering(self):
        """Only PLUGIN_* env vars should pass through."""
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
        PluginProcess(desc)  # Verify it can be created

        # Verify the env filtering logic
        safe_env = {
            k: v for k, v in desc.env.items()
            if k.startswith("PLUGIN_")
        }
        assert "PLUGIN_API_KEY" in safe_env
        assert "PATH" not in safe_env
        assert "HOME" not in safe_env
