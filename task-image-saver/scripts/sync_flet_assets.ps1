# assets/launcher.* を Flet ビルド用・配布用 assets に同期する
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent

$assetsDir = Join-Path $ProjectRoot "assets"
$appAssetsDir = Join-Path (Join-Path $ProjectRoot "app") "assets"
New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null
New-Item -ItemType Directory -Path $appAssetsDir -Force | Out-Null

$ico = Join-Path $assetsDir "launcher.ico"
$png = Join-Path $assetsDir "launcher.png"
if (-not (Test-Path $ico)) { throw "Missing icon: $ico" }
if (-not (Test-Path $png)) { throw "Missing icon: $png" }

$iconWindows = Join-Path $assetsDir "icon_windows.ico"
$iconPng = Join-Path $assetsDir "icon.png"
Copy-Item -Force $ico $iconWindows
Copy-Item -Force $png $iconPng

foreach ($destDir in @($appAssetsDir)) {
    Copy-Item -Force $ico (Join-Path $destDir "icon_windows.ico")
    Copy-Item -Force $png (Join-Path $destDir "icon.png")
    Copy-Item -Force $ico (Join-Path $destDir "launcher.ico")
}

Write-Host "Synced assets: icon_windows.ico, icon.png (root + app/assets)" -ForegroundColor Green
exit 0
