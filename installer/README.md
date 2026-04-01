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

## Optional: Bundle Ollama

To include Ollama for local LLM support:

1. Download the Ollama Windows installer from https://ollama.com
2. Add to `[Files]` section in `neo_setup.iss`:
   ```
   Source: "ollama-setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
   ```
3. Add to `[Run]` section:
   ```
   Filename: "{tmp}\ollama-setup.exe"; Parameters: "/SILENT"; StatusMsg: "Installing Ollama..."
   ```

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
