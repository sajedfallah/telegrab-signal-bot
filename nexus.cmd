@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if /I "%~1"=="status" goto status
if /I "%~1"=="test" goto test
if /I "%~1"=="logs" goto logs
if /I "%~1"=="path" goto path
if /I "%~1"=="restart" goto restart
if /I "%~1"=="help" goto help
:help
echo NEXUS v0.6.0 commands:
echo   nexus status   - services + API health
echo   nexus test     - full pytest suite
echo   nexus logs     - service logs
echo   nexus path     - configured service paths
echo   nexus restart  - restart both services
exit /b 0
:status
sc.exe query NEXUS-AutoTrade-API | findstr /I "STATE"
sc.exe query NEXUS-Telegram-Bot | findstr /I "STATE"
powershell -NoProfile -Command "try {$r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/v1/autotrade/health -TimeoutSec 5; Write-Host ('HTTP: '+$r.StatusCode); Write-Host $r.Content} catch {Write-Host ('ERROR: '+$_.Exception.Message)}"
exit /b 0
:test
if not exist "%PY%" (echo .venv not found&exit /b 1)
"%PY%" -m pytest -q
exit /b %ERRORLEVEL%
:logs
if exist "%~dp0telegram_bot_stderr.log" type "%~dp0telegram_bot_stderr.log"
if exist C:\NEXUS_API_stderr.log type C:\NEXUS_API_stderr.log
exit /b 0
:path
nssm.exe dump NEXUS-AutoTrade-API
nssm.exe dump NEXUS-Telegram-Bot
exit /b 0
:restart
nssm.exe stop NEXUS-Telegram-Bot
nssm.exe stop NEXUS-AutoTrade-API
nssm.exe start NEXUS-AutoTrade-API
nssm.exe start NEXUS-Telegram-Bot
exit /b 0
