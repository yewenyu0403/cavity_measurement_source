@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\measure_folder.ps1" -ImagesPath "%~1"
set "CAVITY_EXIT=%ERRORLEVEL%"
pause
exit /b %CAVITY_EXIT%
