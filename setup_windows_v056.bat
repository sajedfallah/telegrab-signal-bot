@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
if errorlevel 1 exit /b 1
echo NEXUS v0.5.6 Python environment is ready.
