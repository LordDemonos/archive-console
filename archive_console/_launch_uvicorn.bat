@echo off
rem Launched via: start "Archive Console (uvicorn)" cmd /k call "%~f0"
rem Expects parent to set ARCHIVE_CONSOLE_UVICORN_HOST and ARCHIVE_CONSOLE_UVICORN_PORT.
setlocal EnableExtensions
cd /d "%~dp0"

set "H=%ARCHIVE_CONSOLE_UVICORN_HOST%"
set "P=%ARCHIVE_CONSOLE_UVICORN_PORT%"
if not defined H set "H=127.0.0.1"
if not defined P set "P=8756"

if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv\Scripts\python.exe — run start_archive_console.bat from repo root once to create the venv.
  exit /b 2
)

".venv\Scripts\python.exe" -m uvicorn app.main:app --host %H% --port %P% --log-level info
exit /b %ERRORLEVEL%
