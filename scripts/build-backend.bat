@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0..
set DIST=%ROOT%\dist

echo === Building backend.exe with PyInstaller ===

if not exist "%DIST%" mkdir "%DIST%"

:: Use python from uv venv if available
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set PYTHON=%ROOT%\.venv\Scripts\python.exe
) else (
    where python >nul 2>nul || (
        echo ERROR: Python not found. Please install Python 3.11+
        exit /b 1
    )
    set PYTHON=python
)

:: Ensure PyInstaller is installed
"%PYTHON%" -m pip install pyinstaller >nul 2>&1

:: Build
"%PYTHON%" -m PyInstaller ^
    --onefile ^
    --name backend ^
    --distpath "%DIST%" ^
    --add-data "%ROOT%\config.default.yaml;." ^
    --add-data "%ROOT%\frontend;frontend" ^
    --add-data "%ROOT%\backend\asr\models;backend\asr\models" ^
    --hidden-import "uvicorn.logging" ^
    --hidden-import "uvicorn.loops.auto" ^
    --hidden-import "uvicorn.protocols.http.auto" ^
    "%ROOT%\backend\main.py"

echo === Done: %DIST%\backend.exe ===
