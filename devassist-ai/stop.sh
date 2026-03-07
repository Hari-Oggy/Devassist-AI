#!/usr/bin/env bash
# ============================================
# DevAssist AI — Linux/macOS Stop Script
# Usage: ./stop.sh
# ============================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "Stopping DevAssist AI..."

# Kill saved PIDs
if [ -f "$PROJECT_DIR/.pids" ]; then
    while read -r pid; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            echo "  ✅ Stopped process $pid"
        fi
    done < "$PROJECT_DIR/.pids"
    rm -f "$PROJECT_DIR/.pids"
fi

# Kill by port as fallback
if lsof -ti:8000 > /dev/null 2>&1; then
    kill $(lsof -ti:8000) 2>/dev/null
    echo "  ✅ Stopped API on port 8000"
fi
if lsof -ti:8501 > /dev/null 2>&1; then
    kill $(lsof -ti:8501) 2>/dev/null
    echo "  ✅ Stopped Streamlit on port 8501"
fi

# Optionally stop Redis
read -p "Stop Redis container too? (y/N) " yn
if [ "$yn" = "y" ]; then
    docker stop devassist-redis 2>/dev/null
    echo "  ✅ Redis stopped"
fi

echo ""
echo "DevAssist AI stopped."
