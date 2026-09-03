"""
Script 02: Tạo seed prompts từ dataset pháp luật Việt Nam.

Hỗ trợ 3 mode:
- template : Tạo nhanh từ regex/NER + template (không cần API)
- gemini   : Dùng Gemini 2.5 Flash để tạo câu hỏi chất lượng cao [KHUYẾN NGHỊ]
- both     : Kết hợp cả hai (đa dạng nhất)

Usage:
    python evol_instruct/scripts/02_generate_seeds.py --mode gemini --target-seeds 1000
    python evol_instruct/scripts/02_generate_seeds.py --mode template --target-seeds 1000
    python evol_instruct/scripts/02_generate_seeds.py --mode both --target-seeds 1000 --max-docs 400
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.settings import ensure_directories, validate_config, GEMINI_API_KEY
from config.prompts import SYSTEM_SEED_GENERATOR
from evol_instruct.src.utils import setup_logging, save_jsonl, generate_item_id
from evol_instruct.src.data_loader import load_and_preprocess
from evol_instruct.src.seed_generator import (
    generate_seeds_from_templates,
    generate_seeds_with_llm,
    save_seeds,
    load_seeds,
)
from evol_instruct.src.gemini_client import GeminiClient
from evol_instruct.scripts.seed_gen_helpers import generate_seeds_with_gemini, generate_seeds_with_llm_client
from tqdm import tqdm
from loguru import logger


# ── Main ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Tạo seed prompts pháp luật Việt Nam",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dùng Gemini API (khuyến nghị - chất lượng tốt nhất)
  python evol_instruct/scripts/02_generate_seeds.py --mode gemini --target-seeds 1000

  # Dùng template (nhanh, không cần API)
  python evol_instruct/scripts/02_generate_seeds.py --mode template --target-seeds 1000

  # Kết hợp cả hai
  python evol_instruct/scripts/02_generate_seeds.py --mode both --target-seeds 1000
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["template", "gemini", "llm", "both"],
        default="gemini",
        help="Phương thức tạo seeds (mặc định: gemini)",
    )
    parser.add_argument(
        "--target-seeds",
        type=int,
        default=1000,
        help="Số seeds MỤC TIÊU (mặc định: 1000)",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=0,
        help="Số documents tối đa từ dataset (0=tất cả)",
    )
    parser.add_argument(
        "--seeds-per-doc",
        type=int,
        default=3,
        help="Số câu hỏi/document khi dùng Gemini (mặc định: 3)",
    )
    parser.add_argument(
        "--templates-per-doc",
        type=int,
        default=0,
        help="Templates/nội dung khi dùng template mode (0=tự tính)",
    )
    args = parser.parse_args()

    log = setup_logging("02_seeds.log")
    ensure_directories()
    validate_config()

    log.info("=" * 60)
    log.info("🌱 TẠO SEED PROMPTS")
    log.info(f"   Mode: {args.mode}")
    log.info(f"   Target: {args.target_seeds} seeds")
    log.info(f"   Max docs: {args.max_docs or 'tất cả'}")
    log.info("=" * 60)

    # ── Load documents ────────────────────────────────────────────
    documents = load_and_preprocess(max_items=args.max_docs)
    if not documents:
        log.error("❌ Không có documents! Chạy 01_download_data.py trước.")
        sys.exit(1)
    log.info(f"Loaded {len(documents)} documents")

    all_seeds: list[dict] = []

    # ── Template mode ─────────────────────────────────────────────
    if args.mode in ("template", "both"):
        n_target = args.target_seeds if args.mode == "template" else args.target_seeds // 2
        log.info(f"[TEMPLATE] Generating {n_target} seeds...")
        tmpl_seeds = generate_seeds_from_templates(
            documents,
            target_seeds=n_target,
            templates_per_doc=args.templates_per_doc,
        )
        all_seeds.extend(tmpl_seeds)
        save_seeds(tmpl_seeds, "seeds_template.jsonl")
        log.info(f"[TEMPLATE] Done: {len(tmpl_seeds)} seeds")

    # ── Gemini mode ───────────────────────────────────────────────
    if args.mode in ("gemini", "both"):
        if not GEMINI_API_KEY:
            log.error("❌ GEMINI_API_KEY trống! Thêm vào .env")
            sys.exit(1)

        gemini = GeminiClient()
        if not gemini.health_check():
            log.error("❌ Gemini API không khả dụng!")
            sys.exit(1)

        n_target = args.target_seeds if args.mode == "gemini" else args.target_seeds // 2
        log.info(f"[GEMINI] Generating {n_target} seeds...")
        gemini_seeds = generate_seeds_with_gemini(
            documents,
            gemini,
            target_seeds=n_target,
            seeds_per_doc=args.seeds_per_doc,
        )
        all_seeds.extend(gemini_seeds)
        save_seeds(gemini_seeds, "seeds_gemini.jsonl")
        log.info(f"[GEMINI] Done: {len(gemini_seeds)} seeds")

    # ── LLM mode (LM Studio hoặc Rented Proxy API) ────────────────
    if args.mode == "llm":
        from evol_instruct.src.llm_client import LLMClient
        llm = LLMClient()
        if not llm.health_check():
            log.error("❌ LLM API không khả dụng!")
            sys.exit(1)

        log.info(f"[LLM] Generating {args.target_seeds} seeds...")
        llm_seeds = generate_seeds_with_llm_client(
            documents,
            llm,
            target_seeds=args.target_seeds,
            seeds_per_doc=args.seeds_per_doc,
        )
        all_seeds.extend(llm_seeds)
        save_seeds(llm_seeds, "seeds_llm.jsonl")
        log.info(f"[LLM] Done: {len(llm_seeds)} seeds")

    # ── Lưu tổng hợp ─────────────────────────────────────────────
    if all_seeds:
        # Dedup cuối cùng (mode both có thể bị trùng)
        seen_final = set()
        unique_seeds = []
        for s in all_seeds:
            norm = s["instruction"].strip().lower()
            if norm not in seen_final:
                seen_final.add(norm)
                unique_seeds.append(s)
        all_seeds = unique_seeds

        save_seeds(all_seeds, "seeds.jsonl")

    log.info("\n" + "=" * 60)
    log.info("📊 TỔNG KẾT:")
    log.info(f"   Documents đầu vào: {len(documents)}")
    log.info(f"   Tổng seeds tạo ra: {len(all_seeds)}")

    if len(all_seeds) >= 700:
        log.info("   ✅ Đạt ngưỡng 700+ seeds!")
    else:
        needed = 700 - len(all_seeds)
        log.warning(f"   ⚠️  Chưa đủ 700. Cần thêm {needed} seeds.")
        log.info("   Thử: --max-docs lớn hơn hoặc --seeds-per-doc 4")

    log.info(f"   Output: data/evol_instruct/seeds/seeds.jsonl")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
