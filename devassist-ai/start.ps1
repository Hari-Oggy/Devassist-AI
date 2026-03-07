# ============================================
# DevAssist AI - Windows Startup Script
# Usage: .\start.ps1
# ============================================

$ErrorActionPreference = "Continue"
$PROJECT_DIR = $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    DevAssist AI v2.0 - Starting Up     " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# -------------------------------------------
# 0. Check .env file exists
# -------------------------------------------
Write-Host "[0/7] Checking .env file..." -ForegroundColor Yellow
if (-not (Test-Path "$PROJECT_DIR\.env")) {
    Write-Host "  ERROR: .env file not found. Copy .env.example to .env and fill in your values." -ForegroundColor Red
    exit 1
}
Write-Host "  OK: .env file found" -ForegroundColor Green

# -------------------------------------------
# 1. Check Python venv
# -------------------------------------------
Write-Host "[1/7] Checking virtual environment..." -ForegroundColor Yellow
if (Test-Path "$PROJECT_DIR\.venv\Scripts\Activate.ps1") {
    & "$PROJECT_DIR\.venv\Scripts\Activate.ps1"
    Write-Host "  OK: Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "  ERROR: .venv not found. Run 'python -m venv .venv' and 'pip install -r requirements.txt' first." -ForegroundColor Red
    exit 1
}

# -------------------------------------------
# 2. Install dependencies (if needed)
# -------------------------------------------
Write-Host "[2/7] Checking dependencies..." -ForegroundColor Yellow
python -c "import fastapi; import streamlit; import celery; import google.generativeai" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing missing dependencies..." -ForegroundColor Yellow
    & "$PROJECT_DIR\.venv\Scripts\pip.exe" install -r "$PROJECT_DIR\requirements.txt" --quiet
    Write-Host "  OK: Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  OK: All dependencies found" -ForegroundColor Green
}

# -------------------------------------------
# 3. Check / Start Redis via Docker
# -------------------------------------------
Write-Host "[3/7] Checking Redis..." -ForegroundColor Yellow
$redisRunning = docker ps --filter "name=devassist-redis" --format "{{.Names}}" 2>$null
if ($redisRunning -eq "devassist-redis") {
    Write-Host "  OK: Redis already running" -ForegroundColor Green
} else {
    $redisStopped = docker ps -a --filter "name=devassist-redis" --format "{{.Names}}" 2>$null
    if ($redisStopped -eq "devassist-redis") {
        Write-Host "  Starting existing Redis container..." -ForegroundColor Yellow
        docker start devassist-redis | Out-Null
    } else {
        Write-Host "  Starting new Redis container..." -ForegroundColor Yellow
        docker run -d --name devassist-redis -p 6379:6379 redis:alpine | Out-Null
    }
    Start-Sleep -Seconds 2
    Write-Host "  OK: Redis started on port 6379" -ForegroundColor Green
}

# -------------------------------------------
# 4. Build FAISS index (if missing)
# -------------------------------------------
Write-Host "[4/7] Checking FAISS index..." -ForegroundColor Yellow
$indexPath = "$PROJECT_DIR\data\faiss_index\index.faiss"
if (Test-Path $indexPath) {
    Write-Host "  OK: FAISS index exists" -ForegroundColor Green
} else {
    $codePath = python -c "from core.config import get_settings; print(get_settings().CODEBASE_PATH)" 2>$null
    if ($codePath -and (Test-Path $codePath)) {
        Write-Host "  Building FAISS index from $codePath ..." -ForegroundColor Yellow
        python "$PROJECT_DIR\scripts\setup_index.py"
        Write-Host "  OK: FAISS index built" -ForegroundColor Green
    } else {
        Write-Host "  SKIPPED: Set CODEBASE_PATH in .env to a valid repo folder" -ForegroundColor DarkYellow
    }
}

# Ensure PID directory exists
$pidDir = "$PROJECT_DIR\.pids"
if (-not (Test-Path $pidDir)) {
    New-Item -ItemType Directory -Path $pidDir | Out-Null
}

# Helper: stop process listening on a given port
function Stop-PortProcess {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        Write-Host "  Port $Port in use, stopping old process (PID: $($conn.OwningProcess))..." -ForegroundColor Yellow
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
}

# Helper: wait for an HTTP endpoint to respond
function Wait-ForEndpoint {
    param([string]$Url, [int]$MaxRetries = 15)
    $retries = 0
    while ($retries -lt $MaxRetries) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        } catch {
            Start-Sleep -Seconds 1
            $retries++
        }
    }
    return $false
}

# -------------------------------------------
# 5. Start API Server (background)
# -------------------------------------------
Write-Host "[5/7] Starting API server..." -ForegroundColor Yellow
Stop-PortProcess -Port 8000

$apiJob = Start-Process -FilePath "python" `
    -ArgumentList "-m uvicorn api.main:app --host 127.0.0.1 --port 8000" `
    -WorkingDirectory $PROJECT_DIR `
    -PassThru -WindowStyle Minimized

$apiJob.Id | Out-File "$pidDir\api.pid" -Force

Write-Host "  Waiting for API server..." -ForegroundColor DarkGray
if (Wait-ForEndpoint -Url "http://127.0.0.1:8000/health") {
    Write-Host "  OK: API server running at http://127.0.0.1:8000 (PID: $($apiJob.Id))" -ForegroundColor Green
    Write-Host "      Docs: http://127.0.0.1:8000/docs" -ForegroundColor DarkGray
} else {
    Write-Host "  WARNING: API server may not be ready yet - check logs" -ForegroundColor DarkYellow
}

# -------------------------------------------
# 6. Start Celery Worker (background)
# -------------------------------------------
Write-Host "[6/7] Starting Celery worker..." -ForegroundColor Yellow

$celeryJob = Start-Process -FilePath "python" `
    -ArgumentList "-m celery -A core.celery_app worker --loglevel=info" `
    -WorkingDirectory $PROJECT_DIR `
    -PassThru -WindowStyle Minimized

$celeryJob.Id | Out-File "$pidDir\celery.pid" -Force
Start-Sleep -Seconds 2
Write-Host "  OK: Celery worker started (PID: $($celeryJob.Id))" -ForegroundColor Green

# -------------------------------------------
# 7. Start Streamlit Frontend (background)
# -------------------------------------------
Write-Host "[7/7] Starting Streamlit frontend..." -ForegroundColor Yellow
Stop-PortProcess -Port 8501

$stJob = Start-Process -FilePath "python" `
    -ArgumentList "-m streamlit run frontend/app.py --server.port 8501 --server.headless true" `
    -WorkingDirectory $PROJECT_DIR `
    -PassThru -WindowStyle Minimized

$stJob.Id | Out-File "$pidDir\streamlit.pid" -Force

Write-Host "  Waiting for Streamlit..." -ForegroundColor DarkGray
if (Wait-ForEndpoint -Url "http://localhost:8501") {
    Write-Host "  OK: Streamlit running at http://localhost:8501 (PID: $($stJob.Id))" -ForegroundColor Green
} else {
    Write-Host "  WARNING: Streamlit may not be ready yet - check logs" -ForegroundColor DarkYellow
}

# -------------------------------------------
# Done!
# -------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    DevAssist AI is READY!              " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Frontend:  http://localhost:8501" -ForegroundColor White
Write-Host "  API:       http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  API Docs:  http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "  Health:    http://127.0.0.1:8000/health" -ForegroundColor White
Write-Host ""
Write-Host "  PIDs saved to .pids\ - run .\stop.ps1 to shut everything down." -ForegroundColor DarkGray
Write-Host ""

Start-Process "http://localhost:8501"