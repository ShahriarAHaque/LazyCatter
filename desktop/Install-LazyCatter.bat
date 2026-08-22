@echo off
REM double-click friendly bootstrap
REM build if needed then install + desktop shortcut
setlocal
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
  echo Install Python 3.12+ from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH", then run this again.
  pause
  exit /b 1
)

if not exist "dist\LazyCatter\LazyCatter.exe" (
  echo Building LazyCatter desktop app...
  powershell -ExecutionPolicy Bypass -File "scripts\build-windows.ps1"
  if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
  )
)

echo Installing LazyCatter and creating desktop shortcut...
powershell -ExecutionPolicy Bypass -File "desktop\install.ps1"
if errorlevel 1 (
  echo Install failed.
  pause
  exit /b 1
)

echo.
echo Done. Use the LazyCatter shortcut on your desktop.
pause
