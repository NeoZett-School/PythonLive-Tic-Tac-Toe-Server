@echo off
title Launcher
setlocal EnableDelayedExpansion

set "LOG_FILE=%~2"

for %%A in ("%LOG_FILE%") do mkdir "%%~dpA" 2>nul

echo --- Launch Log: %date% %time% --- > "%LOG_FILE%"

set "VENV_DIR=.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"
set "PYW=%VENV_DIR%\Scripts\pythonw.exe"

set "BEST_PY="
set "BEST_VER=0"

echo [DEBUG] Searching for Python 3.13+... >> "%LOG_FILE%"

for /f "delims=" %%i in ('where python 2^>nul') do (
    for /f "tokens=*" %%v in ('%%i -c "import sys; v=sys.version_info; print(v[0]*100+v[1])" 2^>nul') do (
        set "VER=%%v"

        if !VER! GEQ 313 (
            if !VER! GTR !BEST_VER! (
                set "BEST_VER=!VER!"
                set "BEST_PY=%%i"
            )
        )
    )
)

if not defined BEST_PY (
    echo [ERROR] No Python 3.13+ found. >> "%LOG_FILE%"
    echo [ERROR] No Python 3.13+ found in PATH.
    pause
    exit /b 1
)

echo [DEBUG] Using Python: !BEST_PY! (Version: !BEST_VER!) >> "%LOG_FILE%"
echo Using Python: !BEST_PY! (Version: !BEST_VER!)

if not exist "%PY%" (
    echo [DEBUG] Creating venv... >> "%LOG_FILE%"
    echo Creating virtual environment...
    "!BEST_PY!" -m venv "%VENV_DIR%"
)

echo [DEBUG] Installing requirements... >> "%LOG_FILE%"
echo Installing/Updating requirements...
"%PY%" -m pip install --upgrade pip >nul
:: System requirements
"%PY%" -m pip install -r "%~dp0requirements.txt"
:: App requirements
"%PY%" -m pip install -r "requirements.txt"

echo [DEBUG] Starting program in background... >> "%LOG_FILE%"
echo Starting program...

start "" "%PYW%" "%~1"

exit /b 0