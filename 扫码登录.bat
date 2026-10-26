@echo off
rem Bilibili QR login - scan the QR with your bilibili phone app
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PY=D:\epoint\python313\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" videofetch.py --login
echo.
echo Press any key to close this window.
pause >nul
