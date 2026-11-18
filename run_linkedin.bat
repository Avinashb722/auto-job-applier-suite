@echo off
title LinkedIn Easy Apply Bot (Edge Edition)
color 09

echo ===================================================
echo     Starting LinkedIn Easy Apply Bot (Edge Edition)
echo ===================================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

python LinkedIn-Edge.py

echo.
echo ===================================================
echo     Bot run completed or stopped.
echo     Check 'linkedinapplied.csv' for the full report!
echo ===================================================
echo.
pause
