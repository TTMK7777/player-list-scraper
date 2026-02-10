@echo off
chcp 65001 >nul
title プレイヤーリスト調査システム v6 - ランチャー

echo.
echo ========================================
echo   プレイヤーリスト調査システム v6
echo   統合版ランチャー
echo ========================================
echo.
echo   [1] アプリ起動（推奨）
echo   [2] テスト実行
echo   [3] 初回セットアップ
echo   [Q] 終了
echo.

set /p choice="選択 (1/2/3/Q): "

if /i "%choice%"=="1" goto app
if /i "%choice%"=="2" goto test
if /i "%choice%"=="3" goto install
if /i "%choice%"=="Q" goto end
if /i "%choice%"=="q" goto end

echo [ERROR] 無効な選択です
pause
goto end

:app
call "%~dp0start_v5.bat"
goto end

:test
call "%~dp0run_tests.bat"
goto end

:install
call "%~dp0install.bat"
goto end

:end
