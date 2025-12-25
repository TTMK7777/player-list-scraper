@echo off
chcp 65001 >nul
title 店舗情報スクレイパー

echo.
echo ========================================
echo   🏪 店舗情報スクレイパー
echo ========================================
echo.

REM 作業ディレクトリに移動
cd /d "%~dp0"

REM Python確認
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Pythonがインストールされていません
    pause
    exit /b 1
)

REM Streamlit確認（なければインストール）
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo [INFO] 依存パッケージをインストール中...
    pip install -r requirements.txt
    playwright install chromium
)

echo [INFO] アプリを起動中...
echo [INFO] ブラウザで http://localhost:8501 が開きます
echo.
echo 終了するには Ctrl+C を押してください
echo.

REM Streamlit起動
streamlit run app.py --server.headless true
