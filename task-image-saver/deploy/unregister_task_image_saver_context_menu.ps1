# Unregister right-click menu for TaskImageSaver (current user only)

param(
    [switch]$IncludeZip
)

$ErrorActionPreference = "Stop"

function Remove-ExtensionMenu {
    param([string]$Extension)

    $baseKey = "HKCU\Software\Classes\SystemFileAssociations\$Extension\shell\TaskImageSaverPreview"
    reg.exe delete $baseKey /f | Out-Null
}

$extensions = @(".ziq", ".zit", ".zii", ".zig", ".zia")
if ($IncludeZip) {
    $extensions += ".zip"
}

foreach ($ext in $extensions) {
    try {
        Remove-ExtensionMenu -Extension $ext
    } catch {
        # Ignore missing keys to keep this script idempotent.
    }
}

Write-Host "Context menu unregistration completed." -ForegroundColor Green
Write-Host "Extensions: $($extensions -join ', ')" -ForegroundColor Cyan
