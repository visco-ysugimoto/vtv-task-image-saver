@echo off
REM Dropzone 拡張入り Flet クライアントをビルド（実行ポリシー不要）
cd /d "%~dp0"
set PYTHONUTF8=1
set FLET_CLI_NO_RICH_OUTPUT=1

python -m pip install -r requirements.txt flet-cli
if errorlevel 1 exit /b 1

powershell -ExecutionPolicy Bypass -File "%~dp0sync_flet_assets.ps1"
if errorlevel 1 exit /b 1

python -m flet_cli.cli build windows -v --yes --no-rich-output
if errorlevel 1 exit /b 1

if exist "build\windows\*.exe" (
    echo.
    echo ビルド完了: build\windows\
    echo 起動: build\windows\task-image-saver.exe
    echo   または: python main_save_task_images_flet.py
) else (
    echo build\windows に exe が見つかりません。
    exit /b 1
)
