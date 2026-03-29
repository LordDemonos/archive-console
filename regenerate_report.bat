@echo off
REM Rebuild report.html from manifest/issues: .csv and/or legacy .tsv (see read_manifest_issues_from_disk).
cd /d "%~dp0"
python "%~dp0regenerate_report.py" %*
if %errorlevel% neq 0 pause
