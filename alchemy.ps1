# ─────────────────────────────────────────────────────────────────────────────
# Alchemy Trading Platform — Windows PowerShell Helper
# Usage: .\alchemy.ps1 <command>
#
# Commands:
#   .\alchemy.ps1 up        → Build + start (http://localhost:8000)
#   .\alchemy.ps1 dev       → Start + React hot-reload at :3000
#   .\alchemy.ps1 down      → Stop all containers
#   .\alchemy.ps1 logs      → Tail API logs
#   .\alchemy.ps1 restart   → Restart API (no rebuild)
#   .\alchemy.ps1 rebuild   → Force full image rebuild
#   .\alchemy.ps1 shell     → Open bash inside API container
#   .\alchemy.ps1 test      → Run unit tests inside container
#   .\alchemy.ps1 status    → Container status
#   .\alchemy.ps1 health    → Check API health
#   .\alchemy.ps1 backup    → Backup SQLite DB to .\backups\
#   .\alchemy.ps1 reset     → ⚠ Wipe all data and restart fresh
#   .\alchemy.ps1 help      → Show this help
# ─────────────────────────────────────────────────────────────────────────────

param([string]$Command = "help")

$COMPOSE      = "docker compose -f docker-compose.local.yml"
$COMPOSE_DEV  = "docker compose -f docker-compose.local.yml --profile dev"
$CONTAINER    = "alchemy-api"
$Image        = "alchemy:local"

function Write-Banner {
    Write-Host ""
    Write-Host "  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@" -ForegroundColor Cyan
    Write-Host "  @@@  Alchemy Trading Platform — Docker     @@@" -ForegroundColor Cyan
    Write-Host "  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@" -ForegroundColor Cyan
    Write-Host ""
}

function Show-Help {
    Write-Banner
    Write-Host "  Usage: .\alchemy.ps1 <command>" -ForegroundColor White
    Write-Host ""
    Write-Host "  Commands:" -ForegroundColor Yellow
    $cmds = @(
        @("up",      "Build + start everything  →  http://localhost:8000"),
        @("dev",     "Start + React hot-reload  →  http://localhost:3000"),
        @("down",    "Stop all containers"),
        @("logs",    "Tail API logs (Ctrl+C to stop)"),
        @("restart", "Restart API without rebuild"),
        @("rebuild", "Force full image rebuild"),
        @("shell",   "Open bash shell inside API container"),
        @("test",    "Run 134 unit tests inside container"),
        @("status",  "Show container status + resource usage"),
        @("health",  "Check API health endpoint"),
        @("backup",  "Backup SQLite DB to .\backups\"),
        @("reset",   "WARNING: Wipe all data and restart fresh"),
        @("help",    "Show this help")
    )
    foreach ($cmd in $cmds) {
        Write-Host ("    {0,-12} {1}" -f $cmd[0], $cmd[1]) -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "  Quick start:" -ForegroundColor Yellow
    Write-Host "    .\alchemy.ps1 up" -ForegroundColor Green
    Write-Host ""
}

function Invoke-Up {
    Write-Host "Building Alchemy..." -ForegroundColor Cyan
    Invoke-Expression "$COMPOSE up --build -d"
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "  Alchemy is starting up!" -ForegroundColor Green
        Write-Host "  API + Frontend : http://localhost:8000" -ForegroundColor White
        Write-Host "  API Docs       : http://localhost:8000/docs" -ForegroundColor White
        Write-Host "  Login          : admin@alchemy.in / Alchemy#Admin!2024" -ForegroundColor White
        Write-Host ""
        Write-Host "  Waiting for health check..." -ForegroundColor Gray
        Start-Sleep -Seconds 8
        try {
            $resp = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
            Write-Host "  Health: $($resp | ConvertTo-Json -Compress)" -ForegroundColor Green
        } catch {
            Write-Host "  Still starting — check: .\alchemy.ps1 logs" -ForegroundColor Yellow
        }
    }
}

function Invoke-Dev {
    Write-Host "Starting dev stack (API + React hot-reload)..." -ForegroundColor Cyan
    Invoke-Expression "$COMPOSE_DEV up --build -d"
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "  Dev stack started!" -ForegroundColor Green
        Write-Host "  React Dev UI   : http://localhost:3000  <- use this" -ForegroundColor White
        Write-Host "  API Backend    : http://localhost:8000" -ForegroundColor White
        Write-Host "  API Docs       : http://localhost:8000/docs" -ForegroundColor White
        Write-Host ""
    }
}

function Invoke-Down {
    Write-Host "Stopping all containers..." -ForegroundColor Yellow
    Invoke-Expression "$COMPOSE_DEV down"
    Write-Host "All containers stopped." -ForegroundColor Green
}

function Invoke-Logs {
    Write-Host "Tailing API logs (Ctrl+C to stop)..." -ForegroundColor Cyan
    Invoke-Expression "$COMPOSE logs -f api"
}

function Invoke-Restart {
    Write-Host "Restarting API..." -ForegroundColor Cyan
    Invoke-Expression "$COMPOSE restart api"
    Write-Host "API restarted." -ForegroundColor Green
}

function Invoke-Rebuild {
    Write-Host "Force rebuilding images..." -ForegroundColor Cyan
    Invoke-Expression "$COMPOSE build --no-cache"
    Invoke-Expression "$COMPOSE up -d"
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
    Invoke-Expression "$COMPOSE_DEV ps"
    Write-Host ""
    Write-Host "Resource usage:" -ForegroundColor Cyan
    docker stats --no-stream --format "table {{.Name}}`t{{.CPUPerc}}`t{{.MemUsage}}`t{{.Status}}" 2>$null
}

function Invoke-Health {
    Write-Host "Checking API health..." -ForegroundColor Cyan
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8000/health"
        Write-Host ($resp | ConvertTo-Json) -ForegroundColor Green
    } catch {
        Write-Host "API not responding. Is it running? Try: .\alchemy.ps1 up" -ForegroundColor Red
    }
}

function Invoke-Backup {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupDir = ".\backups"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $dest = "$backupDir\alchemy_$timestamp.db"
    Write-Host "Backing up database..." -ForegroundColor Cyan
    docker cp "${CONTAINER}:/app/data/alchemy.db" $dest
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Database backed up to: $dest" -ForegroundColor Green
    } else {
        Write-Host "Backup failed — is the container running?" -ForegroundColor Red
    }
}

function Invoke-Reset {
    Write-Host ""
    Write-Host "  WARNING: This will DELETE all data (database, users, trades)." -ForegroundColor Red
    $confirm = Read-Host "  Type 'yes' to confirm"
    if ($confirm -eq "yes") {
        Write-Host "Wiping all data..." -ForegroundColor Yellow
        Invoke-Expression "$COMPOSE_DEV down -v"
        Invoke-Expression "$COMPOSE up --build -d"
        Write-Host ""
        Write-Host "Fresh start complete!" -ForegroundColor Green
        Write-Host "  Login: admin@alchemy.in / Alchemy#Admin!2024" -ForegroundColor White
    } else {
        Write-Host "Reset cancelled." -ForegroundColor Gray
    }
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
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
    "help"    { Show-Help }
    default   {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Help
    }
}
