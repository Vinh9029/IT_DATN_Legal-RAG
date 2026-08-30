import sys
import json
from pathlib import Path
from tqdm import tqdm

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from config.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR, ensure_directories
from src.preprocessing.chunker import chunk_document
from loguru import logger

def main():
    ensure_directories()
    
    cache_path = RAW_DATA_DIR / "preprocessed_cache.jsonl"
    if not cache_path.exists():
        logger.error(f"File {cache_path} không tồn tại. Chạy 01_fix_preprocess.py trước!")
        sys.exit(1)
        
    chunk_dir = PROCESSED_DATA_DIR / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    
    chunk_path = chunk_dir / "chunks.jsonl"
    
    logger.info(f"Đọc dữ liệu từ: {cache_path}")
    total_chunks = 0
    
    with open(cache_path, "r", encoding="utf-8") as f_in, \
         open(chunk_path, "w", encoding="utf-8") as f_out:
        
        # Đếm số dòng (optional, để làm tqdm)
        # Vì file lớn, tạm thời dùng chunk
        
        for line in tqdm(f_in, desc="Đang chunking"):
            doc = json.loads(line)
            chunks = chunk_document(doc)
            
            for chunk in chunks:
                f_out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                total_chunks += 1

    logger.info(f"Hoàn thành! Tạo ra {total_chunks} chunks.")
    logger.info(f"Lưu tại: {chunk_path}")

if __name__ == "__main__":
    main()
