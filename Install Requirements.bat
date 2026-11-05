@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py -3"
) else (
    set "PYTHON_CMD=python"
)
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :failed
%PYTHON_CMD% -m playwright install chromium
if errorlevel 1 goto :failed
echo.
echo Setup complete! Double-click Start Extractor.bat to begin.
goto :end
:failed
echo.
echo Setup failed. Make sure Python 3.10+ is installed and try again.
:end
pause
