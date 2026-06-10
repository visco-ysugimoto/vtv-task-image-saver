# TaskImageSaver release packaging (build -> dist -> ZIP)
param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectRoot

$env:PYTHONUTF8 = "1"
$env:FLET_CLI_NO_RICH_OUTPUT = "1"

function Get-ProjectVersion {
    $toml = Get-Content (Join-Path $ProjectRoot "pyproject.toml") -Raw
    if ($toml -match 'version\s*=\s*"([^"]+)"') {
        return $Matches[1]
    }
    return "1.0.0"
}

function Find-BuiltExe {
    param([string]$Dir)
    $preferred = Join-Path $Dir "TaskImageSaver.exe"
    if (Test-Path $preferred) { return $preferred }
    $any = Get-ChildItem -Path $Dir -Filter "*.exe" |
        Where-Object { $_.Name -notmatch '^(python|flet|httpx|idna)' } |
        Select-Object -First 1
    if ($any) { return $any.FullName }
    return $null
}

$version = Get-ProjectVersion
$stageDir = Join-Path $ProjectRoot "dist\TaskImageSaver"
$appDir = Join-Path $stageDir "app"
$zipPath = Join-Path $ProjectRoot "dist\TaskImageSaver_v${version}_win64.zip"
$buildOut = Join-Path $ProjectRoot "build\windows"
$deployDir = Join-Path $ProjectRoot "deploy"
$configDir = Join-Path $ProjectRoot "config"

Write-Host "=== TaskImageSaver release package (v$version) ===" -ForegroundColor Cyan

if (-not $SkipBuild) {
    Write-Host "Syncing Flet assets (icon)..." -ForegroundColor Yellow
    & "$PSScriptRoot\sync_flet_assets.ps1"
    if ($LASTEXITCODE -ne 0) { throw "sync_flet_assets failed" }
    Write-Host "Running Flet build..." -ForegroundColor Yellow
    Get-Process -Name "task-image-saver","TaskImageSaver","dart" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    python -m pip install -r (Join-Path $ProjectRoot "requirements.txt") flet-cli -q
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    python -m flet_cli.cli build windows --yes --no-rich-output
    if ($LASTEXITCODE -ne 0) { throw "flet build failed" }
} else {
    Write-Host 'SkipBuild: Flet exe rebuild skipped. Python changes sync via app.zip and app.zip.hash.' -ForegroundColor Yellow
}

if (-not (Test-Path $buildOut)) {
    throw "Build output not found: $buildOut"
}

$appZip = Join-Path $buildOut "data\flutter_assets\app\app.zip"
if (Test-Path $appZip) {
    Write-Host "Syncing Python sources into app.zip..." -ForegroundColor Yellow
    python (Join-Path $PSScriptRoot "sync_python_app_zip.py") $appZip
    if ($LASTEXITCODE -ne 0) { throw "sync_python_app_zip failed" }
}

$builtExe = Find-BuiltExe -Dir $buildOut
if (-not $builtExe) {
    throw "No exe in build\windows. Run build first."
}

Write-Host "Built exe: $builtExe" -ForegroundColor Green

if (Test-Path $stageDir) {
    Remove-Item -Recurse -Force $stageDir
}
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
New-Item -ItemType Directory -Path $appDir -Force | Out-Null

Write-Host "Copying to dist\TaskImageSaver..." -ForegroundColor Yellow
Copy-Item -Path (Join-Path $buildOut "*") -Destination $appDir -Recurse -Force

$iconFiles = @("launcher.ico", "icon_windows.ico", "icon.png", "launcher.png")
$assetsSrc = Join-Path $ProjectRoot "assets"
$stageAssets = Join-Path $stageDir "assets"
$appStageAssets = Join-Path $appDir "assets"
New-Item -ItemType Directory -Path $stageAssets -Force | Out-Null
New-Item -ItemType Directory -Path $appStageAssets -Force | Out-Null
foreach ($name in $iconFiles) {
    $src = Join-Path $assetsSrc $name
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $stageAssets -Force
        Copy-Item -Path $src -Destination $appStageAssets -Force
    }
}

$stageExe = Find-BuiltExe -Dir $appDir
if ($stageExe -and (Split-Path $stageExe -Leaf) -ne "TaskImageSaver.exe") {
    Move-Item -Force $stageExe (Join-Path $appDir "TaskImageSaver.exe")
}
Get-ChildItem -Path $appDir -Filter "task-image-saver.exe" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

$mainExe = Join-Path $appDir "TaskImageSaver.exe"
$appExe = Join-Path $appDir "TaskImageSaverApp.exe"
if (Test-Path $mainExe) {
    if (Test-Path $appExe) { Remove-Item -Force $appExe }
    Rename-Item -Force $mainExe $appExe
    Write-Host "Renamed Flet app to TaskImageSaverApp.exe" -ForegroundColor Green
}

