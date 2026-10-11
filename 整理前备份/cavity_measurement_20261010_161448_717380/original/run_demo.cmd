@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_demo.ps1" -OpenPreview
set "CAVITY_EXIT=%ERRORLEVEL%"
pause
exit /b %CAVITY_EXIT%
