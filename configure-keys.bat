@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure-keys.ps1" %*
if errorlevel 1 (
  echo Configuration did not complete. No key values will be displayed.
)
pause
