import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from config.settings import (
    PROCESSED_DATA_DIR, 
    ensure_directories,
    PINECONE_API_KEY,
    PINECONE_ENVIRONMENT,
    PINECONE_INDEX_NAME,
    EMBEDDING_MODEL,
    EMBEDDING_DIM
)
from src.indexing.pinecone_builder import build_pinecone_index
from loguru import logger

def main():
    ensure_directories()
    
    chunks_path = PROCESSED_DATA_DIR / "chunks" / "chunks.jsonl"
    
    if not chunks_path.exists():
        logger.error(f"File {chunks_path} không tồn tại. Vui lòng chạy 02_chunk_documents.py trước.")
        sys.exit(1)
        
    build_pinecone_index(
        chunks_path=chunks_path,
        api_key=PINECONE_API_KEY,
        env=PINECONE_ENVIRONMENT,
        index_name=PINECONE_INDEX_NAME,
        model_name=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM
    )

if __name__ == "__main__":
    main()
