@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0"
set "AC=%ROOT%archive_console"
if not exist "%AC%\tray_app.py" (
  echo Missing archive_console\tray_app.py
  exit /b 1
)

cd /d "%AC%"

set "VENV_PY=%AC%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo Creating venv...
  python -m venv ".venv"
  if errorlevel 1 exit /b 1
)

"%VENV_PY%" -m pip install -q -r requirements.txt
if errorlevel 1 exit /b 1

echo Starting tray. First run installs pystray and Pillow if needed.
"%VENV_PY%" tray_app.py
exit /b %ERRORLEVEL%
