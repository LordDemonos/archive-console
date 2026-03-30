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
set "VENV_PYW=%AC%\.venv\Scripts\pythonw.exe"
if not exist "%VENV_PY%" (
  echo Creating venv...
  python -m venv ".venv"
  if errorlevel 1 exit /b 1
)

if not exist "%VENV_PYW%" (
  echo ERROR: "%VENV_PYW%" not found. Re-create the venv with: python -m venv ".venv"
  exit /b 1
)

"%VENV_PY%" -m pip install -q -r requirements.txt
if errorlevel 1 exit /b 1

rem Tray UI: pythonw has no console — mandatory for Explorer double-click (no lingering CMD).
rem "start" detaches so this batch window can exit immediately after a successful launch.
start "" /D "%AC%" "%VENV_PYW%" tray_app.py
exit /b 0
