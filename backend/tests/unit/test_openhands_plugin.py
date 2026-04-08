"""Tests for the OpenHands MCP plugin server."""

from unittest.mock import MagicMock, patch

import pytest

from neo.plugins.openhands.server import handle_request


class TestInitialize:
    def test_returns_mcp_protocol_version(self):
        resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert resp is not None
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert resp["result"]["serverInfo"]["name"] == "openhands"


class TestToolsList:
    def test_returns_four_tools(self):
        resp = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert resp is not None
        tools = resp["result"]["tools"]
        assert len(tools) == 4
        names = {t["name"] for t in tools}
        assert names == {"execute_code", "execute_shell", "read_file", "write_file"}

    def test_tools_have_input_schemas(self):
        resp = handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
        for tool in resp["result"]["tools"]:
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"


class TestExecuteCode:
    @patch("neo.plugins.openhands.server._http_request")
    @patch("neo.plugins.openhands.server._conversation_id", "test-conv")
    def test_execute_python_code(self, mock_http):
        mock_http.return_value = {
            "observation": {"content": "Hello, World!", "exit_code": 0},
        }

        resp = handle_request({
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "execute_code", "arguments": {"code": "print('Hello, World!')"}},
        })

        assert resp is not None
        assert resp["result"]["content"][0]["text"] == "Hello, World!"
        mock_http.assert_called_once()
        call_args = mock_http.call_args
        assert call_args[0][0] == "POST"
        assert "test-conv" in call_args[0][1]

    @patch("neo.plugins.openhands.server._http_request")
    @patch("neo.plugins.openhands.server._conversation_id", "test-conv")
    def test_execute_code_with_error_exit(self, mock_http):
        mock_http.return_value = {
            "observation": {"content": "", "stderr": "NameError: name 'x' is not defined", "exit_code": 1},
        }

        resp = handle_request({
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "execute_code", "arguments": {"code": "print(x)"}},
        })

        assert resp is not None
        text = resp["result"]["content"][0]["text"]
        assert "Exit code 1" in text
        assert "NameError" in text


class TestExecuteShell:
    @patch("neo.plugins.openhands.server._http_request")
    @patch("neo.plugins.openhands.server._conversation_id", "test-conv")
    def test_execute_shell_command(self, mock_http):
        mock_http.return_value = {
            "observation": {"content": "file1.txt\nfile2.py", "exit_code": 0},
        }

        resp = handle_request({
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {"name": "execute_shell", "arguments": {"command": "ls"}},
        })

        assert resp is not None
        assert "file1.txt" in resp["result"]["content"][0]["text"]


class TestReadFile:
    @patch("neo.plugins.openhands.server._http_request")
    @patch("neo.plugins.openhands.server._conversation_id", "test-conv")
    def test_read_file(self, mock_http):
        mock_http.return_value = {"content": "Hello from file"}

        resp = handle_request({
            "jsonrpc": "2.0",
            "id": 30,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": "/workspace/test.txt"}},
        })

        assert resp is not None
        assert resp["result"]["content"][0]["text"] == "Hello from file"


class TestWriteFile:
    @patch("neo.plugins.openhands.server._http_request")
    @patch("neo.plugins.openhands.server._conversation_id", "test-conv")
    def test_write_file(self, mock_http):
        mock_http.return_value = {}

        resp = handle_request({
            "jsonrpc": "2.0",
            "id": 40,
            "method": "tools/call",
            "params": {"name": "write_file", "arguments": {"path": "/workspace/out.txt", "content": "data"}},
        })

        assert resp is not None
        assert "Written to" in resp["result"]["content"][0]["text"]
        mock_http.assert_called_once()
        call_body = mock_http.call_args[0][2]
        assert call_body["path"] == "/workspace/out.txt"
        assert call_body["content"] == "data"


class TestConnectionError:
    @patch("neo.plugins.openhands.server._http_request")
    @patch("neo.plugins.openhands.server._conversation_id", "test-conv")
    def test_connection_error_returns_clear_message(self, mock_http):
        mock_http.side_effect = RuntimeError(
            "OpenHands is not running at http://localhost:3000. Start it first."
        )

        resp = handle_request({
            "jsonrpc": "2.0",
            "id": 50,
            "method": "tools/call",
            "params": {"name": "execute_code", "arguments": {"code": "print(1)"}},
        })

        assert resp is not None
        assert resp["result"].get("isError") is True
        assert "not running" in resp["result"]["content"][0]["text"]


class TestUnknownTool:
    def test_unknown_tool_returns_error(self):
        resp = handle_request({
            "jsonrpc": "2.0",
            "id": 60,
            "method": "tools/call",
            "params": {"name": "nonexistent", "arguments": {}},
        })

        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == -32601


class TestNotifications:
    def test_notification_returns_none(self):
        resp = handle_request({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        assert resp is None


class TestUnknownMethod:
    def test_unknown_method_returns_error(self):
        resp = handle_request({"jsonrpc": "2.0", "id": 70, "method": "unknown/method", "params": {}})
        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == -32601
