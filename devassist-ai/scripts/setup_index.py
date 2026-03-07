import sys
import os
import time
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.indexer import CodebaseIndexer

def main():
    load_dotenv()
    CODEBASE_PATH = os.getenv("CODEBASE_PATH", "./local_repo")
    FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./data/faiss_index")
    
    print("================================")
    print("DevAssist AI — Codebase Indexer")
    print("================================")
    
    if not os.path.exists(CODEBASE_PATH):
        print(f"Error: CODEBASE_PATH '{CODEBASE_PATH}' does not exist.")
        sys.exit(1)
        
    os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
    
    print(f"Scanning codebase at: {CODEBASE_PATH}")
    start_time = time.time()
    
    try:
        indexer = CodebaseIndexer(CODEBASE_PATH, FAISS_INDEX_PATH)
        indexer.build_index()
        elapsed = time.time() - start_time
        stats = indexer.get_stats()
        
        print("\n✅ Index built successfully!")
        print(f"📁 Files indexed: {stats['files_indexed']}")
        print(f"📦 Chunks created: {stats['chunks_created']}")
        print(f"⏱️  Time taken: {elapsed:.1f}s")
        print(f"💾 Saved to: {FAISS_INDEX_PATH}")
    except Exception as e:
        print(f"\n❌ Error building index: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
