# Alchemy Trading Platform - Windows PowerShell Helper
# Usage: .\alchemy.ps1 <command>
#
# Commands:
#   .\alchemy.ps1 up        - Build + start (http://localhost:8000)
#   .\alchemy.ps1 dev       - Start + React hot-reload at :3000
#   .\alchemy.ps1 down      - Stop all containers
#   .\alchemy.ps1 logs      - Tail API logs
#   .\alchemy.ps1 restart   - Restart API (no rebuild)
#   .\alchemy.ps1 rebuild   - Force full image rebuild
#   .\alchemy.ps1 shell     - Open bash inside API container
#   .\alchemy.ps1 test      - Run unit tests inside container
#   .\alchemy.ps1 status    - Container status + resource usage
#   .\alchemy.ps1 health    - Check API health endpoint
#   .\alchemy.ps1 backup    - Backup SQLite DB to .\backups\
#   .\alchemy.ps1 reset     - WARNING: Wipe all data and restart fresh
#   .\alchemy.ps1 help      - Show this help

param([string]$Command = "help")

$CONTAINER = "alchemy-api"

function dc  { docker compose -f docker-compose.local.yml @args }
function dcd { docker compose -f docker-compose.local.yml --profile dev @args }

function Show-Help {
    Write-Host ""
    Write-Host "  =================================================" -ForegroundColor Cyan
    Write-Host "   Alchemy Trading Platform - Docker Commands" -ForegroundColor Cyan
    Write-Host "  =================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Usage: .\alchemy.ps1 <command>" -ForegroundColor White
    Write-Host ""
    Write-Host "  COMMAND         DESCRIPTION" -ForegroundColor Yellow
    Write-Host "  up              Build + start  ->  http://localhost:8000" -ForegroundColor Gray
    Write-Host "  dev             Start + React hot-reload at :3000" -ForegroundColor Gray
    Write-Host "  down            Stop all containers" -ForegroundColor Gray
    Write-Host "  logs            Tail API logs (Ctrl+C to stop)" -ForegroundColor Gray
    Write-Host "  restart         Restart API without rebuild" -ForegroundColor Gray
    Write-Host "  rebuild         Force full image rebuild" -ForegroundColor Gray
    Write-Host "  shell           bash shell inside API container" -ForegroundColor Gray
    Write-Host "  test            Run 134 unit tests inside container" -ForegroundColor Gray
    Write-Host "  status          Container health + CPU/RAM usage" -ForegroundColor Gray
    Write-Host "  health          Check /health endpoint" -ForegroundColor Gray
    Write-Host "  backup          Copy SQLite DB to .\backups\" -ForegroundColor Gray
    Write-Host "  reset           WARNING: Wipe all data + restart fresh" -ForegroundColor Gray
    Write-Host "  help            Show this help" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Quick start:" -ForegroundColor Yellow
    Write-Host "    .\alchemy.ps1 up" -ForegroundColor Green
    Write-Host ""
}

function Invoke-Install {
    Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
    python -m pip install --upgrade pip
    pip install -r requirements.docker.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "  Dependencies installed!" -ForegroundColor Green
        Write-Host "  Now run: .\alchemy.ps1 seed" -ForegroundColor White
    } else {
        Write-Host "Install failed. Check output above." -ForegroundColor Red
    }
}

function Invoke-Seed {
    Write-Host "Creating admin user..." -ForegroundColor Cyan
    python scripts\create_admin.py
}

function Invoke-Up {
    Write-Host "Building Alchemy (first build takes 3-5 min)..." -ForegroundColor Cyan
    dc up --build -d
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "  Alchemy is starting up!" -ForegroundColor Green
        Write-Host "  API + Frontend : http://localhost:8000" -ForegroundColor White
        Write-Host "  API Docs       : http://localhost:8000/docs" -ForegroundColor White
        Write-Host "  Login          : admin@alchemy.in / Alchemy#Admin!2024" -ForegroundColor White
        Write-Host ""
        Write-Host "  Waiting 10s for startup..." -ForegroundColor Gray
        Start-Sleep -Seconds 10
        try {
            $resp = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
            Write-Host "  Health OK: version=$($resp.version) env=$($resp.env)" -ForegroundColor Green
        }
        catch {
            Write-Host "  Still starting up - check logs: .\alchemy.ps1 logs" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "Build failed. Check output above." -ForegroundColor Red
    }
}

