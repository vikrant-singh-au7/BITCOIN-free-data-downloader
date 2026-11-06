@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer with Tkinter.
  pause
  exit /b 1
)
start "BTC Options Data" pythonw "%~dp0app.pyw"
