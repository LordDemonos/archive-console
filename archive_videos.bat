@echo off
cd /d "%~dp0"
echo.
echo DEPRECATED: archive_videos.bat was a legacy direct yt-dlp one-liner (no manifest/verify).
echo Use monthly_videos_archive.bat — same yt-dlp.conf stack as Watch Later and channels.
echo.
call "%~dp0monthly_videos_archive.bat" %*
