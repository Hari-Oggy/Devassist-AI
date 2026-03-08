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

<img width="1024" height="559" alt="image" src="https://github.com/user-attachments/assets/42361dd9-333a-4164-9878-27da05599428" />

#REUSLT
<img width="1920" height="1080" alt="Screenshot 2026-03-08 100442" src="https://github.com/user-attachments/assets/66ec43ed-7f5f-4691-9d79-c9ade427a845" />




https://github.com/user-attachments/assets/662eb92e-4f4b-46a0-9f62-921fc1873c88


