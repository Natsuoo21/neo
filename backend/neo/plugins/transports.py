"""MCP transport layer — connect to MCP servers via stdio, SSE, or streamable HTTP.

Wraps the official ``mcp`` Python SDK transport helpers and provides a
uniform ``connect()`` entry-point that returns the
``(read_stream, write_stream)`` pair expected by ``ClientSession``.
"""

import logging
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transport type enum
# ---------------------------------------------------------------------------


class TransportType(Enum):
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StdioConfig:
    """Configuration for a local stdio-based MCP server."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None


@dataclass
class RemoteConfig:
    """Configuration for a remote (SSE / HTTP) MCP server."""

    url: str
    auth_type: str | None = None  # "bearer", "api_key", "header"
    token_env: str | None = None  # env var name holding the token
    headers: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Auth token resolution
# ---------------------------------------------------------------------------

_SECRETS_PATH = Path.home() / ".neo" / "secrets.json"


def resolve_auth_token(config: RemoteConfig) -> str | None:
    """Resolve an auth token from env var or ``~/.neo/secrets.json``.

    Returns ``None`` if no token source is configured.
    """
    # 1. Try environment variable
    if config.token_env:
        value = os.environ.get(config.token_env)
        if value:
            return value

    # 2. Try secrets file (lazy import to avoid circular deps)
    try:
        from neo.plugins.secrets import get_secret

        return get_secret(config.token_env or "")
    except Exception:
        return None


def _build_auth_headers(config: RemoteConfig) -> dict[str, str]:
    """Build HTTP headers with auth token injected."""
    headers = dict(config.headers)
    token = resolve_auth_token(config)
    if token and config.auth_type:
        auth_type = config.auth_type.lower()
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key":
            headers["X-API-Key"] = token
        elif auth_type == "header":
            # token_env points to a raw header value
            headers["Authorization"] = token
    return headers


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


def validate_url(url: str) -> None:
    """Validate a remote MCP server URL.

    Allows ``https://`` for any host and ``http://`` only for localhost.
    Raises ``ValueError`` on invalid URLs.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{parsed.scheme}'. Must be http or https.")

    if not parsed.hostname:
        raise ValueError(f"Invalid URL: missing hostname in '{url}'.")

    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError(
            f"HTTP (non-TLS) is only allowed for localhost. Got: {parsed.hostname}. "
            "Use https:// for remote servers."
        )


# ---------------------------------------------------------------------------
# Connect helpers
# ---------------------------------------------------------------------------


async def connect_stdio(
    config: StdioConfig,
    exit_stack: AsyncExitStack,
) -> tuple[Any, Any]:
    """Connect to a local MCP server via stdio.

    Returns ``(read_stream, write_stream)`` for ``ClientSession``.
    """
    params = StdioServerParameters(
        command=config.command,
        args=config.args,
        env=config.env or None,
        cwd=config.cwd,
    )
    read_stream, write_stream = await exit_stack.enter_async_context(
        stdio_client(params),
    )
    return read_stream, write_stream


async def connect_sse(
    config: RemoteConfig,
    exit_stack: AsyncExitStack,
) -> tuple[Any, Any]:
    """Connect to an MCP server via SSE (legacy transport).

    Returns ``(read_stream, write_stream)`` for ``ClientSession``.
    """
    validate_url(config.url)
    headers = _build_auth_headers(config)
    read_stream, write_stream = await exit_stack.enter_async_context(
        sse_client(url=config.url, headers=headers),
    )
    return read_stream, write_stream


async def connect_streamable_http(
    config: RemoteConfig,
    exit_stack: AsyncExitStack,
) -> tuple[Any, Any]:
    """Connect to an MCP server via streamable HTTP.

    Returns ``(read_stream, write_stream)`` for ``ClientSession``.
    """
    validate_url(config.url)
    headers = _build_auth_headers(config)
    read_stream, write_stream, _get_session_id = await exit_stack.enter_async_context(
        streamablehttp_client(url=config.url, headers=headers),
    )
    return read_stream, write_stream


# ---------------------------------------------------------------------------
# Unified connect entry-point
# ---------------------------------------------------------------------------


_CONNECT_MAP = {
    TransportType.STDIO: None,  # handled separately (different config type)
    TransportType.SSE: connect_sse,
    TransportType.STREAMABLE_HTTP: connect_streamable_http,
}


async def connect(
    transport_type: TransportType,
    *,
    stdio_config: StdioConfig | None = None,
    remote_config: RemoteConfig | None = None,
    exit_stack: AsyncExitStack,
) -> ClientSession:
    """Create and initialise a ``ClientSession`` for the given transport.

    The caller must manage the *exit_stack* lifetime — closing it will
    tear down the underlying transport connection.
    """
    if transport_type == TransportType.STDIO:
        if stdio_config is None:
            raise ValueError("stdio_config is required for STDIO transport")
        read_stream, write_stream = await connect_stdio(stdio_config, exit_stack)
    else:
        if remote_config is None:
            raise ValueError("remote_config is required for remote transports")
        if transport_type == TransportType.SSE:
            read_stream, write_stream = await connect_sse(remote_config, exit_stack)
        elif transport_type == TransportType.STREAMABLE_HTTP:
            read_stream, write_stream = await connect_streamable_http(remote_config, exit_stack)
        else:
            raise ValueError(f"Unsupported transport: {transport_type}")

    session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
    await session.initialize()
    return session
