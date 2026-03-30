@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: oneoff_archive.bat ^<UTC_log_stamp^>
  echo Archive Console sets ARCHIVE_ONEOFF_URL and runs: python -u archive_oneoff_run.py ^<stamp^>
  exit /b 1
)
python -u archive_oneoff_run.py %1
