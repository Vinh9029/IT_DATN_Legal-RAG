import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from config.settings import PROCESSED_DATA_DIR, INDEXES_DIR, ensure_directories
from src.indexing.bm25_builder import build_bm25_index

def main():
    ensure_directories()
    
    chunks_path = PROCESSED_DATA_DIR / "chunks" / "chunks.jsonl"
    bm25_output_dir = INDEXES_DIR / "bm25"
    
    if not chunks_path.exists():
        print(f"File {chunks_path} không tồn tại. Vui lòng chạy 02_chunk_documents.py trước.")
        sys.exit(1)
        
    build_bm25_index(chunks_path, bm25_output_dir)

if __name__ == "__main__":
    main()
