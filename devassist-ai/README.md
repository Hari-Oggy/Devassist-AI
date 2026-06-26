# DevAssist AI v2.0

Autonomous code review and documentation agent powered by a **multi-LLM routing architecture**.

Supports **OpenAI**, **Anthropic (Claude)**, **Google Gemini**, and **local LLMs** (Ollama/vLLM/LM Studio).

## Architecture

```
Frontend (Streamlit)  →  FastAPI  →  Celery + Redis  →  Workers  →  Agents  →  LLM Router  →  Provider Adapters  →  LLM APIs
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys and preferred LLM_PROVIDER

# 3. Build FAISS index
python scripts/setup_index.py

# 4. Run integration tests
python scripts/integration_test.py

# 5. Start API server
uvicorn api.main:app --reload --port 8000

# 6. Start frontend (new terminal)
streamlit run frontend/app.py

# OR use Docker for everything
docker-compose up --build
```

## Configuration

Set `LLM_PROVIDER` in `.env` to switch providers:

| Provider       | Value       | Required Key        |
| -------------- | ----------- | ------------------- |
| OpenAI         | `openai`    | `OPENAI_API_KEY`    |
| Anthropic      | `anthropic` | `ANTHROPIC_API_KEY` |
| Google Gemini  | `gemini`    | `GEMINI_API_KEY`    |
| Local (Ollama) | `local`     | `LOCAL_API_BASE`    |

The router automatically falls back to other providers if the primary fails.

## URLs

- **Frontend:** http://localhost:8501
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

## Expose Local Development With ngrok

Use the ngrok CLI for local demos and webhook testing. It keeps tunneling outside
the application code and avoids starting public tunnels automatically in normal
development or production runs.

Install and authenticate ngrok once:

```powershell
ngrok config add-authtoken <your_ngrok_token>
```

Expose the FastAPI backend for GitHub/GitLab webhooks:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
.\scripts\start-ngrok.ps1 -Target api
```

When ngrok prints its HTTPS forwarding URL, use these webhook URLs:

```text
GitHub: https://<your-ngrok-url>/api/v3/github/webhook
GitLab:  https://<your-ngrok-url>/api/v3/gitlab/
```

Expose the Next.js frontend only when you want to share the UI:

```powershell
cd frontend
npm run dev
cd ..
.\scripts\start-ngrok.ps1 -Target frontend
```

If you have a reserved/static ngrok domain, pass it with `-Url` or set
`NGROK_URL`:

```powershell
.\scripts\start-ngrok.ps1 -Target api -Url https://your-domain.ngrok.app
```

Use `pyngrok` only if Python code needs to create and tear down tunnels
programmatically, such as in integration tests or a custom dev launcher.
