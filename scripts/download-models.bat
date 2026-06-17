@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0..

echo === Downloading ASR models ===
echo.

uv run python "%ROOT%\scripts\download_models.py"
if errorlevel 1 (
    echo ERROR: Failed to download models.
    echo Try running manually: uv run python scripts/download_models.py
    exit /b 1
)

echo === Done ===
