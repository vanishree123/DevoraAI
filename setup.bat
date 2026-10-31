@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo       DEVORA AI - SETUP
 echo ========================================
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Could not create virtual environment.
  echo Install Python 3 and try again.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto failed
pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click run_devora.bat to start Devora AI.
echo.
pause
exit /b 0
:failed
echo.
echo Setup failed. Copy the error text and send it for troubleshooting.
pause
exit /b 1
