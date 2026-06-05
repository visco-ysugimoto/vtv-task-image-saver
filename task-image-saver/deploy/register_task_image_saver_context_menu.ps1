# Register right-click menu for TaskImageSaver (current user only)

param(
    [string]$AppPath = "",
    [switch]$IncludeZip
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    if (Test-Path (Join-Path $PSScriptRoot "TaskImageSaver.exe")) {
        return $PSScriptRoot
    }
    return Split-Path $PSScriptRoot -Parent
}

function Resolve-AppPath {
    param([string]$InputPath)

    $repoRoot = Get-RepoRoot

    if ($InputPath) {
        if ([System.IO.Path]::IsPathRooted($InputPath)) {
            return (Resolve-Path $InputPath).Path
        }
        return (Resolve-Path (Join-Path $PSScriptRoot $InputPath)).Path
    }

    $localExePath = Join-Path $PSScriptRoot "TaskImageSaver.exe"
    if (Test-Path $localExePath) {
        return (Resolve-Path $localExePath).Path
    }

    $releasePath = Join-Path $repoRoot "dist\TaskImageSaver\TaskImageSaver.exe"
    if (Test-Path $releasePath) {
        return (Resolve-Path $releasePath).Path
    }

    $buildPath = Join-Path $repoRoot "build\windows\TaskImageSaver.exe"
    if (Test-Path $buildPath) {
        return (Resolve-Path $buildPath).Path
    }

    $legacyBuild = Join-Path $repoRoot "build\windows\task-image-saver.exe"
    if (Test-Path $legacyBuild) {
        return (Resolve-Path $legacyBuild).Path
    }

    $defaultOneFilePath = Join-Path $repoRoot "dist\TaskImageSaver.exe"
    if (Test-Path $defaultOneFilePath) {
        return (Resolve-Path $defaultOneFilePath).Path
    }

    throw "TaskImageSaver.exe was not found. Pass -AppPath explicitly."
}

function Register-ExtensionMenu {
    param(
        [string]$Extension,
        [string]$ExePath
    )

    $baseKey = "Registry::HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations\$Extension\shell\TaskImageSaverPreview"
    $commandKey = "$baseKey\command"
    $menuLabel = "TaskImageSaver $([char]0x3067)$([char]0x30D7)$([char]0x30EC)$([char]0x30D3)$([char]0x30E5)$([char]0x30FC)"
    $commandValue = "`"$ExePath`" `"%1`""

    New-Item -Path $baseKey -Force | Out-Null
    Set-Item -Path $baseKey -Value $menuLabel
    New-ItemProperty -Path $baseKey -Name "Icon" -Value "$ExePath,0" -PropertyType String -Force | Out-Null

    New-Item -Path $commandKey -Force | Out-Null
    Set-Item -Path $commandKey -Value $commandValue
}

$exePath = Resolve-AppPath -InputPath $AppPath
if (-not (Test-Path $exePath)) {
    throw "App path does not exist: $exePath"
}

$extensions = @(".ziq", ".zit", ".zii", ".zig", ".zia")
if ($IncludeZip) {
    $extensions += ".zip"
}

foreach ($ext in $extensions) {
    Register-ExtensionMenu -Extension $ext -ExePath $exePath
}

Write-Host "Context menu registration completed." -ForegroundColor Green
Write-Host "Target app: $exePath" -ForegroundColor Cyan
Write-Host "Extensions: $($extensions -join ', ')" -ForegroundColor Cyan
