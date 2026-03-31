# Neo — Personal Intelligence Agent

A desktop software agent that runs permanently in the background on Windows. Invoked via global hotkey, voice command, or scheduled triggers. Neo understands natural language, routes tasks to the appropriate tools, and executes actions in the real world.

**Neo is not a chatbot. It is a personal agent that acts on your behalf.**

## Features (Roadmap)

- **Document Creation** — Excel, PowerPoint, Word, Obsidian notes
- **File Management** — Move, rename, organize files by natural language
- **Skills System** — Personalized templates and conventions
- **Intelligence Routing** — Local models (free) → Gemini (free) → Claude (complex)
- **Automation Engine** — Scheduled tasks, file watchers, proactive suggestions
- **Browser Control** — Navigate, extract, fill forms, monitor pages
- **Voice Interface** — "Hey Neo" wake word with local Whisper STT
- **MCP Plugins** — Extensible tool ecosystem via Model Context Protocol

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, SQLite, APScheduler |
| Frontend | Tauri (Rust + webview), React, TypeScript, Tailwind |
| AI | Ollama (local), Gemini (free tier), Claude API |
| Tools | openpyxl, python-pptx, python-docx, Playwright |

## Quick Start

```bash
# Clone
git clone https://github.com/Natsuoo21/neo.git
cd neo

# Python setup
cd backend
python -m venv .venv
source .venv/bin/activate  # Linux/WSL
pip install -r requirements-dev.txt

# Run CLI
python -m neo.main
```

## Project Structure

```
neo/
├── backend/          # Python orchestrator
│   ├── neo/          # Main package
│   │   ├── memory/   # SQLite database layer
│   │   ├── tools/    # Excel, PPT, Word, Obsidian, Files, Browser
│   │   ├── skills/   # Public + user skill files
│   │   ├── automations/  # Scheduler + file watcher
│   │   ├── plugins/  # MCP plugin host
│   │   └── voice/    # STT + TTS
│   └── tests/        # Unit + integration tests
├── frontend/         # Tauri + React app (Phase 2)
├── installer/        # Inno Setup script (Phase 4)
└── data/             # SQLite database (gitignored)
```

## Development Phases

| Phase | Goal | Status |
|-------|------|--------|
| 0 | Foundations + CLI + Tools | Complete |
| 1 | Intelligence Routing + Memory | Complete |
| 2 | Desktop Interface (Tauri) | Planned |
| 3 | Automation + Browser Control | Planned |
| 4 | Voice + Plugins + Installer | Planned |

## License

Private — All rights reserved.
