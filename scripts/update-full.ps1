# Neo — Full update (backend + frontend)
# Rebuilds sidecar, Tauri app, and runs the NSIS installer.
#
# Usage:
#   cd C:\Projects\neo
#   .\scripts\update-full.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Binaries = Join-Path (Join-Path $Frontend "src-tauri") "binaries"

Write-Host "=== Neo Full Update ===" -ForegroundColor Cyan

# Step 1: Kill running Neo processes
Write-Host "`n[1/5] Stopping Neo..." -ForegroundColor Yellow
Stop-Process -Name "neo-desktop" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "Neo" -Force -ErrorAction SilentlyContinue
Get-Process | Where-Object { $_.Name -like "neo-server*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2
Write-Host "  Done."

# Step 2: Rebuild sidecar
Write-Host "`n[2/5] Building sidecar..." -ForegroundColor Yellow
Push-Location $Backend
try {
    $VenvPyInstaller = Join-Path ".venv-win" "Scripts" "pyinstaller.exe"
    if (-Not (Test-Path $VenvPyInstaller)) {
        Write-Host "  Installing PyInstaller..." -ForegroundColor Gray
        & .venv-win\Scripts\pip.exe install pyinstaller --quiet
    }
    & $VenvPyInstaller neo-server.spec --noconfirm --clean
} finally {
    Pop-Location
}

# Step 3: Copy sidecar to Tauri binaries
Write-Host "`n[3/5] Copying sidecar to Tauri binaries..." -ForegroundColor Yellow
if (-Not (Test-Path $Binaries)) {
    New-Item -ItemType Directory -Path $Binaries -Force | Out-Null
}
$SidecarSrc = Join-Path $Backend "dist" "neo-server-x86_64-pc-windows-msvc.exe"
$SidecarDst = Join-Path $Binaries "neo-server-x86_64-pc-windows-msvc.exe"
if (-Not (Test-Path $SidecarSrc)) {
    Write-Host "  ERROR: Sidecar not found at $SidecarSrc" -ForegroundColor Red
    exit 1
}
Copy-Item $SidecarSrc $SidecarDst -Force
Write-Host "  Copied."

# Step 4: Build Tauri app
Write-Host "`n[4/5] Building Tauri app..." -ForegroundColor Yellow
Push-Location $Frontend
try {
    npm install --quiet 2>&1 | Out-Null
    npm run tauri build
} finally {
    Pop-Location
}

# Step 5: Run installer
Write-Host "`n[5/5] Running installer..." -ForegroundColor Yellow
$Installer = Get-ChildItem -Path (Join-Path $Frontend "src-tauri" "target" "release" "bundle" "nsis") -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($Installer) {
    Write-Host "  Launching: $($Installer.FullName)" -ForegroundColor Cyan
    Start-Process $Installer.FullName -Wait
    Write-Host "`n=== Neo updated! ===" -ForegroundColor Green
} else {
    Write-Host "  WARNING: NSIS installer not found. Check build output." -ForegroundColor Yellow
    Write-Host "  You can install manually from: $Frontend\src-tauri\target\release\bundle\" -ForegroundColor Yellow
}
