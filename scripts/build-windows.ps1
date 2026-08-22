# build lazycatter windows desktop app (folder build under dist/LazyCatter)
# run from repo root in powershell:
#   powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    Write-Error "Python is not on PATH. Install Python 3.12+ from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'."
}

Write-Host "Installing desktop build dependencies..."
python -m pip install --upgrade pip
python -m pip install -r bot/requirements-desktop.txt

Write-Host "Building LazyCatter.exe with PyInstaller..."
if (Test-Path "$Root\dist\LazyCatter") {
    Remove-Item "$Root\dist\LazyCatter" -Recurse -Force
}
python -m PyInstaller --noconfirm --clean desktop/lazycatter.spec

if (-not (Test-Path "$Root\dist\LazyCatter\LazyCatter.exe")) {
    Write-Error "Build finished but dist\LazyCatter\LazyCatter.exe is missing."
}

Write-Host ""
Write-Host "Build ok: $Root\dist\LazyCatter\LazyCatter.exe"
Write-Host "Next: powershell -ExecutionPolicy Bypass -File desktop/install.ps1"
