# assets/launcher.* を Flet ビルド用 assets に同期する
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent

$assetsDir = Join-Path $ProjectRoot "assets"
New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null

$ico = Join-Path $assetsDir "launcher.ico"
$png = Join-Path $assetsDir "launcher.png"
if (-not (Test-Path $ico)) { throw "Missing icon: $ico" }
if (-not (Test-Path $png)) { throw "Missing icon: $png" }

Copy-Item -Force $ico (Join-Path $assetsDir "icon_windows.ico")
Copy-Item -Force $png (Join-Path $assetsDir "icon.png")
Write-Host "Synced assets: icon_windows.ico, icon.png" -ForegroundColor Green
exit 0
