"""
Script 03: Chạy Evol-Instruct pipeline chính.

Usage:
    python evol_instruct/scripts/03_run_evolution.py
    python evol_instruct/scripts/03_run_evolution.py --seeds-file seeds.jsonl --batch-size 20
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.settings import ensure_directories, validate_config
from evol_instruct.src.utils import setup_logging, load_jsonl
from evol_instruct.src.llm_client import LLMClient
from evol_instruct.src.evol_engine import EvolPipeline
from evol_instruct.src.seed_generator import load_seeds
from evol_instruct.src.data_loader import load_and_preprocess


def build_legal_references(documents: list[dict]) -> set[str]:
    """Xây dựng tập hợp số hiệu luật hợp lệ từ dataset gốc."""
    refs = set()
    for doc in documents:
        meta = doc.get("metadata", {})
        so_hieu = meta.get("so_hieu", "")
        if so_hieu:
            refs.add(so_hieu)
        loai_vb = meta.get("loai_van_ban", "")
        if so_hieu and loai_vb:
            refs.add(f"{loai_vb} {so_hieu}")
    return refs


def main():
    parser = argparse.ArgumentParser(description="Chạy Evol-Instruct pipeline")
    parser.add_argument("--seeds-file", default="seeds.jsonl", help="File seeds đầu vào")
    parser.add_argument("--output-file", default="legal_evolved.jsonl", help="File output")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size")
    parser.add_argument("--no-hallucination-check", action="store_true",
                        help="Bỏ qua kiểm tra hallucination")
    args = parser.parse_args()

    logger = setup_logging("03_evolution.log")
    ensure_directories()
    validate_config()

    logger.info("=" * 60)
    logger.info("🔄 EVOL-INSTRUCT PIPELINE")
    logger.info("=" * 60)

    # 1. Kiểm tra LM Studio
    llm = LLMClient()
    if not llm.health_check():
        logger.error("❌ LM Studio server không khả dụng!")
        logger.error("   Hãy khởi động LM Studio và bật Local Server tại port 1234")
        sys.exit(1)

    # 2. Load seeds
    seeds = load_seeds(args.seeds_file)
    if not seeds:
        logger.error(f"❌ Không tìm thấy seeds! Chạy evol_instruct/scripts/02_generate_seeds.py trước.")
        sys.exit(1)

    # 3. Build legal references (chống hallucination)
    legal_refs = set()
    if not args.no_hallucination_check:
        logger.info("Loading legal references cho hallucination check...")
        documents = load_and_preprocess(cache=True)
        legal_refs = build_legal_references(documents)
        logger.info(f"Loaded {len(legal_refs)} legal references")

    # 4. Khởi tạo & chạy pipeline
    pipeline = EvolPipeline(
        llm_client=llm,
        output_file=args.output_file,
        legal_references=legal_refs,
    )

    pipeline.run(seeds, batch_size=args.batch_size)

    logger.info("\n✅ PIPELINE HOÀN TẤT!")


if __name__ == "__main__":
    main()
