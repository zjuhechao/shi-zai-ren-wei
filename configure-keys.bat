@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" backend\scripts\configure_secrets.py
) else (
  py -3 backend\scripts\configure_secrets.py
)
pause
