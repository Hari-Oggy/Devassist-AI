# ============================================
# DevAssist AI — Windows Stop Script
# Usage: .\stop.ps1
# ============================================

Write-Host ""
Write-Host "Stopping DevAssist AI..." -ForegroundColor Yellow

# Stop API (uvicorn on port 8000)
$apiProcs = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pid in $apiProcs) {
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Write-Host "  ✅ Stopped API server (PID: $pid)" -ForegroundColor Green
}

# Stop Streamlit (on port 8501)
$stProcs = Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pid in $stProcs) {
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Write-Host "  ✅ Stopped Streamlit (PID: $pid)" -ForegroundColor Green
}

# Optionally stop Redis
$stopRedis = Read-Host "Stop Redis container too? (y/N)"
if ($stopRedis -eq "y") {
    docker stop devassist-redis 2>$null | Out-Null
    Write-Host "  ✅ Redis stopped" -ForegroundColor Green
}

Write-Host ""
Write-Host "DevAssist AI stopped." -ForegroundColor Cyan
