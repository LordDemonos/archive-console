@echo off
rem Wrapper: repo layout has launcher at scripts\start_archive_console.bat — this jumps there.
setlocal EnableExtensions
cd /d "%~dp0.."
call start_archive_console.bat %*
