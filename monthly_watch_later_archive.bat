@echo off
cd /d "%~dp0"
echo ========================================
echo  Monthly Watch Later archive (playlists)
echo ========================================
echo.
echo Primary driver for monthly Watch Later saves. You can also
echo list normal playlist or channel URLs in playlists_input.txt.
echo.
echo This script includes:
echo - File size verification after download
echo - Detailed progress tracking
echo - Rate limiting prevention (8s delays)
echo - Archive integrity checking
echo - Resume capability for large Watch Later lists
echo - Per-run logs under logs\archive_run_^<UTC_timestamp^>\
echo.
if /i not "%ARCHIVE_CONSOLE_UNATTENDED%"=="1" (
    echo Press any key to start...
    pause >nul
)

:download_start
echo.
echo Starting playlist archive run...
echo.
echo Environment toggles ^(optional^):
echo   SKIP_PIP_UPDATE=1    skip pip self-upgrade ^(default when unset^)
echo   SKIP_YTDLP_UPDATE=1   skip yt-dlp pip install before run
echo   ARCHIVE_DRY_RUN=1     pass --simulate to yt-dlp ^(no real downloads; see ARCHIVE_PLAYLIST_RUN_LOGS.txt^)
echo   ARCHIVE_PAUSE_ON_COOKIE_ERROR=1   pause on likely cookie/auth yt-dlp lines ^(see logs^)
echo   ARCHIVE_COOKIE_AUTH_POLL_SEC=N      optional mtime poll on cookies.txt every N seconds
echo   Cookie source: edit yt-dlp.conf ^(--cookies file vs --cookies-from-browser^)
echo   ARCHIVE_OUT_PLAYLIST=   optional: output root for playlists ^(set by Archive Console^)
echo   ARCHIVE_PIP_VERBOSE=1        full pip output ^(default: pip -q for less spam^)
echo.

if /i "%ARCHIVE_PIP_VERBOSE%"=="1" (
    set "ARCHIVE_PIP_QUIET="
) else (
    set "ARCHIVE_PIP_QUIET=-q"
)

if defined ARCHIVE_OUT_PLAYLIST (
    echo [archive] ARCHIVE_OUT_PLAYLIST set — playlist downloads use that folder tree.
)

REM pip self-upgrade first (when enabled), then yt-dlp. Same python.exe as below.
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

REM Keep yt-dlp current (YouTube changes often). Uses the same Python as below.
REM To skip: set SKIP_YTDLP_UPDATE=1 for this session, or comment out the next block.
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

REM Create backup of archive file
if exist "playlists_downloaded.txt" (
    copy "playlists_downloaded.txt" "playlists_downloaded_backup.txt" >nul
    echo Created backup of archive file
)

echo Per-run logs: logs\archive_run_^<UTC_time^>\  (run id chosen by Python^)
echo Pointer file: logs\latest_run.txt
echo Monthly checklist: ARCHIVE_PLAYLIST_RUN_LOGS.txt
echo.

python "%~dp0archive_playlist_run.py"
set "YTDLP_RC=%ERRORLEVEL%"

set "LOGDIR="
if exist "logs\latest_run.txt" (
    set /p LOGDIR=<logs\latest_run.txt
)
if defined LOGDIR (
    echo.
    echo Latest run log directory:
    echo   %LOGDIR%
) else (
    echo.
    echo Latest run log directory: see Python output above ^(logs\latest_run.txt missing^)
)

if not "%YTDLP_RC%"=="0" (
    echo.
    echo ========================================
    echo  Download completed with errors
    echo ========================================
    echo.
    echo Some videos may have failed due to:
    echo - Rate limiting ^(normal for large lists^)
    echo - Unavailable videos
    echo - Network issues
    echo.
    echo Only successfully downloaded videos were
    echo added to the archive file.
    echo.
    call :print_log_paths
    echo See: ARCHIVE_PLAYLIST_RUN_LOGS.txt for verification tips.
    echo.
    echo You can restart this script to continue
    echo downloading remaining videos.
    echo.
    echo Press any key to exit...
    if /i not "%ARCHIVE_CONSOLE_UNATTENDED%"=="1" pause >nul
) else (
    echo.
    echo ========================================
    echo  All downloads completed successfully!
    echo ========================================
    echo.
    echo All videos have been downloaded and verified.
    echo Archive file has been updated.
    echo.
    call :print_log_paths
    echo See: ARCHIVE_PLAYLIST_RUN_LOGS.txt for verification tips.
    echo.
    echo Press any key to exit...
    if /i not "%ARCHIVE_CONSOLE_UNATTENDED%"=="1" pause >nul
)

exit /b %YTDLP_RC%

:print_log_paths
if defined LOGDIR (
    echo See: "%LOGDIR%\manifest.csv"   ^(downloaded rows + file_verified_ok^)
    echo See: "%LOGDIR%\issues.csv"     ^(skipped / failed / unavailable^)
    echo See: "%LOGDIR%\summary.txt"    ^(counts^)
    echo See: "%LOGDIR%\report.html"    ^(static summary + tables^)
    echo See: "%LOGDIR%\rerun_urls.txt"
    echo See: "%LOGDIR%\run.log"
) else (
    echo See logs\latest_run.txt then open manifest.csv, issues.csv, summary.txt, report.html
)
exit /b 0
