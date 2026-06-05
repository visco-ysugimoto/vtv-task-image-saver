# Dropzone 拡張入り Flet クライアントをビルドする（ドラッグ＆ドロップ用）
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

$env:PYTHONUTF8 = "1"
$env:FLET_CLI_NO_RICH_OUTPUT = "1"
python -m pip install -r requirements.txt flet-cli
& "$PSScriptRoot\sync_flet_assets.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m flet_cli.cli build windows -v --yes --no-rich-output

$exe = Get-ChildItem "build\windows\*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($exe) {
    Write-Host "ビルド完了: $($exe.FullName)"
    Write-Host ""
    Write-Host "起動方法 (どちらか):"
    Write-Host "  $($exe.FullName)"
    Write-Host "  python .\app\main_save_task_images_flet.py"
} else {
    Write-Host "build\windows に exe が見つかりません。"
    exit 1
}
