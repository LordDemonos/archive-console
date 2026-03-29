@echo off
REM DEPRECATED: use monthly_channels_archive.bat (same behavior). This file remains
REM so Task Scheduler, shortcuts, and old paths keep working.
echo.
echo NOTE: archive_youtube_channels.bat is deprecated.
echo       Use monthly_channels_archive.bat ^(see BAT_FILES.md^).
echo.
call "%~dp0monthly_channels_archive.bat" %*
exit /b %errorlevel%
