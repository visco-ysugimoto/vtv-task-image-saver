# vtv-task-image-saver: TaskFilePreviewer only -> Windows exe (delegates to task-file-previewer)
param(
    [ValidateSet('OneDir', 'OneFile')]
    [string]$BuildMode = 'OneDir'
)

$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$child = Join-Path $root 'task-file-previewer\build_task_file_previewer.ps1'
if (-not (Test-Path $child)) {
    Write-Host "Missing: $child" -ForegroundColor Red
    exit 1
}

Write-Host '=== TaskFilePreviewer build (from repo root) ===' -ForegroundColor Cyan
& $child -BuildMode $BuildMode
exit $LASTEXITCODE
