@echo off
REM Shared by monthly_*_archive.bat — same interpreter as Archive Console (.venv).
set "ARCHIVE_PY=%~dp0archive_console\.venv\Scripts\python.exe"
if not exist "%ARCHIVE_PY%" (
  set "ARCHIVE_PY=python"
)
