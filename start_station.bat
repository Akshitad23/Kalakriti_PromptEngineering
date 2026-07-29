@echo off
REM ============================================================
REM  start_station.bat — One-click startup for The Prompt Jailbreak
REM  KALAKRITI 26' — IEEE CIS Amrita Bengaluru
REM  Double-click this on the event laptop before teams arrive.
REM ============================================================

echo ============================================================
echo   KALAKRITI 26' - The Prompt Jailbreak
echo   IEEE CIS Amrita Bengaluru
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

cd /d "%~dp0backend"

if not exist ".env" (
    echo [SETUP] No .env file found. Creating from template...
    copy ".env.example" ".env"
    echo.
    echo [ACTION REQUIRED] Open backend\.env in Notepad and replace
    echo   GEMINI_API_KEY=your_gemini_api_key_here
    echo   with your actual key from aistudio.google.com
    echo.
    echo Press any key to continue after editing the .env file...
    pause >nul
)

echo [SETUP] Checking dependencies...
pip install -r requirements.txt --quiet

echo.
echo [READY] Starting server...
echo [INFO]  Browser: http://localhost:5000
echo [INFO]  Admin export: http://localhost:5000/api/admin/export?key=kalakriti2026
echo [INFO]  Press Ctrl+C to stop.
echo.

python app.py
pause
