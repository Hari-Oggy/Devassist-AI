#!/usr/bin/env bash
# ============================================
# DevAssist AI — Linux/macOS Startup Script
# Usage: chmod +x start.sh && ./start.sh
# ============================================

set -e
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "========================================"
echo "    DevAssist AI v2.0 — Starting Up     "
echo "========================================"
echo ""

# -------------------------------------------
# 1. Check Python venv
# -------------------------------------------
echo "[1/6] Checking virtual environment..."
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    source "$PROJECT_DIR/.venv/bin/activate"
    echo "  ✅ Virtual environment activated"
else
    echo "  ❌ .venv not found. Run 'python -m venv .venv && pip install -r requirements.txt' first."
    exit 1
fi

# -------------------------------------------
# 2. Install dependencies (if needed)
# -------------------------------------------
echo "[2/6] Checking dependencies..."
if python -c "import fastapi; import streamlit; import celery; import google.genai" 2>/dev/null; then
    echo "  ✅ All dependencies OK"
else
    echo "  📦 Installing dependencies..."
    pip install -r "$PROJECT_DIR/requirements.txt" --quiet
fi

# -------------------------------------------
# 3. Check / Start Redis via Docker
# -------------------------------------------
echo "[3/6] Checking Redis..."
if docker ps --filter "name=devassist-redis" --format "{{.Names}}" 2>/dev/null | grep -q "devassist-redis"; then
    echo "  ✅ Redis already running"
elif docker ps -a --filter "name=devassist-redis" --format "{{.Names}}" 2>/dev/null | grep -q "devassist-redis"; then
    echo "  🔄 Starting existing Redis container..."
    docker start devassist-redis > /dev/null
    sleep 2
    echo "  ✅ Redis started on port 6379"
else
    echo "  🚀 Starting new Redis container..."
    docker run -d --name devassist-redis -p 6379:6379 redis:alpine > /dev/null
    sleep 2
    echo "  ✅ Redis started on port 6379"
fi

# -------------------------------------------
# 4. Build FAISS index (if missing)
# -------------------------------------------
echo "[4/6] Checking FAISS index..."
if [ -f "$PROJECT_DIR/data/faiss_index/index.faiss" ]; then
    echo "  ✅ FAISS index exists"
else
    CODE_PATH=$(python -c "from core.config import get_settings; print(get_settings().CODEBASE_PATH)" 2>/dev/null || echo "")
    if [ -n "$CODE_PATH" ] && [ -d "$CODE_PATH" ]; then
        echo "  📦 Building FAISS index from $CODE_PATH ..."
        python "$PROJECT_DIR/scripts/setup_index.py"
        echo "  ✅ FAISS index built"
    else
        echo "  ⚠️  Skipped — set CODEBASE_PATH in .env to a valid repo folder"
    fi
fi

# -------------------------------------------
# 5. Start API Server (background)
# -------------------------------------------
echo "[5/6] Starting API server..."

# Kill existing process on port 8000
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "  🔄 Port 8000 in use, stopping old process..."
    kill $(lsof -ti:8000) 2>/dev/null || true
    sleep 1
fi

python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
sleep 3
echo "  ✅ API server running at http://127.0.0.1:8000 (PID: $API_PID)"
echo "     📖 API Docs: http://127.0.0.1:8000/docs"

# -------------------------------------------
# 6. Start Streamlit Frontend (background)
# -------------------------------------------
echo "[6/6] Starting Streamlit frontend..."

python -m streamlit run frontend/app.py --server.port 8501 --server.headless true &
ST_PID=$!
sleep 3
echo "  ✅ Streamlit running at http://localhost:8501 (PID: $ST_PID)"

# -------------------------------------------
# Done!
# -------------------------------------------
echo ""
echo "========================================"
echo "    DevAssist AI is READY!              "
echo "========================================"
echo ""
echo "  🌐 Frontend:  http://localhost:8501"
echo "  🔌 API:       http://127.0.0.1:8000"
echo "  📖 API Docs:  http://127.0.0.1:8000/docs"
echo "  🩺 Health:    http://127.0.0.1:8000/health"
echo ""
echo "  To stop: kill $API_PID $ST_PID"
echo "           or run: ./stop.sh"
echo ""

# Save PIDs for stop script
echo "$API_PID" > "$PROJECT_DIR/.pids"
echo "$ST_PID" >> "$PROJECT_DIR/.pids"

# Open browser (best effort)
if command -v xdg-open > /dev/null; then
    xdg-open "http://localhost:8501" 2>/dev/null &
elif command -v open > /dev/null; then
    open "http://localhost:8501" 2>/dev/null &
fi

# Wait for background processes
wait
