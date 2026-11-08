@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
title PS5 FFPFSC PRO v1.3.0 (Git Auto-Update)
cd /d "%~dp0"

echo ===================================================
echo   PS5 FFPFSC PRO - Git Pull ^& Launcher
echo ===================================================
echo.
echo [1/3] Pulling latest updates from Git...
git pull
if errorlevel 1 (
    echo.
    echo [WARNING] Git pull encountered an issue. Continuing with current local files...
)
echo.
echo [2/3] Checking dependencies...
py -m pip install -r requirements.txt --quiet
if errorlevel 1 python -m pip install -r requirements.txt --quiet
echo.
echo [3/3] Launching PS5 FFPFSC PRO...
py PS5_FFPFSC_PRO_v1.3.0.py
if errorlevel 1 python PS5_FFPFSC_PRO_v1.3.0.py
if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
