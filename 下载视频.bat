@echo off
rem Bilibili video downloader - double click, then paste a video URL
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PY=D:\epoint\python313\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" videofetch.py %*
echo.
echo Done. Press any key to close this window.
pause >nul
