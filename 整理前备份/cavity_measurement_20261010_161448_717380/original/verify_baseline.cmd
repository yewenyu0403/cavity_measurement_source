@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify_baseline.ps1"
set "CAVITY_EXIT=%ERRORLEVEL%"
pause
exit /b %CAVITY_EXIT%
