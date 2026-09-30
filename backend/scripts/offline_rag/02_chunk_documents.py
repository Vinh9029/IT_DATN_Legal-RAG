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
    temp_chunk_path = chunk_dir / "chunks.jsonl.tmp"
    
    logger.info(f"Đọc dữ liệu từ: {cache_path}")
    total_chunks = 0
    corrupted_lines = 0
    
    with open(cache_path, "r", encoding="utf-8") as f_in, \
         open(temp_chunk_path, "w", encoding="utf-8") as f_out:
        
        skipped_status = 0
        total_docs = 0

        # Các trạng thái văn bản không còn giá trị áp dụng cần loại bỏ
        EXCLUDED_STATUSES = {
            "hết hiệu lực toàn bộ",
            "không còn phù hợp",
            "ngưng hiệu lực"
        }

        for line_idx, line in enumerate(tqdm(f_in, desc="Đang chunking"), 1):
            line = line.strip()
            if not line:
                continue
            total_docs += 1
            try:
                doc = json.loads(line, strict=False)
            except json.JSONDecodeError as e:
                corrupted_lines += 1
                logger.warning(f"Bỏ qua dòng {line_idx} do lỗi JSON decode: {e}")
                continue
            
            # Lọc theo tình trạng hiệu lực
            status = doc.get("metadata", {}).get("tinh_trang", "").strip().lower()
            if status in EXCLUDED_STATUSES:
                skipped_status += 1
                continue

            chunks = chunk_document(doc)
            for chunk in chunks:
                f_out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                total_chunks += 1

    temp_chunk_path.replace(chunk_path)
    if corrupted_lines > 0:
        logger.warning(f"Đã bỏ qua {corrupted_lines} dòng hỏng.")

    logger.info(f"Tổng số văn bản đọc: {total_docs}")
    logger.info(f"Đã loại bỏ: {skipped_status} văn bản hết hiệu lực/không còn phù hợp.")
    logger.info(f"Hoàn thành! Tạo ra {total_chunks} chunks hợp lệ.")
    logger.info(f"Lưu tại: {chunk_path}")

if __name__ == "__main__":
    main()
