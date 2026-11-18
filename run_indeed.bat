@echo off
title Indeed Auto-Apply Bot (Edge Edition)
color 0E

echo ===================================================
echo     Starting Indeed Auto-Apply Bot (Edge Edition)
echo ===================================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

python Indeed-Edge.py

echo.
echo ===================================================
echo     Bot run completed or stopped.
echo     Check 'indeedapplied.csv' for the full report!
echo ===================================================
echo.
pause
