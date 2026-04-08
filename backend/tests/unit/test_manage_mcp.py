"""Tests for neo.tools.manage_mcp — MCP management tool (chat-accessible)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from neo.tools.manage_mcp import manage_mcp


def _make_host(plugins=None):
    """Create a mock MCPHost with optional plugin list."""
    host = MagicMock()
    host.list_plugins.return_value = plugins or []
    host.start_plugin = AsyncMock(return_value=True)
    host.stop_plugin = AsyncMock(return_value=True)
    host.add_remote = AsyncMock(return_value=True)
    host.remove_remote = AsyncMock(return_value=True)
    host.get_plugin_tools.return_value = [
        {"name": "tool1", "description": "A tool"},
    ]
    return host


class TestManageMcpList:
    @pytest.mark.asyncio
    async def test_list_empty(self):
        host = _make_host([])
        result = await manage_mcp(host, action="list")
        assert "No MCP servers" in result

    @pytest.mark.asyncio
    async def test_list_with_plugins(self):
        host = _make_host([
            {"name": "weather", "status": "running", "transport": "stdio", "tools": [{"name": "get_weather"}]},
            {"name": "github", "status": "connected", "transport": "streamable_http", "url": "https://api.github.com/mcp", "tools": []},
        ])
        result = await manage_mcp(host, action="list")
        assert "weather" in result
        assert "github" in result
        assert "2" in result  # count


class TestManageMcpConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        host = _make_host([
            {"name": "github", "status": "stopped", "transport": "streamable_http"},
        ])
        result = await manage_mcp(host, action="connect", name="github")
        assert "Successfully connected" in result
        host.start_plugin.assert_awaited_once_with("github")

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        host = _make_host([
            {"name": "github", "status": "connected", "transport": "streamable_http"},
        ])
        result = await manage_mcp(host, action="connect", name="github")
        assert "already connected" in result

    @pytest.mark.asyncio
    async def test_connect_not_found(self):
        host = _make_host([])
        with pytest.raises(ValueError, match="not found"):
            await manage_mcp(host, action="connect", name="nonexistent")

    @pytest.mark.asyncio
    async def test_connect_failure(self):
        host = _make_host([
            {"name": "bad", "status": "stopped", "transport": "streamable_http"},
        ])
        host.start_plugin = AsyncMock(return_value=False)
        with pytest.raises(RuntimeError, match="Failed to connect"):
            await manage_mcp(host, action="connect", name="bad")


class TestManageMcpDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_success(self):
        host = _make_host()
        result = await manage_mcp(host, action="disconnect", name="github")
        assert "Disconnected" in result

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self):
        host = _make_host()
        host.stop_plugin = AsyncMock(return_value=False)
        result = await manage_mcp(host, action="disconnect", name="github")
        assert "not connected" in result


class TestManageMcpAdd:
    @pytest.mark.asyncio
    async def test_add_success(self):
        host = _make_host()
        result = await manage_mcp(
            host, action="add", name="github",
            url="https://api.github.com/mcp",
            transport="streamable_http",
        )
        assert "Added and connected" in result
        assert "github" in result
        host.add_remote.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_missing_url(self):
        host = _make_host()
        with pytest.raises(ValueError, match="url"):
            await manage_mcp(host, action="add", name="github")

    @pytest.mark.asyncio
    async def test_add_invalid_transport(self):
        host = _make_host()
        with pytest.raises(ValueError, match="Invalid transport"):
            await manage_mcp(host, action="add", name="x", url="https://x.com", transport="websocket")

    @pytest.mark.asyncio
    async def test_add_with_token(self):
        host = _make_host()
        with patch("neo.plugins.secrets.set_secret") as mock_set:
            result = await manage_mcp(
                host, action="add", name="github",
                url="https://api.github.com/mcp",
                auth_type="bearer", token_env="GITHUB_TOKEN",
                token_value="ghp_abc123",
            )
            assert "Added and connected" in result
            mock_set.assert_called_once_with("GITHUB_TOKEN", "ghp_abc123")

    @pytest.mark.asyncio
    async def test_add_with_auth_no_token(self):
        host = _make_host()
        result = await manage_mcp(
            host, action="add", name="github",
            url="https://api.github.com/mcp",
            auth_type="bearer", token_env="GITHUB_TOKEN",
        )
        assert "Added and connected" in result
        # Verify auth was passed
        call_kwargs = host.add_remote.call_args[1]
        assert call_kwargs["auth"] == {"type": "bearer", "token_env": "GITHUB_TOKEN"}


class TestManageMcpRemove:
    @pytest.mark.asyncio
    async def test_remove_success(self):
        host = _make_host()
        result = await manage_mcp(host, action="remove", name="github")
        assert "Removed" in result

    @pytest.mark.asyncio
    async def test_remove_not_found(self):
        host = _make_host()
        host.remove_remote = AsyncMock(return_value=False)
        with pytest.raises(ValueError, match="not found"):
            await manage_mcp(host, action="remove", name="nonexistent")


class TestManageMcpValidation:
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        host = _make_host()
        with pytest.raises(ValueError, match="Invalid action"):
            await manage_mcp(host, action="restart")

    @pytest.mark.asyncio
    async def test_missing_name_for_connect(self):
        host = _make_host()
        with pytest.raises(ValueError, match="name"):
            await manage_mcp(host, action="connect")
