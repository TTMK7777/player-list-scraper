@echo off
chcp 65001 >nul
title プレイヤーリスト調査システム - ランチャー

echo.
echo ========================================
echo   プレイヤーリスト調査システム
echo   Launcher
echo ========================================
echo.
echo どのバージョンを起動しますか？
echo.
echo   [1] v4.1 正誤チェック（推奨）
echo   [2] v3.0 店舗調査
echo   [3] テスト実行
echo   [4] 初回セットアップ
echo   [Q] 終了
echo.

set /p choice="選択 (1/2/3/4/Q): "

if /i "%choice%"=="1" goto v4
if /i "%choice%"=="2" goto v3
if /i "%choice%"=="3" goto test
if /i "%choice%"=="4" goto install
if /i "%choice%"=="Q" goto end
if /i "%choice%"=="q" goto end

echo [ERROR] 無効な選択です
pause
goto end

:v4
call "%~dp0start_v4.bat"
goto end

:v3
call "%~dp0start_v3.bat"
goto end

:test
call "%~dp0run_tests.bat"
goto end

:install
call "%~dp0install.bat"
goto end

:end
