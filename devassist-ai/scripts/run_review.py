"""
Run a PR review directly (no HTTP server needed).
Usage: python scripts/run_review.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agents.review_agent import ReviewAgent

PR_NUMBER = 2  # https://github.com/HAREESH14/casestudy/pull/1

def main():
    print("=== DevAssist AI — Code Review ===")
    print(f"Reviewing PR #{PR_NUMBER}...\n")

    agent = ReviewAgent()
    result = agent.review_pr(PR_NUMBER)

    print("\n=== RESULT ===")
    print(f"Success       : {result['success']}")
    print(f"Provider/Model: {result.get('provider_used')} / {result.get('model_used')}")
    print(f"Files reviewed: {result.get('files_reviewed')}")
    print(f"Comments posted to GitHub: {len(result.get('comments', []))}")

    print("\n--- Audit Log ---")
    for entry in result.get("audit_log", []):
        print(entry)

    if not result["success"]:
        print(f"\nError: {result.get('error')}")

if __name__ == "__main__":
    main()
