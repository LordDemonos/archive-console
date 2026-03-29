@echo off
cd /d "%~dp0"
echo ========================================
echo  Monthly / batch video list archive
echo ========================================
echo.
echo Primary driver for ad-hoc or batch URLs in videos_input.txt.
echo Same stack as monthly_watch_later_archive.bat: yt-dlp.conf, cookies, EJS,
echo per-run logs under logs\archive_run_^<UTC^>\, verification before archiving IDs.
echo.
echo Input: videos_input.txt — one http(s) URL or "youtube VIDEO_ID" per line (# comments ok^).
echo Output: videos\^(uploader^).100B\...
echo Pointer: logs\latest_run_videos.txt — playlist uses latest_run.txt; channels use latest_run_channel.txt.
echo.
echo This script includes:
echo - File size verification after download ^(same as playlist/channel drivers^)
echo - Deferred videos_downloaded.txt ^(only verified completes^)
echo - Per-run manifest, issues, summary.txt, report.html
echo.
if /i not "%ARCHIVE_CONSOLE_UNATTENDED%"=="1" (
    echo Press any key to start...
    pause >nul
)

:download_start
echo.
echo Starting video list archive run...
echo.
echo Environment toggles ^(optional^):
echo   SKIP_PIP_UPDATE=1           skip pip self-upgrade ^(default when unset^)
echo   SKIP_YTDLP_UPDATE=1          skip yt-dlp pip install before run
echo   ARCHIVE_DRY_RUN=1            pass --simulate to yt-dlp
echo   ARCHIVE_PAUSE_ON_COOKIE_ERROR=1   pause on likely cookie/auth yt-dlp lines ^(see logs^)
echo   ARCHIVE_COOKIE_AUTH_POLL_SEC=N    optional mtime poll on cookies.txt every N seconds
echo   Cookie source: edit yt-dlp.conf ^(--cookies file vs --cookies-from-browser^)
echo   ARCHIVE_OUT_VIDEOS=     optional: output root for video list ^(set by Archive Console^)
echo   ARCHIVE_PIP_VERBOSE=1        full pip output ^(default: pip -q for less spam^)
echo.

if /i "%ARCHIVE_PIP_VERBOSE%"=="1" (
    set "ARCHIVE_PIP_QUIET="
) else (
    set "ARCHIVE_PIP_QUIET=-q"
)

if defined ARCHIVE_OUT_VIDEOS (
    echo [archive] ARCHIVE_OUT_VIDEOS set — video list downloads use that folder tree.
)

if not defined SKIP_PIP_UPDATE set "SKIP_PIP_UPDATE=1"
if /i "%SKIP_PIP_UPDATE%"=="1" (
    python "%~dp0archive_print_role.py" skip "[archive] Skipping pip self-upgrade (SKIP_PIP_UPDATE=1)"
) else (
    echo [archive] Upgrading pip ^(python -m pip install --upgrade pip^)...
    python -m pip install %ARCHIVE_PIP_QUIET% --upgrade pip --disable-pip-version-check
    if errorlevel 1 (
        python "%~dp0archive_print_role.py" warn "WARNING: [archive] pip self-upgrade failed; continuing with existing pip."
    ) else (
        python "%~dp0archive_print_role.py" ok "[archive] pip self-upgrade finished OK."
    )
    echo.
)

if /i "%SKIP_YTDLP_UPDATE%"=="1" (
    python "%~dp0archive_print_role.py" skip "Skipping yt-dlp update (SKIP_YTDLP_UPDATE=1)"
) else (
    echo Updating yt-dlp via pip ^(includes yt-dlp-ejs for YouTube challenges^)...
    python -m pip install %ARCHIVE_PIP_QUIET% -U --disable-pip-version-check "yt-dlp[default]"
    if errorlevel 1 (
        python "%~dp0archive_print_role.py" warn "WARNING: pip could not update yt-dlp; continuing with the already-installed version."
    ) else (
        python "%~dp0archive_print_role.py" ok "[archive] yt-dlp pip update finished OK."
    )
    echo.
)

if exist "videos_downloaded.txt" (
    copy "videos_downloaded.txt" "videos_downloaded_backup.txt" >nul
    echo Created backup of videos_downloaded.txt
)

echo Per-run logs: logs\archive_run_^<UTC_time^>\
echo Video pointer: logs\latest_run_videos.txt
echo Playlist pointer: logs\latest_run.txt
echo Channel pointer: logs\latest_run_channel.txt
echo Checklist / failure families: ARCHIVE_PLAYLIST_RUN_LOGS.txt
echo.

python "%~dp0archive_video_run.py"
set "YTDLP_RC=%ERRORLEVEL%"

set "LOGDIR="
if exist "logs\latest_run_videos.txt" (
    set /p LOGDIR=<logs\latest_run_videos.txt
)
if defined LOGDIR (
    echo.
    echo Latest video-list run log directory:
    echo   %LOGDIR%
) else (
    echo.
    echo Latest video-list run log directory: see Python output above
)

if not "%YTDLP_RC%"=="0" (
    echo.
    echo ========================================
    echo  Video list archive completed with errors
    echo ========================================
    echo.
    call :print_log_paths
    echo See ARCHIVE_PLAYLIST_RUN_LOGS.txt ^(video list section^).
    echo.
    echo Press any key to exit...
    if /i not "%ARCHIVE_CONSOLE_UNATTENDED%"=="1" pause >nul
) else (
    echo.
    echo ========================================
    echo  Video list archive finished ^(exit 0^)
    echo ========================================
    echo.
    echo See manifest for verified downloads; archive file updated only for verified files.
    echo.
    call :print_log_paths
    echo See ARCHIVE_PLAYLIST_RUN_LOGS.txt ^(video list section^).
    echo.
    echo Press any key to exit...
    if /i not "%ARCHIVE_CONSOLE_UNATTENDED%"=="1" pause >nul
)

exit /b %YTDLP_RC%

:print_log_paths
if defined LOGDIR (
    echo See: "%LOGDIR%\manifest.csv"
    echo See: "%LOGDIR%\issues.csv"
    echo See: "%LOGDIR%\summary.txt"
    echo See: "%LOGDIR%\report.html"
    echo See: "%LOGDIR%\rerun_urls.txt"
    echo See: "%LOGDIR%\run.log"
) else (
    echo See logs\latest_run_videos.txt then manifest.csv, issues.csv, etc.
)
exit /b 0
