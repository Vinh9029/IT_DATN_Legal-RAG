"""
Script 01: Tải và tiền xử lý dataset pháp luật Việt Nam từ HuggingFace.

Usage:
    python scripts/01_download_data.py
    python scripts/01_download_data.py --max-items 100
"""

import argparse
import sys
from pathlib import Path

# Thêm project root vào sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ensure_directories, validate_config
from evol_instruct.src.utils import setup_logging
from evol_instruct.src.data_loader import load_and_preprocess, get_unique_categories


def main():
    parser = argparse.ArgumentParser(description="Tải dataset pháp luật Việt Nam")
    parser.add_argument("--max-items", type=int, default=0, help="Số items tối đa (0=tất cả)")
    parser.add_argument("--min-length", type=int, default=200, help="Độ dài content tối thiểu")
    parser.add_argument("--no-cache", action="store_true", help="Bỏ qua cache, tải lại")
    args = parser.parse_args()

    # Setup
    logger = setup_logging("01_download.log")
    ensure_directories()
    validate_config()

    logger.info("=" * 50)
    logger.info("📦 BẮT ĐẦU TẢI DATASET")
    logger.info("=" * 50)

    # Load & preprocess
    documents = load_and_preprocess(
        max_items=args.max_items,
        min_content_length=args.min_length,
        cache=not args.no_cache,
    )

    # Thống kê
    categories = get_unique_categories(documents)

    logger.info(f"\n📊 THỐNG KÊ:")
    logger.info(f"   Tổng documents: {len(documents)}")
    logger.info(f"   Ngành: {len(categories['nganh'])} loại")
    logger.info(f"   Lĩnh vực: {len(categories['linh_vuc'])} loại")
    logger.info(f"   Loại VB: {len(categories['loai_van_ban'])} loại")
    logger.info(f"   Cơ quan: {len(categories['co_quan_ban_hanh'])} cơ quan")

    # Hiển thị mẫu
    if documents:
        sample = documents[0]
        logger.info(f"\n📄 MẪU DOCUMENT:")
        logger.info(f"   Content (100 chars): {sample['content'][:100]}...")
        logger.info(f"   Metadata: {sample['metadata']}")

    logger.info("\n✅ HOÀN TẤT!")


if __name__ == "__main__":
    main()
