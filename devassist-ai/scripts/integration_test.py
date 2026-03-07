"""
DevAssist AI — End-to-End Integration Test.
Tests all system components: env, LLM Router, GitHub, RAG, Redis, API.
"""

import sys
import os
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from core.config import get_settings


def main():
    print("================")
    print("INTEGRATION TEST")
    print("================\n")

    settings = get_settings()
    results = {}

    # 1. Environment variables
    print("--- Environment ---")
    required = {
        "OPENAI_API_KEY": settings.OPENAI_API_KEY,
        "GITHUB_TOKEN": settings.GITHUB_TOKEN,
        "GITHUB_REPO": settings.GITHUB_REPO,
        "CODEBASE_PATH": settings.CODEBASE_PATH,
    }
    env_ok = True
    for key, val in required.items():
        ok = bool(val) and val not in ("your_openai_api_key_here", "your_github_personal_access_token_here", "owner/repository-name")
        status = "✅" if ok else "❌"
        print(f"  {key}: {status}")
        if not ok:
            env_ok = False
    results["Environment"] = "✅" if env_ok else "❌"

    # 2. LLM Router — test the configured provider
    print("\n--- LLM Router ---")
    llm_ok = False
    try:
        from llm.router import LLMRouter
        from llm.schemas import LLMRequest
        router = LLMRouter()
        req = LLMRequest(
            task_type="general",
            messages=[{"role": "user", "content": "Reply with just the word OK"}],
            max_tokens=10,
        )
        resp = router.generate(req)
        if resp.success:
            print(f"  Provider: {resp.provider} | Model: {resp.model}")
            print(f"  Response: {resp.content.strip()}")
            llm_ok = True
        else:
            print(f"  Error: {resp.error}")
    except Exception as e:
        print(f"  Error: {e}")
    results["LLM Router"] = "✅" if llm_ok else "❌"

    # 3. RAG System
    print("\n--- RAG System ---")
    rag_ok = False
    if os.path.exists(settings.FAISS_INDEX_PATH):
        try:
            from rag.retriever import CodebaseRetriever
            retriever = CodebaseRetriever(settings.FAISS_INDEX_PATH)
            ctx = retriever.get_context("error handling", k=1)
            print(f"  Preview: {ctx[:150].replace(chr(10), ' ')}...")
            rag_ok = True
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print("  Index not found. Run: python scripts/setup_index.py")
    results["RAG System"] = "✅" if rag_ok else "❌"

    # 4. GitHub
    print("\n--- GitHub ---")
    github_ok = False
    try:
        from github import Github
        gh = Github(settings.GITHUB_TOKEN)
        repo = gh.get_repo(settings.GITHUB_REPO)
        print(f"  Found repo: {repo.full_name}")
        prs = list(repo.get_pulls(state='open', sort='created', direction='desc')[:3])
        if prs:
            for pr in prs:
                print(f"    PR #{pr.number}: {pr.title}")
        else:
            print("    No open PRs found (that's OK)")
        github_ok = True
    except Exception as e:
        print(f"  Error: {e}")
    results["GitHub"] = "✅" if github_ok else "❌"

    # 5. Redis / Celery
    print("\n--- Redis Queue ---")
    redis_ok = False
    try:
        import redis as redis_lib
        r = redis_lib.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
        print(f"  Connected to Redis at {settings.REDIS_URL}")
        redis_ok = True
    except Exception as e:
        print(f"  Redis unavailable (sync fallback active): {e}")
    results["Redis Queue"] = "✅" if redis_ok else "❌"

    # 6. API Server
    print("\n--- API Server ---")
    api_ok = False
    api_url = f"http://{settings.API_HOST}:{settings.API_PORT}"
    try:
        resp = requests.get(f"{api_url}/status", timeout=5)
        if resp.status_code == 200:
            print(f"  API Status: {resp.json()}")
            api_ok = True
    except Exception:
        print(f"  API not running — start with: uvicorn api.main:app --reload")
    results["API Server"] = "✅" if api_ok else "❌"

    # Summary
    print("\n==================")
    print("  RESULTS SUMMARY")
    print("==================")
    for name, status in results.items():
        print(f"  {name:15s}: {status}")
    print("==================\n")


if __name__ == "__main__":
    main()
