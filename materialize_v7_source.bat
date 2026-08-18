@echo off
setlocal
cd /d "%~dp0"
py -3.11 scripts\materialize_v7_source.py
if errorlevel 1 (
  echo.
  echo [NEXUS] Source materialization failed.
  exit /b 1
)
echo.
echo [NEXUS] Source is ready. Run setup_windows.bat then start_windows.bat.
