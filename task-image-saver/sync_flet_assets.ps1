# icon_image.* を Flet ビルド用 assets に同期する
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$assetsDir = Join-Path $PSScriptRoot "assets"
New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null

$ico = Join-Path $PSScriptRoot "icon_image.ico"
$png = Join-Path $PSScriptRoot "icon_image.png"
if (-not (Test-Path $ico)) { throw "Missing icon: $ico" }
if (-not (Test-Path $png)) { throw "Missing icon: $png" }

Copy-Item -Force $ico (Join-Path $assetsDir "icon_windows.ico")
Copy-Item -Force $png (Join-Path $assetsDir "icon.png")
Write-Host "Synced assets: icon_windows.ico, icon.png" -ForegroundColor Green
exit 0
