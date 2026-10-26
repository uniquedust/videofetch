@echo off
rem Bilibili video downloader - double click, then paste a video URL
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
rem find Python: py launcher first, then python on PATH (skip the WindowsApps stub)
set "PY="
where py >nul 2>nul && set "PY=py"
if defined PY goto :run
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo %%i | find /i "WindowsApps" >nul || (set "PY=%%i" & goto :run)
)
if not defined PY (
    echo [!] Python not found. Please install Python 3.8+ from python.org first.
    pause
    exit /b 1
)
:run
"%PY%" videofetch.py %*
echo.
echo Done. Press any key to close this window.
pause >nul
