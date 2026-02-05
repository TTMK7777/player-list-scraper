@echo off
chcp 65001 >nul
title プレイヤーリスト調査システム v4.1

echo.
echo ========================================
echo   プレイヤーリスト調査システム v4.1
echo   正誤チェック自動化ツール
echo ========================================
echo.

REM 作業ディレクトリに移動
cd /d "%~dp0"

REM Python確認
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Pythonがインストールされていません
    echo         https://www.python.org/ からインストールしてください
    pause
    exit /b 1
)

REM 仮想環境のアクティベート（あれば）
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] 仮想環境をアクティベート中...
    call .venv\Scripts\activate.bat
)

REM 依存パッケージ確認
python -c "import streamlit; import requests; import openpyxl" >nul 2>&1
if errorlevel 1 (
    echo [INFO] 依存パッケージをインストール中...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] パッケージのインストールに失敗しました
        pause
        exit /b 1
    )
)

REM APIキー確認
python -c "import os; from pathlib import Path; from dotenv import load_dotenv; load_dotenv(Path.home()/'.env.local'); exit(0 if os.getenv('PERPLEXITY_API_KEY') or os.getenv('GOOGLE_API_KEY') else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [WARNING] APIキーが設定されていません
    echo           ~/.env.local に以下を設定してください:
    echo           PERPLEXITY_API_KEY=pplx-xxxxx
    echo           GOOGLE_API_KEY=AIzaSy-xxxxx
    echo.
)

echo.
echo ========================================
echo   機能:
echo   - 撤退・統合・名称変更の自動検出
echo   - Perplexity/Gemini APIで最新情報取得
echo   - アラートレベル別レポート出力
echo ========================================
echo.
echo [INFO] アプリを起動中...
echo [INFO] ブラウザで http://localhost:8502 が開きます
echo.
echo 終了するには Ctrl+C を押してください
echo.

REM Streamlit起動
streamlit run app_v4.py --server.port 8502 --server.headless true

pause
