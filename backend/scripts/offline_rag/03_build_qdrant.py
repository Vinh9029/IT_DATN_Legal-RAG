import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from config.settings import (
    PROCESSED_DATA_DIR, 
    ensure_directories,
    QDRANT_HOST,
    QDRANT_PORT,
    QDRANT_COLLECTION_NAME,
    EMBEDDING_MODEL,
    EMBEDDING_DIM
)
from src.indexing.qdrant_builder import build_qdrant_index
from loguru import logger

def main():
    ensure_directories()
    
    chunks_path = PROCESSED_DATA_DIR / "chunks" / "chunks.jsonl"
    
    if not chunks_path.exists():
        logger.error(f"File {chunks_path} không tồn tại. Vui lòng chạy 02_chunk_documents.py trước.")
        sys.exit(1)
        
    logger.info("=== BẮT ĐẦU BUILD VECTOR INDEX TRÊN QDRANT (LOCAL DOCKER) ===")
    build_qdrant_index(
        chunks_path=chunks_path,
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        collection_name=QDRANT_COLLECTION_NAME,
        model_name=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        batch_size=128
    )

if __name__ == "__main__":
    main()
