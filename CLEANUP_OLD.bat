@echo off
REM ---------------------------------------------------------------------
REM Removes files left over from the previous folder layout.
REM
REM The old layout had app.py, core, views, components and theme.py sitting
REM at the top level. They now live inside the nids package, so the copies at
REM the top level are stale. Python will not import them, but leaving them
REM there invites running the wrong app.py by mistake.
REM
REM This does NOT touch .venv, and it does NOT touch the new nids folder.
REM ---------------------------------------------------------------------

cd /d "%~dp0"

echo Removing stale top-level copies from the old layout...

if exist "app.py"        del /q "app.py"
if exist "theme.py"      del /q "theme.py"
if exist "__init__.py"   del /q "__init__.py"
if exist "core"          rmdir /s /q "core"
if exist "views"         rmdir /s /q "views"
if exist "components"    rmdir /s /q "components"
if exist "models"        echo Keeping models\ (your trained model may be there)
if exist "data"          echo Keeping data\ (your detection log is there)
if exist "__pycache__"   rmdir /s /q "__pycache__"

echo.
echo Done. Your .venv is untouched.
echo.
echo Now run:
echo     .venv\Scripts\activate
echo     streamlit run nids/app.py
echo.
pause