function Invoke-Dev {
    Write-Host "Starting dev stack (API + React hot-reload)..." -ForegroundColor Cyan
    dcd up --build -d
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "  Dev stack started!" -ForegroundColor Green
        Write-Host "  React Dev UI   : http://localhost:3000  (use this for dev)" -ForegroundColor White
        Write-Host "  API Backend    : http://localhost:8000" -ForegroundColor White
        Write-Host "  API Docs       : http://localhost:8000/docs" -ForegroundColor White
        Write-Host ""
    }
}

function Invoke-Down {
    Write-Host "Stopping all containers..." -ForegroundColor Yellow
    dcd down
    Write-Host "Done." -ForegroundColor Green
}

function Invoke-Logs {
    Write-Host "Tailing API logs (Ctrl+C to stop)..." -ForegroundColor Cyan
    dc logs -f api
}

function Invoke-Restart {
    Write-Host "Restarting API..." -ForegroundColor Cyan
    dc restart api
    Write-Host "Done." -ForegroundColor Green
}

function Invoke-Rebuild {
    Write-Host "Force rebuilding images..." -ForegroundColor Cyan
    dc build --no-cache
    dc up -d
    Write-Host "Rebuilt and restarted." -ForegroundColor Green
}

function Invoke-Shell {
    Write-Host "Opening shell in $CONTAINER..." -ForegroundColor Cyan
    docker exec -it $CONTAINER bash
}

function Invoke-Test {
    Write-Host "Running unit tests..." -ForegroundColor Cyan
    docker exec $CONTAINER python3 -m pytest tests/unit/ -v --no-cov -q
}

function Invoke-Status {
    Write-Host "Container status:" -ForegroundColor Cyan
    dcd ps
    Write-Host ""
    Write-Host "Resource usage:" -ForegroundColor Cyan
    docker stats --no-stream --format "table {{.Name}}`t{{.CPUPerc}}`t{{.MemUsage}}" 2>$null
}

function Invoke-Health {
    Write-Host "Checking API health..." -ForegroundColor Cyan
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
        Write-Host "  status  : $($resp.status)" -ForegroundColor Green
        Write-Host "  version : $($resp.version)" -ForegroundColor Green
        Write-Host "  env     : $($resp.env)" -ForegroundColor Green
    }
    catch {
        Write-Host "  API not responding. Run: .\alchemy.ps1 up" -ForegroundColor Red
    }
}

function Invoke-Backup {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupDir = ".\backups"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $dest = "$backupDir\alchemy_$timestamp.db"
    Write-Host "Backing up database to $dest ..." -ForegroundColor Cyan
    docker cp "${CONTAINER}:/app/data/alchemy.db" $dest
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Backup saved: $dest" -ForegroundColor Green
    }
    else {
        Write-Host "Backup failed. Is the container running?" -ForegroundColor Red
    }
}

function Invoke-Reset {
    Write-Host ""
    Write-Host "  WARNING: This will DELETE all data (database, users, trades)." -ForegroundColor Red
    $confirm = Read-Host "  Type 'yes' to confirm"
    if ($confirm -eq "yes") {
        Write-Host "Wiping all data and volumes..." -ForegroundColor Yellow
        dcd down -v
        dc up --build -d
        Write-Host ""
        Write-Host "Fresh start complete!" -ForegroundColor Green
        Write-Host "  Login: admin@alchemy.in / Alchemy#Admin!2024" -ForegroundColor White
    }
    else {
        Write-Host "Reset cancelled." -ForegroundColor Gray
    }
}

# Dispatch
switch ($Command.ToLower()) {
    "up"      { Invoke-Up }
    "dev"     { Invoke-Dev }
    "down"    { Invoke-Down }
    "logs"    { Invoke-Logs }
    "restart" { Invoke-Restart }
    "rebuild" { Invoke-Rebuild }
    "shell"   { Invoke-Shell }
    "test"    { Invoke-Test }
    "status"  { Invoke-Status }
    "health"  { Invoke-Health }
    "backup"  { Invoke-Backup }
    "reset"   { Invoke-Reset }
    "install" { Invoke-Install }
    "seed"    { Invoke-Seed }
    "help"    { Show-Help }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
