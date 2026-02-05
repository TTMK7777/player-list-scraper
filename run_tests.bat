@echo off
chcp 65001 >nul
title プレイヤーリスト調査システム - テスト実行

echo.
echo ========================================
echo   テスト実行
echo ========================================
echo.

REM 作業ディレクトリに移動
cd /d "%~dp0"

REM 仮想環境のアクティベート（あれば）
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM pytest確認
python -c "import pytest" >nul 2>&1
if errorlevel 1 (
    echo [INFO] pytestをインストール中...
    pip install pytest pytest-asyncio pytest-mock
)

echo.
echo どのテストを実行しますか？
echo.
echo   [1] 全テスト実行
echo   [2] 詳細表示付き (-v)
echo   [3] カバレッジ付き
echo   [4] player_validator のみ
echo   [5] llm_client のみ
echo   [Q] 終了
echo.

set /p choice="選択 (1/2/3/4/5/Q): "

if /i "%choice%"=="1" goto all
if /i "%choice%"=="2" goto verbose
if /i "%choice%"=="3" goto coverage
if /i "%choice%"=="4" goto validator
if /i "%choice%"=="5" goto llm
if /i "%choice%"=="Q" goto end
if /i "%choice%"=="q" goto end

echo [ERROR] 無効な選択です
pause
goto end

:all
echo.
echo [INFO] 全テスト実行中...
pytest tests/
goto done

:verbose
echo.
echo [INFO] 詳細モードで実行中...
pytest tests/ -v
goto done

:coverage
echo.
echo [INFO] カバレッジ計測中...
pip install pytest-cov >nul 2>&1
pytest tests/ --cov=. --cov-report=html --cov-report=term
echo.
echo [INFO] カバレッジレポート: htmlcov/index.html
goto done

:validator
echo.
echo [INFO] player_validator テスト実行中...
pytest tests/test_player_validator.py -v
goto done

:llm
echo.
echo [INFO] llm_client テスト実行中...
pytest tests/test_llm_client.py -v
goto done

:done
echo.
echo ========================================
echo   テスト完了
echo ========================================

:end
echo.
pause
