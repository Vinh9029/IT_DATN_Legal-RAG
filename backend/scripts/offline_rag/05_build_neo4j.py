import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from config.settings import (
    PROCESSED_DATA_DIR, 
    ensure_directories,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    HF_DATASET_NAME
)
from src.indexing.neo4j_builder import build_neo4j_graph
from loguru import logger

def main():
    ensure_directories()
    
    chunks_path = PROCESSED_DATA_DIR / "chunks" / "chunks.jsonl"
    
    if not chunks_path.exists():
        logger.error(f"File {chunks_path} không tồn tại. Vui lòng chạy 02_chunk_documents.py trước.")
        sys.exit(1)
        
    build_neo4j_graph(
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
        dataset_name=HF_DATASET_NAME,
        chunks_path=chunks_path
    )

if __name__ == "__main__":
    main()
