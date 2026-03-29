@echo off
REM DEPRECATED: use monthly_watch_later_archive.bat (same behavior). This file remains
REM so Task Scheduler, shortcuts, and old docs paths keep working.
echo.
echo NOTE: archive_playlists_advanced.bat is deprecated.
echo       Use monthly_watch_later_archive.bat ^(see BAT_FILES.md^).
echo.
call "%~dp0monthly_watch_later_archive.bat" %*
exit /b %errorlevel%
