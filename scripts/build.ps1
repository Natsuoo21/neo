# Neo — Windows build script (PowerShell)
# Builds PyInstaller sidecar + Tauri desktop app.
#
# Prerequisites:
#   - Python 3.12+ with pip
#   - Rust (rustup)
#   - Node.js 20+
#   - PyInstaller: pip install pyinstaller
#
# Usage:
#   .\scripts\build.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Binaries = Join-Path $Frontend "src-tauri" "binaries"

Write-Host "=== Neo Build Script ===" -ForegroundColor Cyan

# Step 1: Build Python sidecar with PyInstaller
Write-Host "`n[1/3] Building Python sidecar..." -ForegroundColor Yellow

Push-Location $Backend
try {
    if (-Not (Test-Path ".venv")) {
        python -m venv .venv
    }
    & .venv\Scripts\Activate.ps1
    pip install -r requirements.txt --quiet
    pip install pyinstaller --quiet
    pyinstaller neo-server.spec --noconfirm --clean
} finally {
    Pop-Location
}

# Step 2: Copy sidecar binary to Tauri binaries dir
Write-Host "`n[2/3] Copying sidecar to Tauri binaries..." -ForegroundColor Yellow

if (-Not (Test-Path $Binaries)) {
    New-Item -ItemType Directory -Path $Binaries -Force | Out-Null
}

$SidecarSrc = Join-Path $Backend "dist" "neo-server-x86_64-pc-windows-msvc.exe"
$SidecarDst = Join-Path $Binaries "neo-server-x86_64-pc-windows-msvc.exe"

if (Test-Path $SidecarSrc) {
    Copy-Item $SidecarSrc $SidecarDst -Force
    Write-Host "  Copied: $SidecarDst"
} else {
    Write-Host "  ERROR: Sidecar not found at $SidecarSrc" -ForegroundColor Red
    exit 1
}

# Step 3: Build Tauri app
Write-Host "`n[3/3] Building Tauri app..." -ForegroundColor Yellow

Push-Location $Frontend
try {
    npm install --quiet
    npm run tauri build
} finally {
    Pop-Location
}

Write-Host "`n=== Build complete! ===" -ForegroundColor Green

$Installer = Get-ChildItem -Path (Join-Path $Frontend "src-tauri" "target" "release" "bundle") -Recurse -Filter "*.msi" | Select-Object -First 1
if ($Installer) {
    Write-Host "Installer: $($Installer.FullName)" -ForegroundColor Cyan
}
