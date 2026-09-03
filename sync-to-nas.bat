@echo off
REM Refresh the read-only GitHub mirror on the NAS. Run after `git push`.
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" sync_to_nas.py
) else (
    python sync_to_nas.py
)
endlocal
pause
