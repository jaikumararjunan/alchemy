# Alchemy - Quick start script
# Run: powershell -ExecutionPolicy Bypass -File run.ps1

Write-Host ""
Write-Host "  Starting Alchemy Trading Platform..." -ForegroundColor Cyan
Write-Host ""

# Check venv exists
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "  Setting up virtual environment..." -ForegroundColor Yellow
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Python 3.12 not found." -ForegroundColor Red
        Write-Host "  Download: https://python.org/downloads/release/python-3128/" -ForegroundColor White
        exit 1
    }
    .venv\Scripts\pip install -r requirements.local.txt --quiet
    Write-Host "  Packages installed" -ForegroundColor Green
}

# Activate venv
.venv\Scripts\activate.ps1

# Check data dir and admin
if (-not (Test-Path "data\alchemy.db")) {
    Write-Host "  First run - creating admin account..." -ForegroundColor Yellow
    python scripts\create_admin.py
}

# Build frontend if dist doesn't exist
if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Host "  Building frontend..." -ForegroundColor Yellow
    Push-Location frontend
    npm install --silent
    npm run build
    Pop-Location
    Write-Host "  Frontend built" -ForegroundColor Green
}

Write-Host ""
Write-Host "  READY" -ForegroundColor Green
Write-Host "  Open: http://localhost:8000" -ForegroundColor White
Write-Host "  Login: admin@alchemy.in / Alchemy#Admin!2024" -ForegroundColor White
Write-Host "  Stop: Ctrl+C" -ForegroundColor Gray
Write-Host ""

# Start API
uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000 --reload
