@echo off
title Naukri Auto-Apply Bot (Edge Edition)
color 0A

echo ===================================================
echo     Starting Naukri Auto-Apply Bot (Edge Edition)
echo ===================================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

python Naukri-Edge.py

echo.
echo ===================================================
echo     Bot run completed or stopped.
echo     Check 'naukriapplied.csv' for the full report!
echo ===================================================
echo.
pause
