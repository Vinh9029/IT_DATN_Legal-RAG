"""
Script 03: Chạy Evol-Instruct pipeline chính.

Usage:
    python evol_instruct/scripts/03_run_evolution.py
    python evol_instruct/scripts/03_run_evolution.py --seeds-file seeds.jsonl --batch-size 20
"""

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.settings import ensure_directories, validate_config
from evol_instruct.src.utils import setup_logging, load_jsonl
from evol_instruct.src.llm_client import LLMClient
from evol_instruct.src.evol_engine import EvolPipeline
from evol_instruct.src.seed_generator import load_seeds
from evol_instruct.src.data_loader import iter_document_metadata


def build_legal_references(metadatas) -> set[str]:
    """
    Xây dựng tập hợp số hiệu luật hợp lệ từ dataset gốc.

    Nhận iterable metadata (không phải list document) để không phải nạp cả 2.6 GB
    `content` vào RAM chỉ nhằm lấy vài trường `so_hieu`.
    """
    refs = set()
    for meta in metadatas:
        meta = meta or {}
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
    parser.add_argument("--checkpoint-file", default=None,
                        help="File checkpoint (mặc định suy ra từ --output-file)")
    parser.add_argument("--rounds", type=int, default=1,
                        help="Số vòng tiến hoá liên tiếp theo WizardLM (mặc định 1)")
    parser.add_argument("--target", type=int, default=0,
                        help="Dừng khi đủ N record accepted (0 = chạy hết seeds)")
    parser.add_argument("--sim-threshold", type=float, default=None,
                        help="Ngưỡng similarity seed↔evolved (mặc định lấy từ .env)")
    parser.add_argument("--no-dedup-pool", action="store_true",
                        help="Tắt chống trùng lặp trên toàn bộ pool đã accept")
    parser.add_argument("--dedup-threshold", type=float, default=None,
                        help="Ngưỡng trùng lặp pool (mặc định 0.92)")
    parser.add_argument("--allow-truncated", action="store_true",
                        help="Chấp nhận cả response bị cắt vì chạm max_tokens")
    parser.add_argument("--seed", type=int, default=None,
                        help="Seed cho random để chạy lại tái lập được")
    args = parser.parse_args()

    logger = setup_logging("03_evolution.log")
    ensure_directories()
    validate_config()

    if args.seed is not None:
        random.seed(args.seed)
        logger.info(f"random.seed({args.seed}) — kết quả tái lập được")

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
        legal_refs = build_legal_references(iter_document_metadata())
        logger.info(f"Loaded {len(legal_refs)} legal references")
        if not legal_refs:
            logger.error(
                "❌ legal_refs RỖNG → bộ lọc hallucination sẽ KHÔNG hoạt động. "
                "Nhiều khả năng preprocessed_cache.jsonl là cache cũ có metadata rỗng. "
                "Xoá cache rồi chạy lại 01_download_data.py, hoặc chạy với "
                "--no-hallucination-check nếu cố ý bỏ qua."
            )

    # 4. Khởi tạo & chạy pipeline
    pipeline = EvolPipeline(
        llm_client=llm,
        output_file=args.output_file,
        checkpoint_file=args.checkpoint_file,
        legal_references=legal_refs,
        rounds=args.rounds,
        sim_threshold=args.sim_threshold,
        dedup_pool=not args.no_dedup_pool,
        dedup_threshold=args.dedup_threshold,
        strict_truncation=not args.allow_truncated,
    )

    pipeline.run(seeds, batch_size=args.batch_size, target=args.target)

    logger.info("\n✅ PIPELINE HOÀN TẤT!")


if __name__ == "__main__":
    main()
