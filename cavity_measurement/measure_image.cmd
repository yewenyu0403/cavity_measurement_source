@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\measure_image.ps1" -ImagePath "%~1"
set "CAVITY_EXIT=%ERRORLEVEL%"
pause
exit /b %CAVITY_EXIT%
