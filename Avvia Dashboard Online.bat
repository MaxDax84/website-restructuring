@echo off
cd /d "%~dp0"
echo Avvio dashboard con accesso da cellulare...
echo.
.\venv\Scripts\python.exe dashboard_online.py
pause
