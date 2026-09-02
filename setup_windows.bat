@echo off
cd /d "%~dp0"
echo [NEXUS] Creating Python 3.11 virtual environment...
py -3.11 -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip --timeout 120 --retries 10
python -m pip install -r requirements.txt --timeout 120 --retries 10
echo.
echo [NEXUS] Setup completed.
echo [NEXUS] Use start_all_windows.bat to launch API and Telegram Bot.
pause
