@echo off
setlocal
cd /d "%~dp0"
echo Starting LeadDock 2.0...
set "VENV=%LOCALAPPDATA%\LeadDock2\venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo Setting up a short-path Python environment in %%LOCALAPPDATA%%...
  py -3 -m venv "%VENV%"
  if errorlevel 1 (
    echo Python launcher was not found. Trying python...
    python -m venv "%VENV%"
    if errorlevel 1 goto :error
  )
)
"%VENV%\Scripts\python.exe" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
  echo Installing desktop dependencies. Internet access is needed the first time...
  "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
  "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)
"%VENV%\Scripts\python.exe" leaddock\app.py
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Setup or startup failed. Copy this window's error and send it for troubleshooting.
pause
exit /b 1
