@echo off
chcp 65001 >nul
title Player List Investigation System v5.0

echo.
echo =========================================
echo  Player List Investigation System v5.0
echo =========================================
echo.
echo [Features]
echo  - Player List Validation Check
echo  - Store Investigation (AI / Scraping / Hybrid)
echo.
echo Starting...
echo.

cd /d "%~dp0"

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [Error] Python not found
    echo Please install Python 3.10+
    pause
    exit /b 1
)

REM Start Streamlit
streamlit run app_v5.py --server.port 8505

pause
