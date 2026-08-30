import sys
from pathlib import Path

# Thêm backend vào sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from config.settings import ensure_directories
from src.data_loader import load_and_preprocess, get_unique_categories
from loguru import logger

def main():
    ensure_directories()
    
    logger.info("=== BẮT ĐẦU FIX PREPROCESS & CACHE ===")
    
    # max_items=0 -> load tất cả
    documents = load_and_preprocess(max_items=0, cache=True)
    
    logger.info(f"Đã tiền xử lý xong {len(documents)} văn bản.")
    
    # In ra một số thông kê để kiểm tra
    categories = get_unique_categories(documents)
    
    # Kiểm tra metadata completeness
    missing_so_hieu = sum(1 for doc in documents if not doc.get("metadata", {}).get("so_hieu"))
    logger.info(f"Số lượng văn bản thiếu số hiệu: {missing_so_hieu} / {len(documents)}")

if __name__ == "__main__":
    main()
