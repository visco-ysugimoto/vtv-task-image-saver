# このスクリプトは「ローカル初回コミット」→「GitHubにリポジトリ作成」→「push」までをまとめて実行します。
# 事前に Git / GitHub CLI(gh) をインストールしてください。
#
# 実行例:
#   powershell -ExecutionPolicy Bypass -File .\create_repo_and_push.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoOwner = "visco-ysugimoto"
$RepoName  = "task-image-select-save"   # 必要なら変更してください（英数字推奨）

Write-Host "== check tools ==" -ForegroundColor Cyan
git --version
gh --version

Write-Host "== git init / commit ==" -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
  git init
}

git add -A
git status
git commit -m "Initial commit"

Write-Host "== create GitHub repo & push ==" -ForegroundColor Cyan
Write-Host "もし未ログインなら先に: gh auth login" -ForegroundColor Yellow

# --confirm を付けると対話を減らせますが、未ログインの場合は login が必要です。
gh repo create "$RepoOwner/$RepoName" --public --source . --remote origin --push --confirm

Write-Host "Done: https://github.com/$RepoOwner/$RepoName" -ForegroundColor Green

