import requests
import json
import sys
import os
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

def test_api_status():
    try:
        response = requests.get(f"{API_URL}/status")
        print(f"API Status: {response.json()}")
    except Exception as e:
        print(f"Error connecting to API: {e}")

def test_review(pr_number: int):
    print(f"Testing PR review for PR #{pr_number}...")
    try:
        response = requests.post(f"{API_URL}/review", json={"pr_number": pr_number})
        data = response.json()
        print(json.dumps(data, indent=2))
        print(f"Count of comments generated: {len(data.get('comments', []))}")
    except Exception as e:
        print(f"Error testing review: {e}")

def test_documentation(file_path: str):
    print(f"Testing documentation for {file_path}...")
    try:
        response = requests.post(f"{API_URL}/document", json={"file_path": file_path, "save_updated": False})
        data = response.json()
        print(f"Number of items documented: {data.get('changes_made', 0)}")
        
        markdown = data.get("markdown", "")
        if markdown:
            print("\nPreview of markdown:\n" + markdown[:500] + "...\n")
        else:
            print("No markdown generated.")
    except Exception as e:
        print(f"Error testing documentation: {e}")

if __name__ == "__main__":
    print(f"Using API URL: {API_URL}")
    test_api_status()
    
    if len(sys.argv) > 1:
        if sys.argv[1].isdigit():
            test_review(int(sys.argv[1]))
        elif len(sys.argv) > 2 and sys.argv[1] == "--doc":
            test_documentation(sys.argv[2])
        else:
            test_documentation(sys.argv[1])
    else:
        print("\nUsage instructions:")
        print("  python test_review.py <pr_number>       - Test PR review")
        print("  python test_review.py <file_path>       - Test documentation generation")
