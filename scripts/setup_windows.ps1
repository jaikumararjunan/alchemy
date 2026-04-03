# Alchemy Platform - Windows Setup Script
# Handles Python version check, venv creation, and dependency install
# Run: powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

Write-Host ""
Write-Host "  Alchemy Trading Platform - Windows Setup" -ForegroundColor Cyan
Write-Host "  ========================================" -ForegroundColor Cyan
Write-Host ""

# ── Check Python version ──────────────────────────────────────────────────────
$pyVersions = @()

# Check all python launchers
foreach ($cmd in @("py -3.12", "py -3.11", "python3.12", "python3.11", "python")) {
    try {
        $ver = & cmd /c "$cmd --version 2>&1" 2>$null
        if ($ver -match "Python (3\.(1[01]|[89])\.\d+)") {
            $pyVersions += @{cmd=$cmd; ver=$Matches[1]}
        }
    } catch {}
}

$python = $null

if ($pyVersions.Count -gt 0) {
    $best = $pyVersions[0]
    $python = $best.cmd
    Write-Host "  Found Python $($best.ver) -> using '$python'" -ForegroundColor Green
} else {
    # Check if 3.14 is available
    $ver314 = & cmd /c "python --version 2>&1" 2>$null
    if ($ver314 -match "3\.14") {
        Write-Host "  Python 3.14 detected - NOT compatible with pydantic-core / numpy" -ForegroundColor Red
        Write-Host ""
        Write-Host "  REQUIRED: Python 3.12 (has pre-built wheels for all packages)" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Install Python 3.12:" -ForegroundColor White
        Write-Host "    winget install Python.Python.3.12" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Then re-run this script." -ForegroundColor White
        Write-Host ""

        $download = Read-Host "  Open Python 3.12 download page now? (y/n)"
        if ($download -eq "y") {
            Start-Process "https://www.python.org/downloads/release/python-3128/"
        }
        exit 1
    }
    Write-Host "  No compatible Python found (need 3.11 or 3.12)" -ForegroundColor Red
    Write-Host "  Install: winget install Python.Python.3.12" -ForegroundColor Yellow
    exit 1
}

# ── Create venv with correct Python ───────────────────────────────────────────
Write-Host ""
Write-Host "  Creating virtual environment with $python..." -ForegroundColor Cyan

if (Test-Path ".venv") {
    # Check if existing venv uses wrong Python
    $venvPy = & .venv\Scripts\python.exe --version 2>$null
    if ($venvPy -match "3\.14") {
        Write-Host "  Existing .venv uses Python 3.14 - recreating with 3.12..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force .venv
    } else {
        Write-Host "  Existing .venv OK ($venvPy)" -ForegroundColor Green
    }
}

if (-not (Test-Path ".venv")) {
    & cmd /c "$python -m venv .venv 2>&1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Failed to create venv" -ForegroundColor Red
        exit 1
    }
    Write-Host "  .venv created" -ForegroundColor Green
}

# ── Install packages ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Installing packages..." -ForegroundColor Cyan

& .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .venv\Scripts\pip.exe install -r requirements.docker.txt --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Host "  Install failed!" -ForegroundColor Red
    exit 1
}

Write-Host "  Packages installed" -ForegroundColor Green

# ── Create data dir + admin ───────────────────────────────────────────────────
Write-Host ""
Write-Host "  Creating admin user..." -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path data | Out-Null
& .venv\Scripts\python.exe scripts\create_admin.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "  Admin creation failed - check output above" -ForegroundColor Red
    exit 1
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  SETUP COMPLETE" -ForegroundColor Green
Write-Host "  ==============" -ForegroundColor Green
Write-Host ""
Write-Host "  Start the API:" -ForegroundColor White
Write-Host "    .venv\Scripts\uvicorn alchemy.api.app:app --host 0.0.0.0 --port 8000 --reload" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Start the frontend (new terminal):" -ForegroundColor White
Write-Host "    cd frontend" -ForegroundColor Cyan
Write-Host "    npm install" -ForegroundColor Cyan
Write-Host "    npm run dev" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Open: http://localhost:3000" -ForegroundColor Green
Write-Host "  Login: admin@alchemy.in / Alchemy#Admin!2024" -ForegroundColor Green
Write-Host ""
