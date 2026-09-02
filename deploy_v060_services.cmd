@echo off
setlocal
cd /d "%~dp0"
set "ROOT=%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [NEXUS] .venv not found. Run setup_windows.bat first.
  exit /b 1
)

echo [NEXUS] Stopping services...
nssm.exe stop NEXUS-Telegram-Bot >nul 2>&1
nssm.exe stop NEXUS-AutoTrade-API >nul 2>&1

echo [NEXUS] Configuring API service...
nssm.exe set NEXUS-AutoTrade-API Application "%PY%"
nssm.exe set NEXUS-AutoTrade-API AppParameters run_api.py
nssm.exe set NEXUS-AutoTrade-API AppDirectory "%ROOT%"
nssm.exe set NEXUS-AutoTrade-API AppExit Default Restart
nssm.exe set NEXUS-AutoTrade-API AppStdout C:\NEXUS_API_stdout.log
nssm.exe set NEXUS-AutoTrade-API AppStderr C:\NEXUS_API_stderr.log
nssm.exe set NEXUS-AutoTrade-API Start SERVICE_AUTO_START

 echo [NEXUS] Configuring Telegram service (reporting/subscription only)...
nssm.exe set NEXUS-Telegram-Bot Application "%PY%"
nssm.exe set NEXUS-Telegram-Bot AppParameters run.py
nssm.exe set NEXUS-Telegram-Bot AppDirectory "%ROOT%"
nssm.exe set NEXUS-Telegram-Bot AppExit Default Restart
nssm.exe set NEXUS-Telegram-Bot AppStdout "%ROOT%telegram_bot_stdout.log"
nssm.exe set NEXUS-Telegram-Bot AppStderr "%ROOT%telegram_bot_stderr.log"
nssm.exe set NEXUS-Telegram-Bot Start SERVICE_AUTO_START

nssm.exe start NEXUS-AutoTrade-API
nssm.exe start NEXUS-Telegram-Bot

echo.
echo [NEXUS] Services configured for v0.6.0
sc.exe query NEXUS-AutoTrade-API | findstr /I "STATE"
sc.exe query NEXUS-Telegram-Bot | findstr /I "STATE"
endlocal
