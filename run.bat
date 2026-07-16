@echo off
REM Launch the NIDS dashboard.
REM Double-click this file, or run it from a terminal.
REM For LIVE CAPTURE, right-click and choose "Run as administrator".

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo Virtual environment not found. Creating one now...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo.
echo Starting the dashboard. It will open in your browser.
echo Press Ctrl+C in this window to stop it.
echo.

streamlit run nids/app.py

pause
