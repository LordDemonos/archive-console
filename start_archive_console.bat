@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0"
set "AC=%ROOT%archive_console"
if not exist "%AC%\app\main.py" (
  echo Missing archive_console\app\main.py under:
  echo   %ROOT%
  exit /b 1
)

cd /d "%AC%"

set "VENV_PY=%AC%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo Creating venv...
  python -m venv ".venv"
  if errorlevel 1 (
    echo python -m venv failed. Is Python 3.10+ on PATH?
    exit /b 1
  )
)

"%VENV_PY%" -m pip install -q -r requirements.txt
if errorlevel 1 exit /b 1

set "AC_HOST="
set "AC_PORT="
for /f "tokens=1,2" %%A in ('"%VENV_PY%" print_bind.py') do (
  set "AC_HOST=%%A"
  set "AC_PORT=%%B"
)

if not defined AC_HOST set "AC_HOST=127.0.0.1"
if not defined AC_PORT set "AC_PORT=8756"
if "!AC_HOST!"=="" set "AC_HOST=127.0.0.1"
if "!AC_PORT!"=="" set "AC_PORT=8756"

"%VENV_PY%" -c "import urllib.request; urllib.request.urlopen('http://!AC_HOST!:!AC_PORT!/api/health', timeout=2)" 1>nul 2>nul
if not errorlevel 1 (
  start "" "http://!AC_HOST!:!AC_PORT!/"
  exit /b 0
)

rem Health failed: if something is still listening, offer safe kill (narrow uvicorn match).
powershell -NoProfile -ExecutionPolicy Bypass -File "%AC%\port_busy.ps1" -Port !AC_PORT!
if errorlevel 1 goto :AC_LAUNCH

echo.
echo Port !AC_PORT! is in use but http://!AC_HOST!:!AC_PORT!/api/health did not respond.
if /i "!ARCHIVE_CONSOLE_REPLACE!"=="1" (
  echo ARCHIVE_CONSOLE_REPLACE=1 - stopping prior uvicorn on this port...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%AC%\stop_server.ps1" -Port !AC_PORT! -Force
  if errorlevel 1 exit /b 1
  goto :AC_LAUNCH
)

choice /C YN /M "Kill Archive Console uvicorn on port !AC_PORT! and start a new server"
if errorlevel 2 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%AC%\stop_server.ps1" -Port !AC_PORT! -Force
if errorlevel 1 exit /b 1

:AC_LAUNCH
if /i "!ARCHIVE_CONSOLE_ATTACHED!"=="1" (
  echo.
  echo ARCHIVE_CONSOLE_ATTACHED=1 — uvicorn runs in THIS window. Ctrl+C stops the server.
  echo Closing the browser tab does NOT stop the server.
  echo.
  "%VENV_PY%" -m uvicorn app.main:app --host !AC_HOST! --port !AC_PORT! --log-level info
  exit /b !ERRORLEVEL!
)

rem Dedicated console: helper avoids fragile "cmd /k cd ... && quoted python.exe ..." parsing
rem (which can make CMD pass python.exe as a script and yield SyntaxError on MZ header).
set "ARCHIVE_CONSOLE_UVICORN_HOST=!AC_HOST!"
set "ARCHIVE_CONSOLE_UVICORN_PORT=!AC_PORT!"
start "Archive Console (uvicorn)" cmd /k call "%AC%\_launch_uvicorn.bat"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 3"

start "" "http://!AC_HOST!:!AC_PORT!/"
exit /b 0
