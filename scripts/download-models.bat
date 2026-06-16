@echo off
setlocal enabledelayedexpansion

set ROOT=%~dp0..
set MODELS_DIR=%ROOT%\backend\asr\models

echo === Downloading ASR models ===

if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%"

echo.
echo This script will download the required ASR models.
echo.
echo Required models:
echo   1. sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
echo   2. silero_vad.onnx
echo.
echo Please download manually or use the Python scripts/download_models.py
echo.

echo Placeholder — see scripts/download_models.py for automated download.
echo.
echo Done.
