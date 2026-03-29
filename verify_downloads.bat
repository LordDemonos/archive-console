@echo off
cd /d "%~dp0"
echo ========================================
echo  Download Verification Tool
echo ========================================
echo.
echo This script will verify your downloads and
echo check the archive file integrity.
echo.

echo Checking playlist downloads...
if exist "playlists\WL" (
    echo Found Watch Later folder
    dir "playlists\WL" /b | find /c ".mp4" > temp_count.txt
    set /p video_count=<temp_count.txt
    del temp_count.txt
    echo Found %video_count% downloaded videos
) else (
    echo No Watch Later folder found
)

echo.
echo Checking archive file...
if exist "playlists_downloaded.txt" (
    find /c "youtube" "playlists_downloaded.txt" > temp_archive.txt
    set /p archive_count=<temp_archive.txt
    del temp_archive.txt
    echo Archive contains %archive_count% entries
) else (
    echo No archive file found
)

echo.
echo ========================================
echo  Verification Complete
echo ========================================
echo.
echo If the numbers don't match, some videos
echo may have failed to download or weren't
echo properly added to the archive.
echo.
echo You can restart the download script to
echo continue downloading missing videos.
echo.
pause 