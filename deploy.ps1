# deploy.ps1 — Deploy NGX Bot to Railway
# Requires: Railway CLI installed (npm install -g @railway/cli)
# Usage: .\deploy.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  NGX Analyst Bot — Deploy to Railway" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Check Railway CLI
try {
    $rlVersion = railway --version 2>&1
    Write-Host "Railway CLI: $rlVersion" -ForegroundColor Green
} catch {
    Write-Host "Railway CLI not found. Install with:" -ForegroundColor Red
    Write-Host "  npm install -g @railway/cli" -ForegroundColor Yellow
    exit 1
}

# Check git
try {
    git status | Out-Null
} catch {
    Write-Host "Not a git repo. Run: git init && git add . && git commit -m 'init'" -ForegroundColor Red
    exit 1
}

# Commit any pending changes
$status = git status --porcelain
if ($status) {
    Write-Host "Committing pending changes..." -ForegroundColor Yellow
    git add -A
    git commit -m "NGX Bot v2.0 — 18 modules + fixed income + PowerShell"
    Write-Host "Committed." -ForegroundColor Green
} else {
    Write-Host "No pending changes." -ForegroundColor Gray
}

# Deploy
Write-Host ""
Write-Host "Deploying to Railway..." -ForegroundColor Yellow
railway up --detach

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  Deployment triggered!" -ForegroundColor Green
Write-Host ""
Write-Host "  Monitor at: https://railway.app/dashboard" -ForegroundColor White
Write-Host "  View logs:  railway logs" -ForegroundColor White
Write-Host ""
Write-Host "  Remember to set all env vars in Railway dashboard" -ForegroundColor Yellow
Write-Host "  if this is a first deployment." -ForegroundColor Yellow
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
