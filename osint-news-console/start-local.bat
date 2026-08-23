@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment is missing. Run install-to-d.bat from the deployment package again.
  pause
  exit /b 1
)
echo Starting OSINT News Console...
echo Close this window or press Ctrl+C to stop the local service.
".venv\Scripts\python.exe" local_server.py
pause
endlocal
