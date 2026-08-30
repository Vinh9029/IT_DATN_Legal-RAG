"""
Script 02: Tạo seed prompts từ dataset đã tiền xử lý.

Usage:
    python scripts/02_generate_seeds.py
    python scripts/02_generate_seeds.py --mode template --target-seeds 1000
    python scripts/02_generate_seeds.py --mode llm --max-docs 200 --seeds-per-doc 3
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ensure_directories, validate_config
from evol_instruct.src.utils import setup_logging
from evol_instruct.src.data_loader import load_and_preprocess
from evol_instruct.src.seed_generator import (
    generate_seeds_from_templates,
    generate_seeds_with_llm,
    save_seeds,
)
from evol_instruct.src.llm_client import LLMClient


def main():
    parser = argparse.ArgumentParser(description="Tạo seed prompts")
    parser.add_argument("--mode", choices=["template", "llm", "both"], default="template",
                        help="Phương thức tạo seeds")
    parser.add_argument("--target-seeds", type=int, default=1000,
                        help="Số seeds MỤC TIÊU cần tạo (mode template, mặc định 1000)")
    parser.add_argument("--max-docs", type=int, default=0,
                        help="Số documents tối đa để load từ dataset (0=tất cả)")
    parser.add_argument("--seeds-per-doc", type=int, default=3,
                        help="Số seeds/document (mode llm)")
    parser.add_argument("--templates-per-doc", type=int, default=0,
                        help="Số templates áp dụng cho mỗi nội dung (mode template, 0=tự tính)")
    args = parser.parse_args()

    logger = setup_logging("02_seeds.log")
    ensure_directories()
    validate_config()

    logger.info("=" * 60)
    logger.info(f"🌱 TẠO SEED PROMPTS")
    logger.info(f"   Mode: {args.mode}")
    logger.info(f"   Target seeds: {args.target_seeds}")
    logger.info(f"   Max docs: {args.max_docs or 'tất cả'}")
    logger.info("=" * 60)

    # Load documents (load TẤT CẢ hoặc theo max_docs)
    documents = load_and_preprocess(max_items=args.max_docs)

    if not documents:
        logger.error("❌ Không có documents! Chạy scripts/01_download_data.py trước.")
        sys.exit(1)

    all_seeds = []

    # ── Template-based ────────────────────────────────────────────
    if args.mode in ("template", "both"):
        template_seeds = generate_seeds_from_templates(
            documents,
            target_seeds=args.target_seeds,
            templates_per_doc=args.templates_per_doc,
        )
        all_seeds.extend(template_seeds)
        save_seeds(template_seeds, "seeds_template.jsonl")

    # ── LLM-based ─────────────────────────────────────────────────
    if args.mode in ("llm", "both"):
        llm = LLMClient()
        if not llm.health_check():
            logger.error("❌ LM Studio server không khả dụng!")
            logger.error("   Hãy khởi động LM Studio và bật Local Server tại port 1234")
            sys.exit(1)

        llm_seeds = generate_seeds_with_llm(
            documents, llm,
            max_docs=args.max_docs or len(documents),
            seeds_per_doc=args.seeds_per_doc,
        )
        all_seeds.extend(llm_seeds)
        save_seeds(llm_seeds, "seeds_llm.jsonl")

    # ── Lưu tổng hợp ─────────────────────────────────────────────
    if all_seeds:
        save_seeds(all_seeds, "seeds.jsonl")

    logger.info(f"\n{'=' * 60}")
    logger.info(f"📊 TỔNG KẾT:")
    logger.info(f"   Documents đầu vào: {len(documents)}")
    logger.info(f"   Seeds tạo ra: {len(all_seeds)}")
    if len(all_seeds) >= 700:
        logger.info(f"   ✅ Đạt ngưỡng 700+ seeds!")
    else:
        logger.info(f"   ⚠️ Chưa đạt 700 seeds. Thử tăng --max-docs hoặc --templates-per-doc")
    logger.info(f"   Output: data/seeds/seeds.jsonl")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
