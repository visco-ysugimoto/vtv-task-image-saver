@echo off
REM TaskImageSaver 配布 ZIP 作成（ビルド込み）
cd /d "%~dp0"
set PYTHONUTF8=1
set FLET_CLI_NO_RICH_OUTPUT=1
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\package_release.ps1" %*
if errorlevel 1 exit /b 1
pause
