@echo off
title Multi-Platform Job Auto-Apply Suite
color 0B
setlocal enabledelayedexpansion

:: Navigate to the bot directory
if exist "%~dp0Naukri-Edge.py" (
    cd /d "%~dp0"
) else if exist "%~dp0Naukri-autoapply-bot\Naukri-Edge.py" (
    cd /d "%~dp0Naukri-autoapply-bot"
) else (
    cd /d "%~dp0"
)

:: Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    pause
    exit /b 1
)

:MENU
cls
echo ======================================================================
echo           AUTOMATED MULTI-PLATFORM JOB APPLICATION SUITE
echo ======================================================================
echo.
echo   Select a platform to run:
echo.
echo     [1] Naukri    (Edge Edition)
echo     [2] LinkedIn  (Easy Apply + Entry Level + AI Answers)
echo     [3] Indeed    (Edge Edition)
echo     [4] Foundit   (Monster India Edition)
echo     [5] Run ALL Platforms Sequentially (LinkedIn -^> Naukri -^> Foundit -^> Indeed)
echo     [6] Open Web Dashboard (Live Application Status ^& Today's Results)
echo     [0] Exit
echo.
echo ======================================================================
set choice=
set /p choice="Enter your choice [0-6]: "

if "%choice%"=="" goto MENU
if "%choice%"=="1" goto RUN_NAUKRI
if "%choice%"=="2" goto RUN_LINKEDIN
if "%choice%"=="3" goto RUN_INDEED
if "%choice%"=="4" goto RUN_FOUNDIT
if "%choice%"=="5" goto RUN_ALL
if "%choice%"=="6" goto OPEN_DASHBOARD
if "%choice%"=="0" goto EXIT
echo.
echo [!] Invalid selection, please enter 0, 1, 2, 3, 4, 5, or 6.
timeout /t 2 >nul
goto MENU

:RUN_NAUKRI
cls
echo ======================================================================
echo   [1/2] Opening Web Dashboard: Naukri Section...
echo ======================================================================
start "" python dashboard.py naukri
timeout /t 2 >nul
echo.
echo ======================================================================
echo   [2/2] Launching Naukri Auto-Apply Bot...
echo ======================================================================
python Naukri-Edge.py
echo.
echo Updating Dashboard with latest Naukri applications...
python dashboard.py naukri
echo.
pause
goto MENU

:RUN_LINKEDIN
cls
echo ======================================================================
echo   [1/2] Opening Web Dashboard: LinkedIn Section...
echo ======================================================================
start "" python dashboard.py linkedin
timeout /t 2 >nul
echo.
echo ======================================================================
echo   [2/2] Launching LinkedIn Easy Apply Bot...
echo ======================================================================
python LinkedIn-Edge.py
echo.
echo Updating Dashboard with latest LinkedIn applications...
python dashboard.py linkedin
echo.
pause
goto MENU

:RUN_INDEED
cls
echo ======================================================================
echo   [1/2] Opening Web Dashboard: Indeed Section...
echo ======================================================================
start "" python dashboard.py indeed
timeout /t 2 >nul
echo.
echo ======================================================================
echo   [2/2] Launching Indeed Auto-Apply Bot...
echo ======================================================================
python Indeed-Edge.py
echo.
echo Updating Dashboard with latest Indeed applications...
python dashboard.py indeed
echo.
pause
goto MENU

:RUN_FOUNDIT
cls
echo ======================================================================
echo   [1/2] Opening Web Dashboard: Foundit Section...
echo ======================================================================
start "" python dashboard.py foundit
timeout /t 2 >nul
echo.
echo ======================================================================
echo   [2/2] Launching Foundit Auto-Apply Bot...
echo ======================================================================
python Foundit-Edge.py
echo.
echo Updating Dashboard with latest Foundit applications...
python dashboard.py foundit
echo.
pause
goto MENU

:RUN_ALL
cls
echo ======================================================================
echo   Starting ALL Bots Sequentially
echo ======================================================================
start "" python dashboard.py all
timeout /t 2 >nul

echo.
echo [1/4] Running LinkedIn Easy Apply Bot...
python LinkedIn-Edge.py
python dashboard.py linkedin

echo.
echo [2/4] Running Naukri Bot...
python Naukri-Edge.py
python dashboard.py naukri

echo.
echo [3/4] Running Foundit Bot...
python Foundit-Edge.py
python dashboard.py foundit

echo.
echo [4/4] Running Indeed Bot...
python Indeed-Edge.py
python dashboard.py indeed

echo.
echo ======================================================================
echo   All platform runs completed!
echo ======================================================================
python dashboard.py all
pause
goto MENU

:OPEN_DASHBOARD
cls
echo ======================================================================
echo   Opening Live Application Dashboard in default browser...
echo ======================================================================
python dashboard.py all
timeout /t 2 >nul
goto MENU

:EXIT
cls
echo Exiting Job Auto-Apply Suite. Good luck with your applications!
timeout /t 2 >nul
exit /b 0
