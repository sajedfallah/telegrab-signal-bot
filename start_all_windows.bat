@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [NEXUS] .venv not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
start "NEXUS AutoTrade API" cmd /k ""%~dp0.venv\Scripts\python.exe" "%~dp0run_api.py""
ping 127.0.0.1 -n 3 >nul
start "NEXUS Telegram Bot" cmd /k ""%~dp0.venv\Scripts\python.exe" "%~dp0run.py""
