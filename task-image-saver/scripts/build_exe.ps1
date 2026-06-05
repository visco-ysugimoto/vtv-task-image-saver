# PowerShell script to build distributable TaskImageSaver package
# 配布用 ZIP（dist\TaskImageSaver_v*_win64.zip）を作成します

Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    Write-Host "=== TaskImageSaver 配布ビルド ===" -ForegroundColor Cyan
    Write-Host "package_release.ps1 に処理を委譲します..." -ForegroundColor Yellow
    Write-Host ""
    & "$PSScriptRoot\package_release.ps1"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
