# PowerShell script to build Windows exe
# =========================================
# TaskImageSaver を Windows exe にビルドするスクリプト

Write-Host "=== TaskImageSaver ビルドスクリプト ===" -ForegroundColor Cyan
Write-Host ""

# 仮想環境の確認
if (Test-Path ".\venv") {
    Write-Host "仮想環境を有効化します..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
} elseif (Test-Path ".\.venv") {
    Write-Host "仮想環境を有効化します..." -ForegroundColor Yellow
    .\.venv\Scripts\Activate.ps1
}

# 必要なパッケージのインストール
Write-Host "必要なパッケージをインストールしています..." -ForegroundColor Yellow
pip install --upgrade pip
pip install pyinstaller
pip install -r requirements.txt

# 以前のビルド成果物をクリーンアップ
Write-Host ""
Write-Host "以前のビルド成果物をクリーンアップしています..." -ForegroundColor Yellow
if (Test-Path ".\build") {
    Remove-Item -Recurse -Force ".\build"
}
if (Test-Path ".\dist") {
    Remove-Item -Recurse -Force ".\dist"
}

# PyInstallerでビルド
Write-Host ""
Write-Host "PyInstallerでビルドを開始します..." -ForegroundColor Green
pyinstaller main_save_task_images_flet.spec --noconfirm

# ビルド結果の確認
Write-Host ""
if (Test-Path ".\dist\TaskImageSaver\TaskImageSaver.exe") {
    Write-Host "=== ビルド成功! ===" -ForegroundColor Green
    Write-Host "実行ファイル: .\dist\TaskImageSaver\TaskImageSaver.exe" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "配布する場合は dist\TaskImageSaver フォルダ全体をコピーしてください。" -ForegroundColor Yellow
    
    # ファイルサイズの表示
    $exeFile = Get-Item ".\dist\TaskImageSaver\TaskImageSaver.exe"
    Write-Host "EXEファイルサイズ: $([math]::Round($exeFile.Length / 1MB, 2)) MB" -ForegroundColor Gray
} else {
    Write-Host "=== ビルド失敗 ===" -ForegroundColor Red
    Write-Host "エラーログを確認してください。" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "ビルド完了!" -ForegroundColor Cyan
