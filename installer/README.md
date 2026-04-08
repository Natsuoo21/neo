# Neo Installer — Build Instructions

## Prerequisites

- Windows 10/11 (x64)
- [Inno Setup 6+](https://jrsoftware.org/isdl.php) installed
- Node.js 20+ (for Tauri build)
- Python 3.12+ (for PyInstaller)
- Rust toolchain (for Tauri)

## Build Steps

### 1. Build the Tauri desktop app

```bash
cd frontend
npm install
npm run tauri build
```

Output: `frontend/src-tauri/target/release/Neo.exe`

### 2. Package the Python backend sidecar

```bash
cd backend
pip install pyinstaller
pyinstaller --name neo-server --onedir neo/server.py \
  --hidden-import neo.tools.excel \
  --hidden-import neo.tools.powerpoint \
  --hidden-import neo.tools.word \
  --hidden-import neo.tools.obsidian \
  --hidden-import neo.tools.files \
  --hidden-import neo.tools.browser \
  --hidden-import neo.tools.calendar \
  --hidden-import neo.tools.gmail \
  --hidden-import neo.plugins.mcp_host \
  --hidden-import neo.voice.stt \
  --hidden-import neo.voice.tts \
  --hidden-import neo.automations.scheduler \
  --hidden-import neo.automations.watcher \
  --hidden-import neo.automations.suggestions
```

Output: `backend/dist/neo-server/`

### 3. Compile the installer

Open `installer/neo_setup.iss` in Inno Setup Compiler and click Build, or:

```bash
iscc installer/neo_setup.iss
```

Output: `installer/output/NeoSetup-0.1.0.exe`

## Optional: Ollama for Local AI

The installer includes an optional checkbox to download and install Ollama during setup:

- **Auto-detection**: If Ollama is already installed, the checkbox is disabled with "(already installed)"
- **Download at install time**: `OllamaSetup.exe` is downloaded from `https://ollama.com/download/OllamaSetup.exe` via Inno Setup's `DownloadTemporaryFile` (requires Inno Setup 6.3+)
- **Silent install**: Runs `/VERYSILENT /SUPPRESSMSGBOXES` — no user interaction needed
- **Default model pull**: After install, `ollama pull qwen2.5:3b` runs in the background (non-blocking) so the model downloads while the user starts Neo
- **Graceful failure**: If download or install fails, a message box informs the user and the Neo installation continues normally

## Directory Structure (installed)

```
C:\Users\{user}\AppData\Local\Programs\Neo\
├── Neo.exe              # Tauri desktop app
├── neo-server/          # Python backend (PyInstaller bundle)
│   ├── neo-server.exe
│   └── ...
├── data/                # SQLite database
│   └── neo.db
└── skills/              # Built-in skills
    └── public/
```
