@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 capture_preview.py
) else (
    python capture_preview.py
)
echo.
pause