Write-Host "Building TaskImageSaver launcher..." -ForegroundColor Yellow
python -m pip install pyinstaller -q
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
$launcherDist = Join-Path $ProjectRoot "build\launcher_dist"
$launcherWork = Join-Path $ProjectRoot "build\launcher_work"
if (Test-Path $launcherDist) { Remove-Item -Recurse -Force $launcherDist }
if (Test-Path $launcherWork) { Remove-Item -Recurse -Force $launcherWork }
python -m PyInstaller --clean --noconfirm `
    --distpath $launcherDist `
    --workpath $launcherWork `
    (Join-Path $ProjectRoot "launcher\task_image_saver_launcher.spec")
if ($LASTEXITCODE -ne 0) { throw "launcher build failed" }
Copy-Item -Path (Join-Path $launcherDist "TaskImageSaver.exe") -Destination (Join-Path $stageDir "TaskImageSaver.exe") -Force
Write-Host "Launcher installed as TaskImageSaver.exe" -ForegroundColor Green

$extraFiles = @(
    "RELEASE_README.txt",
    "register_task_image_saver_context_menu.ps1",
    "unregister_task_image_saver_context_menu.ps1"
)
$sampleConfig = Get-ChildItem -Path $configDir -Filter "*sample.json" | Select-Object -First 1
if ($sampleConfig) {
    $extraFiles += $sampleConfig.Name
}

foreach ($name in $extraFiles) {
    if ($name -like "*sample.json") {
        $src = Join-Path $configDir $name
    } else {
        $src = Join-Path $deployDir $name
    }
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $stageDir -Force
    }
}

@'
@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0register_task_image_saver_context_menu.ps1" -AppPath "%~dp0TaskImageSaver.exe"
pause
'@ | Set-Content -Path (Join-Path $stageDir "register_task_image_saver_context_menu.cmd") -Encoding ASCII

@'
@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0unregister_task_image_saver_context_menu.ps1"
pause
'@ | Set-Content -Path (Join-Path $stageDir "unregister_task_image_saver_context_menu.cmd") -Encoding ASCII

@'
@echo off
cd /d "%~dp0"
"%~dp0TaskImageSaver.exe" %*
'@ | Set-Content -Path (Join-Path $stageDir "TaskImageSaver.cmd") -Encoding ASCII

Copy-Item -Path (Join-Path $deployDir "TaskImageSaver_launch.cmd") -Destination $stageDir -Force

@'
@echo off
cd /d "%~dp0"
echo Starting TaskImageSaver (debug)...
TaskImageSaver.exe %*
echo.
echo --- startup.log ---
if exist "%~dp0startup.log" type "%~dp0startup.log"
if exist "%~dp0app\startup.log" type "%~dp0app\startup.log"
echo.
echo --- console.log ---
set CONLOG=%LOCALAPPDATA%\VISCO\TaskImageSaver\console.log
if exist "%CONLOG%" type "%CONLOG%"
echo.
pause
'@ | Set-Content -Path (Join-Path $stageDir "TaskImageSaver_debug.cmd") -Encoding ASCII

Copy-Item -Path (Join-Path $stageDir "RELEASE_README.txt") -Destination (Join-Path $stageDir "README.txt") -Force

Write-Host "Verifying release bundle..." -ForegroundColor Yellow
python (Join-Path $PSScriptRoot "verify_release_bundle.py") $appDir
if ($LASTEXITCODE -ne 0) { throw "verify_release_bundle failed" }

if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
Write-Host "Creating ZIP..." -ForegroundColor Yellow
$zipParent = Split-Path $zipPath -Parent
$zipName = Split-Path $zipPath -Leaf
$stageName = Split-Path $stageDir -Leaf
Push-Location $zipParent
try {
    if (Test-Path $zipName) { Remove-Item -Force $zipName }
    tar.exe -a -cf $zipName -C $zipParent $stageName
    if ($LASTEXITCODE -ne 0) { throw "tar failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

$zipSizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)

Write-Host "Writing release ZIP SHA256..." -ForegroundColor Yellow
python (Join-Path $PSScriptRoot "write_release_zip_hash.py") $zipPath
if ($LASTEXITCODE -ne 0) { throw "write_release_zip_hash failed" }

$hashPath = "$zipPath.sha256"
if (-not (Test-Path $hashPath)) {
    throw "SHA256 sidecar missing: $hashPath"
}

Write-Host ""
Write-Host "=== Release package ready ===" -ForegroundColor Green
Write-Host "Folder: $stageDir" -ForegroundColor Cyan
Write-Host "ZIP   : $zipPath ($zipSizeMb MB)" -ForegroundColor Cyan
Write-Host "SHA256: $hashPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "Distribute the ZIP or copy dist\TaskImageSaver folder as-is." -ForegroundColor Yellow
