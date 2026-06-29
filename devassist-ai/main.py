"""
DevAssist AI v3.0 — Entry Point

This file is a convenience launcher. The real FastAPI app lives in api/main.py.

Usage:
    # Start the full stack (recommended):
    ./start.ps1         (Windows)
    ./start.sh          (Linux/macOS)

    # Start individual components manually:
    uv run uvicorn api.main:app --reload --port 8000   # API server
    uv run celery -A taskqueue.celery_app worker --pool=solo  # Celery worker (Windows)
    cd frontend && npm run dev                          # Next.js frontend

    # Expose API for webhooks:
    ngrok http 8000
    Set GitHub webhook to: https://<ngrok-url>/api/v3/github/webhook
"""

import sys
import os
import subprocess


def main():
    """Launch the DevAssist AI API server."""
    print(__doc__)
    print("Starting DevAssist AI API server on http://localhost:8000 ...")
    print("Press Ctrl+C to stop.\n")

    # Ensure we run from the project directory
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    try:
        # Try uv first (preferred package manager)
        uv_available = subprocess.run(
            ["uv", "--version"], capture_output=True, timeout=3
        ).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        uv_available = False

    if uv_available:
        cmd = ["uv", "run", "uvicorn", "api.main:app", "--reload", "--host","0.0.0.0","--port", "8000"]
    else:
        cmd = [sys.executable, "-m", "uvicorn", "api.main:app", "--reload", "--port", "8000"]

    try:
        subprocess.run(cmd, cwd=project_dir, check=True)
    except KeyboardInterrupt:
        print("\nDevAssist AI stopped.")
    except subprocess.CalledProcessError as e:
        print(f"\nError starting server: {e}")
        print("Make sure dependencies are installed: uv sync")
        sys.exit(1)


if __name__ == "__main__":
    main()
