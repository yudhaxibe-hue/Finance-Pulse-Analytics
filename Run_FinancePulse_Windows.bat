@echo off
rem ==============================================================================
rem Finance Pulse Analytics - 1-Click Windows Launcher
rem Double-click in Explorer to start locally in a native desktop window.
rem ==============================================================================

title Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform
cd /d "%~dp0"
cls

echo ==================================================================
echo   Finance Pulse Analytics
echo   Enterprise Financial Performance Intelligence ^&
echo   Profitability Optimization Analytics Platform
echo ==================================================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "VENV_DIR=.venv"
    goto :run
)
if exist "venv\Scripts\python.exe" (
    set "VENV_DIR=venv"
    goto :run
)

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3 is not installed on this Windows PC.
    echo Download the standalone pre-packaged Windows ZIP from GitHub Releases.
    pause
    exit /b 1
)

set "VENV_DIR=.venv"
echo [1/2] Initializing local virtual environment (first run only)...
python -m venv "%VENV_DIR%"
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements-desktop.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Local environment ready.
echo.

:run
echo [2/2] Starting Finance Pulse Analytics...
"%VENV_DIR%\Scripts\python.exe" -m app_launcher %*
if %errorlevel% neq 0 (
    echo.
    echo [NOTICE] Application exited cleanly or closed with an error.
    pause
)
