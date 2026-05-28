@echo off
cd /d "%~dp0"

:: Se la dashboard e' gia' attiva, apri solo il browser
netstat -ano | findstr "127.0.0.1:5000" | findstr "LISTENING" >nul 2>&1
if %errorlevel% == 0 (
    echo Dashboard gia' in esecuzione - apro il browser...
    start "" http://localhost:5000
    exit
)

echo Avvio dashboard mockup...
echo Tieni questa finestra aperta mentre lavori.
echo.
start /min "" cmd /c "timeout /t 2 >nul && start "" http://localhost:5000"
.\venv\Scripts\python.exe dashboard.py
pause
