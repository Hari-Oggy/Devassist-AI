# ============================================
# DevAssist AI - Windows Stop Script
# Usage: .\stop.ps1
# ============================================

$ErrorActionPreference = "Continue"
$PROJECT_DIR = $PSScriptRoot
$pidDir = "$PROJECT_DIR\.pids"

Write-Host ""
Write-Host "Stopping DevAssist AI..." -ForegroundColor Yellow

# Helper: stop by port, fallback to PID file
function Stop-Service {
    param([string]$Name, [int]$Port, [string]$PidFile)

    $stopped = $false

    # Try port first
    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $conns) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "  OK: Stopped $Name via port $Port (PID: $procId)" -ForegroundColor Green
        $stopped = $true
    }

    # Fallback to PID file
    if (-not $stopped -and (Test-Path $PidFile)) {
        $procId = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($procId) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Write-Host "  OK: Stopped $Name via PID file (PID: $procId)" -ForegroundColor Green
            $stopped = $true
        }
    }

    if (-not $stopped) {
        Write-Host "  INFO: $Name was not running" -ForegroundColor DarkGray
    }

    # Clean up PID file
    if (Test-Path $PidFile) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

# Stop API server (port 8000)
Stop-Service -Name "API server" -Port 8000 -PidFile "$pidDir\api.pid"

# Stop Streamlit (port 8501)
Stop-Service -Name "Streamlit" -Port 8501 -PidFile "$pidDir\streamlit.pid"

# Stop Celery worker (no port, PID file only)
if (Test-Path "$pidDir\celery.pid") {
    $procId = Get-Content "$pidDir\celery.pid" -ErrorAction SilentlyContinue
    if ($procId) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "  OK: Stopped Celery worker (PID: $procId)" -ForegroundColor Green
    }
    Remove-Item "$pidDir\celery.pid" -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "  INFO: Celery worker was not running" -ForegroundColor DarkGray
}

# Optionally stop Redis
$stopRedis = Read-Host "Stop Redis container too? (y/N)"
if ($stopRedis.ToLower() -eq "y") {
    docker stop devassist-redis 2>$null | Out-Null
    Write-Host "  OK: Redis stopped" -ForegroundColor Green
} else {
    Write-Host "  INFO: Redis left running" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "DevAssist AI stopped." -ForegroundColor Cyan
Write-Host ""