@echo off
setlocal
cd /d "%~dp0"
for %%F in (nexus_bot.db nexus_bot.db-wal nexus_bot.db-shm) do if exist "%%F" del /f /q "%%F" >nul 2>&1
echo NEXUS v0.6.4 fresh database state prepared.
echo First signal will be NX-0001 after the backend initializes the DB.
endlocal
