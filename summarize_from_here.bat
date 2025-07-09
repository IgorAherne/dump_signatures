@echo off
REM This script runs the Python code summarization utility.

REM Activate the virtual environment
call .\venv\Scripts\activate.bat
if errorlevel 1 (
    echo Failed to activate virtual environment. Exiting.
    pause
    exit /b 1
)

echo Starting Python script to summarize code...

REM Scan the current directory, recursively.
REM You can instead change it to .\my_subfolder\some_deeper_subfolder and so on.
REM Output will be CODE_SUMMARY.txt in the current directory.
python summarize_code.py --scan_directory .

echo.
echo Script execution finished.
pause