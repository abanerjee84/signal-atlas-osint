@echo off
setlocal
cd /d "%~dp0"
title Global OSINT Dashboard
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 (
    echo.
    echo Startup failed. See the message above and logs in data\logs.
    pause
)
endlocal
