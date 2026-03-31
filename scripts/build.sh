#!/usr/bin/env bash
# Neo — Linux/WSL build script
# Builds PyInstaller sidecar + Tauri desktop app.
#
# Prerequisites:
#   - Python 3.12+ with pip
#   - Rust (rustup)
#   - Node.js 20+
#   - System deps: libwebkit2gtk-4.1-dev, libappindicator3-dev, etc.
#   - PyInstaller: pip install pyinstaller
#
# Usage:
#   bash scripts/build.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
BINARIES="$FRONTEND/src-tauri/binaries"

echo "=== Neo Build Script ==="

# Step 1: Build Python sidecar
echo ""
echo "[1/3] Building Python sidecar..."

cd "$BACKEND"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet
pyinstaller neo-server.spec --noconfirm --clean

# Step 2: Copy sidecar binary
echo ""
echo "[2/3] Copying sidecar to Tauri binaries..."

mkdir -p "$BINARIES"

# Detect target triple
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64) TRIPLE="x86_64-unknown-linux-gnu" ;;
    aarch64) TRIPLE="aarch64-unknown-linux-gnu" ;;
    *) TRIPLE="$ARCH-unknown-linux-gnu" ;;
esac

SIDECAR_SRC="$BACKEND/dist/neo-server-x86_64-pc-windows-msvc"
SIDECAR_DST="$BINARIES/neo-server-$TRIPLE"

if [ -f "$SIDECAR_SRC" ]; then
    cp "$SIDECAR_SRC" "$SIDECAR_DST"
    chmod +x "$SIDECAR_DST"
    echo "  Copied: $SIDECAR_DST"
else
    echo "  WARNING: Sidecar not found at $SIDECAR_SRC"
    echo "  Continuing without sidecar (dev mode)..."
fi

# Step 3: Build Tauri app
echo ""
echo "[3/3] Building Tauri app..."

cd "$FRONTEND"
npm install --quiet
npm run tauri build

echo ""
echo "=== Build complete! ==="
