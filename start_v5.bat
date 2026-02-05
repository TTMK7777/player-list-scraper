@echo off
chcp 65001 >nul
title プレイヤーリスト調査システム v5.0

echo.
echo =========================================
echo  プレイヤーリスト調査システム v5.0
echo =========================================
echo.
echo [機能]
echo  - プレイヤーリスト正誤チェック
echo  - 店舗・教室調査（AI調査 / スクレイピング / ハイブリッド）
echo.
echo 起動中...
echo.

cd /d "%~dp0"

REM Pythonパス確認
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [エラー] Pythonが見つかりません
    echo Python 3.10以上をインストールしてください
    pause
    exit /b 1
)

REM Streamlit起動
streamlit run app_v5.py --server.port 8505

pause
