@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0..
set DIST=%ROOT%\dist
set BUILD=%ROOT%\build

echo === Building backend.exe with PyInstaller ===

if not exist "%DIST%" mkdir "%DIST%"
if not exist "%BUILD%" mkdir "%BUILD%"

:: Generate config.default.yaml with built-in OpenRouter key
if not "%OPENROUTER_BUILD_KEY%"=="" (
    echo Injecting OpenRouter build key into config.default.yaml
    powershell -Command "(Get-Content '%ROOT%\config.default.yaml') -replace 'api_key: \"\"', 'api_key: \"%OPENROUTER_BUILD_KEY%\"' | Set-Content '%BUILD%\config.default.yaml'"
) else (
    echo WARNING: OPENROUTER_BUILD_KEY not set, using empty api_key
    copy /Y "%ROOT%\config.default.yaml" "%BUILD%\config.default.yaml"
)

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
    --add-data "%BUILD%\config.default.yaml;." ^
    --add-data "%ROOT%\frontend;frontend" ^
    --add-data "%ROOT%\backend\asr\models;backend\asr\models" ^
    --hidden-import "uvicorn.logging" ^
    --hidden-import "uvicorn.loops.auto" ^
    --hidden-import "uvicorn.protocols.http.auto" ^
    "%ROOT%\backend\main.py"

:: Clean up build artifacts
if exist "%BUILD%\config.default.yaml" del "%BUILD%\config.default.yaml"

echo === Done: %DIST%\backend.exe ===
