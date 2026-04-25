# Neo — Quick sidecar update (backend-only changes)
# Rebuilds the Python sidecar and replaces it in the install dir.
#
# Usage:
#   cd C:\Projects\neo
#   .\scripts\update-sidecar.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Backend = Join-Path $Root "backend"
$InstallDir = Join-Path $env:LOCALAPPDATA "Neo"
$SidecarSrc = Join-Path $Backend "dist" "neo-server-x86_64-pc-windows-msvc.exe"
$SidecarDst = Join-Path $InstallDir "neo-server.exe"

Write-Host "=== Neo Sidecar Update ===" -ForegroundColor Cyan

# Step 1: Kill running Neo processes
Write-Host "`n[1/3] Stopping Neo..." -ForegroundColor Yellow
Stop-Process -Name "neo-desktop" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "Neo" -Force -ErrorAction SilentlyContinue
Get-Process | Where-Object { $_.Name -like "neo-server*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2
Write-Host "  Done."

# Step 2: Rebuild sidecar
Write-Host "`n[2/3] Building sidecar..." -ForegroundColor Yellow
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

# Step 3: Copy to install location
Write-Host "`n[3/3] Updating installed sidecar..." -ForegroundColor Yellow
if (-Not (Test-Path $SidecarSrc)) {
    Write-Host "  ERROR: Build output not found at $SidecarSrc" -ForegroundColor Red
    exit 1
}
Copy-Item $SidecarSrc $SidecarDst -Force
Write-Host "  Updated: $SidecarDst" -ForegroundColor Green

Write-Host "`n=== Sidecar updated! Relaunch Neo from Start Menu. ===" -ForegroundColor Green
