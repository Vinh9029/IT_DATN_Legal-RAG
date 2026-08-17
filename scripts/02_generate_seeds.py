"""
Script 02: Tạo seed prompts từ dataset đã tiền xử lý.

Usage:
    python scripts/02_generate_seeds.py
    python scripts/02_generate_seeds.py --mode template --max-seeds 500
    python scripts/02_generate_seeds.py --mode llm --max-seeds 100
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ensure_directories, validate_config
from src.utils import setup_logging
from src.data_loader import load_and_preprocess
from src.seed_generator import (
    generate_seeds_from_templates,
    generate_seeds_with_llm,
    save_seeds,
)
from src.llm_client import LLMClient


def main():
    parser = argparse.ArgumentParser(description="Tạo seed prompts")
    parser.add_argument("--mode", choices=["template", "llm", "both"], default="template",
                        help="Phương thức tạo seeds")
    parser.add_argument("--max-seeds", type=int, default=0, help="Số seeds tối đa")
    parser.add_argument("--seeds-per-doc", type=int, default=2, help="Seeds/doc (mode llm)")
    args = parser.parse_args()

    logger = setup_logging("02_seeds.log")
    ensure_directories()
    validate_config()

    logger.info("=" * 50)
    logger.info(f"🌱 TẠO SEED PROMPTS (mode={args.mode})")
    logger.info("=" * 50)

    # Load documents
    documents = load_and_preprocess(max_items=args.max_seeds)

    all_seeds = []

    # Template-based
    if args.mode in ("template", "both"):
        template_seeds = generate_seeds_from_templates(documents, args.max_seeds)
        all_seeds.extend(template_seeds)
        save_seeds(template_seeds, "seeds_template.jsonl")

    # LLM-based
    if args.mode in ("llm", "both"):
        llm = LLMClient()
        if not llm.health_check():
            logger.error("❌ LM Studio server không khả dụng!")
            logger.error("   Hãy khởi động LM Studio và bật Local Server tại port 1234")
            sys.exit(1)

        llm_seeds = generate_seeds_with_llm(
            documents, llm, args.max_seeds, args.seeds_per_doc
        )
        all_seeds.extend(llm_seeds)
        save_seeds(llm_seeds, "seeds_llm.jsonl")

    # Lưu tổng hợp
    if all_seeds:
        save_seeds(all_seeds, "seeds.jsonl")

    logger.info(f"\n📊 TỔNG KẾT:")
    logger.info(f"   Documents đầu vào: {len(documents)}")
    logger.info(f"   Seeds tạo ra: {len(all_seeds)}")
    logger.info("\n✅ HOÀN TẤT!")


if __name__ == "__main__":
    main()
