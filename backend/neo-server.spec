# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Neo server sidecar.

Produces a platform-specific binary:
    Windows:  neo-server-x86_64-pc-windows-msvc.exe
    Linux:    neo-server-x86_64-unknown-linux-gnu
    macOS:    neo-server-aarch64-apple-darwin

Place output in: frontend/src-tauri/binaries/

Build:
    cd backend
    pyinstaller neo-server.spec --noconfirm --clean
"""

import os
import platform
import struct
from pathlib import Path

block_cipher = None


# ---------------------------------------------------------------------------
# Target triple detection (matches Tauri's sidecar naming convention)
# ---------------------------------------------------------------------------

def _target_triple():
    bits = struct.calcsize("P") * 8
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        arch = "x86_64" if bits == 64 else "i686"
        return f"{arch}-pc-windows-msvc"
    elif system == "linux":
        arch = "x86_64" if machine == "x86_64" else machine
        return f"{arch}-unknown-linux-gnu"
    elif system == "darwin":
        arch = "aarch64" if machine == "arm64" else machine
        return f"{arch}-apple-darwin"
    return f"{machine}-unknown-{system}"


TARGET_TRIPLE = _target_triple()

# ---------------------------------------------------------------------------
# Paths relative to this spec file
# ---------------------------------------------------------------------------

backend_dir = os.path.dirname(os.path.abspath(SPEC))
neo_dir = os.path.join(backend_dir, "neo")
schema_path = os.path.join(neo_dir, "memory", "schema.sql")
skills_public = os.path.join(neo_dir, "skills", "public")

a = Analysis(
    [os.path.join(neo_dir, "server.py")],
    pathex=[backend_dir],
    binaries=[],
    datas=[
        (schema_path, os.path.join("neo", "memory")),
        (skills_public, os.path.join("neo", "skills", "public")),
    ],
    hiddenimports=[
        # ------------------------------------------------------------------
        # Neo core
        # ------------------------------------------------------------------
        "neo",
        "neo.server",
        "neo.orchestrator",
        "neo.router",
        "neo.main",
        "neo.updater",

        # Memory / DB
        "neo.memory",
        "neo.memory.db",
        "neo.memory.models",
        "neo.memory.seed",

        # Skills
        "neo.skills",
        "neo.skills.loader",
        "neo.skills.watcher",

        # LLM providers
        "neo.llm",
        "neo.llm.provider",
        "neo.llm.registry",
        "neo.llm.claude",
        "neo.llm.gemini",
        "neo.llm.openai_provider",
        "neo.llm.ollama",
        "neo.llm.mock",

        # Tools
        "neo.tools",
        "neo.tools.excel",
        "neo.tools.powerpoint",
        "neo.tools.word",
        "neo.tools.obsidian",
        "neo.tools.files",
        "neo.tools.paths",
        "neo.tools.browser",
        "neo.tools.calendar",
        "neo.tools.gmail",
        "neo.tools.google_auth",

        # Automations
        "neo.automations",
        "neo.automations.scheduler",
        "neo.automations.safety",
        "neo.automations.watcher",
        "neo.automations.suggestions",

        # Voice
        "neo.voice",
        "neo.voice.stt",
        "neo.voice.tts",

        # Plugins
        "neo.plugins",
        "neo.plugins.mcp_host",

        # ------------------------------------------------------------------
        # Third-party — HTTP server
        # ------------------------------------------------------------------
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "starlette",
        "starlette.responses",
        "starlette.routing",
        "sse_starlette",
        "anyio",
        "anyio._backends",
        "anyio._backends._asyncio",

        # HTTP client (Ollama, etc.)
        "httpx",
        "httpx._transports",
        "httpx._transports.default",

        # Data / settings
        "pydantic",
        "pydantic_settings",
        "dotenv",

        # ------------------------------------------------------------------
        # Third-party — scheduling & persistence
        # ------------------------------------------------------------------
        "apscheduler",
        "apscheduler.schedulers.background",
        "apscheduler.triggers.cron",
        "apscheduler.jobstores.sqlalchemy",
        "sqlalchemy",
        "sqlalchemy.pool",

        # File watching
        "watchdog",
        "watchdog.observers",
        "watchdog.events",

        # ------------------------------------------------------------------
        # Third-party — AI providers
        # ------------------------------------------------------------------
        "anthropic",
        "openai",
        "google.generativeai",

        # ------------------------------------------------------------------
        # Third-party — Google APIs (Calendar, Gmail, OAuth)
        # ------------------------------------------------------------------
        "google.auth",
        "google.auth.transport.requests",
        "google_auth_oauthlib",
        "google_auth_oauthlib.flow",
        "googleapiclient",
        "googleapiclient.discovery",

        # ------------------------------------------------------------------
        # Third-party — document creation
        # ------------------------------------------------------------------
        "openpyxl",
        "pptx",
        "docx",

        # ------------------------------------------------------------------
        # Third-party — MCP
        # ------------------------------------------------------------------
        "mcp",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "PIL",
        "cv2",
        # Playwright is heavy and loaded lazily — excluded from bundle
        "playwright",
        # Voice deps are heavy and loaded lazily — exclude from base bundle
        "whisper",
        "sounddevice",
        "pyttsx3",
        "numpy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=f"neo-server-{TARGET_TRIPLE}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
