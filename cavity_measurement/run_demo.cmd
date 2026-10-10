@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "CAVITY_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%CAVITY_PY%" set "CAVITY_PY=python"
"%CAVITY_PY%" -X utf8 cavity_measure.py demo --out demo_output
set "CAVITY_EXIT=%ERRORLEVEL%"
if "%CAVITY_EXIT%"=="0" start "" "%~dp0demo_output\overlay.png"
echo.
echo Output: %~dp0demo_output
pause
exit /b %CAVITY_EXIT%
