@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-app.ps1" %*
set "appExitCode=%errorlevel%"
if not "%appExitCode%"=="0" (
  echo Startup failed. Read the message above and the included getting-started guide.
)
pause
exit /b %appExitCode%
