@echo off
chcp 65001 > nul
echo ====================================
echo プレイヤーリスト調査システム v4.0
echo ====================================
echo.

REM 仮想環境のアクティベート（あれば）
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Streamlit起動
echo Streamlit を起動中...
streamlit run app_v4.py --server.port 8502

pause
