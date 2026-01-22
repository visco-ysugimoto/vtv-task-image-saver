<# 
create_repo_and_push.ps1

NOTE:
PowerShell 5.x may misread UTF-8 (no BOM) scripts and cause parse errors.
This file intentionally contains ASCII-only text to avoid encoding issues.

Usage:
  powershell -ExecutionPolicy Bypass -File .\create_repo_and_push.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoOwner = "visco-ysugimoto"
$RepoName  = "vtv-task-image-saver"

function Resolve-GhCommand {
  # Prefer gh on PATH
  $ghCmd = Get-Command gh -ErrorAction SilentlyContinue
  if ($ghCmd) { return $ghCmd.Source }

  # Common install path (winget GitHub.cli)
  $candidates = @(
    "$env:ProgramFiles\GitHub CLI\gh.exe",
    "${env:ProgramFiles(x86)}\GitHub CLI\gh.exe"
  )
  foreach ($p in $candidates) {
    if ($p -and (Test-Path $p)) { return $p }
  }

  return $null
}

$GhExe = Resolve-GhCommand

Write-Host "== check tools ==" -ForegroundColor Cyan
git --version

if (-not $GhExe) {
  Write-Host ""
  Write-Host "ERROR: GitHub CLI (gh) was not found." -ForegroundColor Yellow
  Write-Host ""
  Write-Host "Option A) Install gh (recommended):" -ForegroundColor Cyan
  Write-Host "  winget install --id GitHub.cli -e" -ForegroundColor Cyan
  Write-Host ""
  Write-Host "Option B) Push with git (repo must already exist on GitHub Web):" -ForegroundColor Cyan
  Write-Host "  git remote remove origin 2> NUL" -ForegroundColor Cyan
  Write-Host "  git remote add origin https://github.com/$RepoOwner/$RepoName.git" -ForegroundColor Cyan
  Write-Host "  git branch -M main" -ForegroundColor Cyan
  Write-Host "  git push -u origin main" -ForegroundColor Cyan
  exit 2
}

& $GhExe --version

Write-Host "== git init / commit ==" -ForegroundColor Cyan
if (-not (Test-Path ".git")) { git init }

git add -A
git status
try {
  git commit -m "Initial commit"
} catch {
  # If there's nothing to commit, continue.
  Write-Host "NOTE: commit skipped (possibly nothing to commit)." -ForegroundColor Yellow
}

Write-Host "== create GitHub repo and push ==" -ForegroundColor Cyan
Write-Host "If not logged in, run: gh auth login" -ForegroundColor Yellow

Write-Host "Target: https://github.com/$RepoOwner/$RepoName" -ForegroundColor Cyan

# Ensure remote points to the requested repo (repo is expected to exist; create manually if needed)
git remote remove origin 2> $null
git remote add origin "https://github.com/$RepoOwner/$RepoName.git"
git branch -M main

# If repo doesn't exist, gh repo view will fail; we still try push (git will error clearly)
try { & $GhExe repo view "$RepoOwner/$RepoName" *> $null } catch { }

git push -u origin main

Write-Host "Done: https://github.com/$RepoOwner/$RepoName" -ForegroundColor Green

