# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Neo server sidecar.

Produces: neo-server-x86_64-pc-windows-msvc.exe
Place output in: frontend/src-tauri/binaries/

Build:
    cd backend
    pyinstaller neo-server.spec
"""

import os
from pathlib import Path

block_cipher = None

# Paths relative to this spec file
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
        "neo",
        "neo.server",
        "neo.orchestrator",
        "neo.router",
        "neo.main",
        "neo.memory.db",
        "neo.memory.models",
        "neo.memory.seed",
        "neo.skills.loader",
        "neo.llm.provider",
        "neo.llm.claude",
        "neo.llm.gemini",
        "neo.llm.openai_provider",
        "neo.llm.ollama",
        "neo.llm.mock",
        "neo.tools.excel",
        "neo.tools.powerpoint",
        "neo.tools.word",
        "neo.tools.obsidian",
        "neo.tools.files",
        "neo.tools.paths",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "starlette",
        "sse_starlette",
        "httpx",
        "pydantic",
        "pydantic_settings",
        "dotenv",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "PIL",
        "cv2",
        "playwright",
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
    name="neo-server-x86_64-pc-windows-msvc",
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
