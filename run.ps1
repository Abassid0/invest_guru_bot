# run.ps1 — Start the NGX Bot server locally
# Usage: .\run.ps1
# For production, deploy to Railway instead (see README)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  NGX Analyst Bot — Starting" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check venv exists
if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Host "ERROR: venv not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# Check .env exists
if (-not (Test-Path ".\.env")) {
    Write-Host "ERROR: .env not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Check ngrok for local webhook tunnelling
Write-Host ""
Write-Host "TIP: For local Telegram webhook, run ngrok in a separate terminal:" -ForegroundColor Gray
Write-Host "     ngrok http 8000" -ForegroundColor Gray
Write-Host "     Then set WEBHOOK_URL in .env to the ngrok https URL" -ForegroundColor Gray
Write-Host ""

Write-Host "Starting NGX Analyst Bot on http://localhost:8000 ..." -ForegroundColor Green
Write-Host "Admin dashboard: http://localhost:8000/admin" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
