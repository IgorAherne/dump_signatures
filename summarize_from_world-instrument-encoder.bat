@echo off
REM This script runs the Python code summarization utility.

REM Activate the virtual environment
cd ..\..\

call .\venv\Scripts\activate.bat
if errorlevel 1 (
    echo Failed to activate virtual environment. Exiting.
    pause
    exit /b 1
)

echo Starting Python script to summarize code...

REM Scan the parent directory recursively, relative to this batch file's location
REM You can change it to ..\my_subfolder\some_deeper_subfolder and so on.
REM Output will be CODE_SUMMARY.txt in the current directory.
python submodules\dump_signatures\summarize_code.py --scan_directory .\submodules\aura-world-instrument-encoder

echo.
echo Script execution finished.
pause