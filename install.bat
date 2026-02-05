@echo off
chcp 65001 >nul
title プレイヤーリスト調査システム - セットアップ

echo.
echo ========================================
echo   初回セットアップ
echo ========================================
echo.

REM 作業ディレクトリに移動
cd /d "%~dp0"

REM Python確認
echo [1/4] Python確認中...
python --version
if errorlevel 1 (
    echo [ERROR] Pythonがインストールされていません
    echo         https://www.python.org/ からインストールしてください
    pause
    exit /b 1
)
echo       OK
echo.

REM 仮想環境作成（任意）
echo [2/4] 仮想環境の作成（スキップ可）
if exist ".venv" (
    echo       仮想環境は既に存在します
) else (
    set /p create_venv="仮想環境を作成しますか？ (y/N): "
    if /i "%create_venv%"=="y" (
        echo       仮想環境を作成中...
        python -m venv .venv
        call .venv\Scripts\activate.bat
        echo       OK
    ) else (
        echo       スキップ
    )
)
echo.

REM 依存パッケージインストール
echo [3/4] 依存パッケージをインストール中...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] パッケージのインストールに失敗しました
    pause
    exit /b 1
)
echo       OK
echo.

REM Playwright（v3用）
echo [4/4] Playwright ブラウザのインストール（v3用）
set /p install_pw="Playwrightブラウザをインストールしますか？ (y/N): "
if /i "%install_pw%"=="y" (
    playwright install chromium
    echo       OK
) else (
    echo       スキップ（v3を使わない場合は不要）
)
echo.

echo ========================================
echo   セットアップ完了！
echo ========================================
echo.
echo 次のステップ:
echo   1. APIキーを設定:
echo      ~/.env.local に以下を追加
echo      PERPLEXITY_API_KEY=pplx-xxxxx
echo      GOOGLE_API_KEY=AIzaSy-xxxxx
echo.
echo   2. 起動:
echo      start.bat または start_v4.bat
echo.

pause
