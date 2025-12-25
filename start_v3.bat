@echo off
chcp 65001 >nul
title 店舗情報スクレイパー v3.0

echo.
echo ========================================
echo   🏪 店舗情報スクレイパー v3.0
echo   マルチ戦略対応版
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

REM 依存パッケージ確認
python -c "import streamlit; import playwright" >nul 2>&1
if errorlevel 1 (
    echo [INFO] 依存パッケージをインストール中...
    pip install -r requirements.txt
    playwright install chromium
)

echo [INFO] アプリを起動中...
echo [INFO] ブラウザで http://localhost:8501 が開きます
echo.
echo ========================================
echo   3段階戦略で自動スクレイピング
echo   1. 静的HTML解析（高速）
echo   2. ブラウザ自動操作（JS対応）
echo   3. AI推論 + 複合（最終手段）
echo ========================================
echo.
echo 終了するには Ctrl+C を押してください
echo.

REM Streamlit起動
streamlit run app_v3.py --server.headless true
