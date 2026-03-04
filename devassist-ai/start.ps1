# ============================================
# DevAssist AI — Windows Startup Script
# Usage: .\start.ps1
# ============================================

$ErrorActionPreference = "Continue"
$PROJECT_DIR = $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    DevAssist AI v2.0 — Starting Up     " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# -------------------------------------------
# 1. Check Python venv
# -------------------------------------------
Write-Host "[1/6] Checking virtual environment..." -ForegroundColor Yellow
if (Test-Path "$PROJECT_DIR\.venv\Scripts\activate.ps1") {
    & "$PROJECT_DIR\.venv\Scripts\Activate.ps1"
    Write-Host "  ✅ Virtual environment activated" -ForegroundColor Green
} else {
    Write-Host "  ❌ .venv not found. Run 'uv init' and 'uv pip install -r requirements.txt' first." -ForegroundColor Red
    exit 1
}

# -------------------------------------------
# 2. Install dependencies (if needed)
# -------------------------------------------
Write-Host "[2/6] Checking dependencies..." -ForegroundColor Yellow
$missing = $false
python -c "import fastapi; import streamlit; import celery; import google.genai" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  📦 Installing dependencies..." -ForegroundColor Yellow
    pip install -r "$PROJECT_DIR\requirements.txt" --quiet
    $missing = $true
}
if (-not $missing) {
    Write-Host "  ✅ All dependencies OK" -ForegroundColor Green
}

# -------------------------------------------
# 3. Check / Start Redis via Docker
# -------------------------------------------
Write-Host "[3/6] Checking Redis..." -ForegroundColor Yellow
$redisRunning = docker ps --filter "name=devassist-redis" --format "{{.Names}}" 2>$null
if ($redisRunning -eq "devassist-redis") {
    Write-Host "  ✅ Redis already running" -ForegroundColor Green
} else {
    # Check if container exists but is stopped
    $redisStopped = docker ps -a --filter "name=devassist-redis" --format "{{.Names}}" 2>$null
    if ($redisStopped -eq "devassist-redis") {
        Write-Host "  🔄 Starting existing Redis container..." -ForegroundColor Yellow
        docker start devassist-redis | Out-Null
    } else {
        Write-Host "  🚀 Starting new Redis container..." -ForegroundColor Yellow
        docker run -d --name devassist-redis -p 6379:6379 redis:alpine | Out-Null
    }
    Start-Sleep -Seconds 2
    Write-Host "  ✅ Redis started on port 6379" -ForegroundColor Green
}

# -------------------------------------------
# 4. Build FAISS index (if missing)
# -------------------------------------------
Write-Host "[4/6] Checking FAISS index..." -ForegroundColor Yellow
$indexPath = "$PROJECT_DIR\data\faiss_index\index.faiss"
if (Test-Path $indexPath) {
    Write-Host "  ✅ FAISS index exists" -ForegroundColor Green
} else {
    $codePath = python -c "from core.config import get_settings; print(get_settings().CODEBASE_PATH)" 2>$null
    if ($codePath -and (Test-Path $codePath)) {
        Write-Host "  📦 Building FAISS index from $codePath ..." -ForegroundColor Yellow
        python "$PROJECT_DIR\scripts\setup_index.py"
        Write-Host "  ✅ FAISS index built" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Skipped — set CODEBASE_PATH in .env to a valid repo folder" -ForegroundColor DarkYellow
    }
}

# -------------------------------------------
# 5. Start API Server (background)
# -------------------------------------------
Write-Host "[5/6] Starting API server..." -ForegroundColor Yellow

# Kill any existing API process on port 8000
$existingApi = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existingApi) {
    Write-Host "  🔄 Port 8000 in use, stopping old process..." -ForegroundColor Yellow
    Stop-Process -Id $existingApi.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

$apiJob = Start-Process -FilePath "python" -ArgumentList "-m uvicorn api.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $PROJECT_DIR -PassThru -WindowStyle Minimized
Start-Sleep -Seconds 3
Write-Host "  ✅ API server running at http://127.0.0.1:8000 (PID: $($apiJob.Id))" -ForegroundColor Green
Write-Host "     📖 API Docs: http://127.0.0.1:8000/docs" -ForegroundColor DarkGray

# -------------------------------------------
# 6. Start Streamlit Frontend (background)
# -------------------------------------------
Write-Host "[6/6] Starting Streamlit frontend..." -ForegroundColor Yellow

$stJob = Start-Process -FilePath "python" -ArgumentList "-m streamlit run frontend/app.py --server.port 8501 --server.headless true" -WorkingDirectory $PROJECT_DIR -PassThru -WindowStyle Minimized
Start-Sleep -Seconds 3
Write-Host "  ✅ Streamlit running at http://localhost:8501 (PID: $($stJob.Id))" -ForegroundColor Green

# -------------------------------------------
# Done!
# -------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    DevAssist AI is READY!              " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  🌐 Frontend:  http://localhost:8501" -ForegroundColor White
Write-Host "  🔌 API:       http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  📖 API Docs:  http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "  🩺 Health:    http://127.0.0.1:8000/health" -ForegroundColor White
Write-Host ""
Write-Host "  To stop: Close the minimized terminal windows or run .\stop.ps1" -ForegroundColor DarkGray
Write-Host ""

# Open browser
Start-Process "http://localhost:8501"
