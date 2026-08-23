@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure-fixed-url.ps1"
if errorlevel 1 (
  echo Fixed URL configuration failed. Read the message above.
)
pause
endlocal
