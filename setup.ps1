# setup.ps1 — Run once to set up the NGX Bot on Windows
# Usage: .\setup.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NGX Analyst Bot — Windows Setup v2.0" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
Write-Host "[1/5] Checking Python..." -ForegroundColor Yellow
try {
    $pyVersion = python --version 2>&1
    Write-Host "      Found: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "      ERROR: Python not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

# 2. Create virtual environment
Write-Host "[2/5] Creating virtual environment..." -ForegroundColor Yellow
if (Test-Path ".\venv") {
    Write-Host "      venv already exists, skipping." -ForegroundColor Gray
} else {
    python -m venv venv
    Write-Host "      venv created." -ForegroundColor Green
}

# 3. Activate venv and install dependencies
Write-Host "[3/5] Installing dependencies..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"
pip install -r requirements.txt --quiet
Write-Host "      Dependencies installed." -ForegroundColor Green

# 4. Set up .env
Write-Host "[4/5] Setting up .env..." -ForegroundColor Yellow
if (Test-Path ".\.env") {
    Write-Host "      .env already exists, skipping." -ForegroundColor Gray
} else {
    Copy-Item ".\.env.example" ".\.env"
    Write-Host "      .env created from template." -ForegroundColor Green
    Write-Host ""
    Write-Host "  *** ACTION REQUIRED: Open .env and fill in your API keys ***" -ForegroundColor Red
    Write-Host ""
}

# 5. Validate .env keys
Write-Host "[5/5] Validating .env..." -ForegroundColor Yellow
$envContent = Get-Content ".\.env" -Raw
$required = @(
    "TELEGRAM_BOT_TOKEN",
    "ANTHROPIC_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "PAYSTACK_SECRET_KEY",
    "WEBHOOK_URL",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD"
)
$missing = @()
foreach ($key in $required) {
    if ($envContent -notmatch "$key=\S") {
        $missing += $key
    }
}
if ($missing.Count -gt 0) {
    Write-Host "      Missing or empty keys in .env:" -ForegroundColor Red
    foreach ($k in $missing) { Write-Host "        - $k" -ForegroundColor Red }
} else {
    Write-Host "      All required keys present." -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "  1. Edit .env with your real API keys" -ForegroundColor White
Write-Host "  2. Run supabase_schema.sql in Supabase dashboard" -ForegroundColor White
Write-Host "  3. Run: .\run.ps1" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
