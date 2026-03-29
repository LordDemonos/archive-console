@echo off
cd /d "%~dp0"
echo.
echo DEPRECATED: archive_channels_robust.bat was the legacy direct yt-dlp wrapper.
echo Use monthly_channels_archive.bat (Python driver + verification + reporting).
echo.
call "%~dp0monthly_channels_archive.bat" %*
exit /b %errorlevel%
