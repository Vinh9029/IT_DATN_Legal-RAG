"""
Script 06: Pipeline Evol-Instruct HOÀN CHỈNH dùng Gemini 2.5 Flash.

Pipeline tự động end-to-end:
  Documents → Seeds (Gemini) → Evolved Instructions (Gemini) → IRAC Answers (Gemini) → Filter → JSONL

Usage:
    # Chạy toàn bộ pipeline (khuyến nghị)
    python scripts/06_gemini_pipeline.py --target 500

    # Chỉ chạy evol từ seeds có sẵn
    python scripts/06_gemini_pipeline.py --skip-seed-gen --target 500

    # Test với 10 samples
    python scripts/06_gemini_pipeline.py --target 10 --test
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from tqdm import tqdm

from config.settings import (
    ensure_directories, validate_config,
    GEMINI_API_KEY, OUTPUT_DIR, SEEDS_DIR,
)
from config.prompts import (
    EVOL_TECHNIQUES, SYSTEM_EVOL_REWRITER,
    SYSTEM_IRAC_RESPONDER, FEW_SHOT_IRAC_EXAMPLE,
)
from src.gemini_client import GeminiClient
from src.filters import instruction_eliminator
from src.utils import (
    setup_logging, load_jsonl, append_jsonl,
    Checkpoint, generate_item_id, truncate_text,
)


# ── Gemini Evol-Instruct Core ─────────────────────────────────────

class GeminiEvolPipeline:
    """
    Pipeline Evol-Instruct sử dụng Gemini 2.5 Flash.

    Bước 1: Evolve seed → câu hỏi pháp lý phức tạp hơn
    Bước 2: Generate IRAC response
    Bước 3: Filter chất lượng
    Bước 4: Lưu Alpaca JSONL
    """

    def __init__(
        self,
        gemini: GeminiClient,
        output_file: str = "legal_evolved.jsonl",
        checkpoint_file: str = "gemini_checkpoint.json",
        legal_refs: set[str] = None,
        rate_limit_delay: float = 1.0,
    ):
        self.gemini = gemini
        self.output_path = OUTPUT_DIR / output_file
        self.checkpoint = Checkpoint(OUTPUT_DIR / checkpoint_file)
        self.legal_refs = legal_refs or set()
        self.technique_keys = list(EVOL_TECHNIQUES.keys())
        self.delay = rate_limit_delay  # giây giữa các API calls

        self.stats = {
            "total": 0,
            "accepted": 0,
            "rejected": 0,
            "errors": 0,
            "rejection_reasons": {},
            "techniques": {},
        }

        logger.info(
            f"GeminiEvolPipeline | output={self.output_path.name} | "
            f"checkpoint={self.checkpoint.processed_count} đã xử lý"
        )

    # ── Bước 1: Evolve Instruction ────────────────────────────────

    def evolve_instruction(self, seed: str, technique_key: str = None) -> tuple[str, str]:
        """
        Tiến hóa seed instruction bằng Gemini (temperature cao).

        Returns:
            (evolved_prompt, technique_key)
        """
        if not technique_key:
            technique_key = random.choice(self.technique_keys)

        tech = EVOL_TECHNIQUES[technique_key]
        user_prompt = tech["prompt"].format(seed_instruction=seed)

        evolved = self.gemini.evolve(SYSTEM_EVOL_REWRITER, user_prompt)
        return evolved.strip(), technique_key

    # ── Bước 2: Generate IRAC Response ───────────────────────────

    def generate_irac_response(self, evolved_instruction: str) -> str:
        """
        Sinh phản hồi IRAC bằng Gemini (temperature thấp → chính xác).
        """
        system = SYSTEM_IRAC_RESPONDER + "\n\n" + FEW_SHOT_IRAC_EXAMPLE
        response = self.gemini.answer(system, evolved_instruction)
        return response.strip()

    # ── Xử lý 1 seed ─────────────────────────────────────────────

    def process_seed(self, seed: dict, technique_key: str = None) -> dict | None:
        """
        Xử lý 1 seed: evolve → IRAC → filter → save.

        Returns:
            Record dict nếu accepted, None nếu rejected/error.
        """
        seed_id = seed.get("id", generate_item_id(seed["instruction"]))

        # Bỏ qua đã xử lý
        if self.checkpoint.is_processed(seed_id):
            return None

        original = seed["instruction"]

        try:
            # Bước 1: Evolve
            evolved, used_tech = self.evolve_instruction(original, technique_key)
            time.sleep(self.delay)  # Rate limit

            if not evolved or len(evolved) < 20:
                logger.debug(f"Evolved quá ngắn, bỏ qua: {evolved[:50]}")
                self.stats["errors"] += 1
                self._checkpoint(seed_id)
                return None

            # Bước 2: IRAC response
            response = self.generate_irac_response(evolved)
            time.sleep(self.delay)

            # Bước 3: Filter
            passed, fails = instruction_eliminator(
                original_prompt=original,
                evolved_prompt=evolved,
                response=response,
                legal_refs=self.legal_refs,
            )

            self.stats["total"] += 1
            self.stats["techniques"][used_tech] = self.stats["techniques"].get(used_tech, 0) + 1

            if passed:
                record = {
                    "instruction": evolved,
                    "input": "",
                    "output": response,
                    "metadata": {
                        "technique": used_tech,
                        "seed_id": seed_id,
                        "seed_instruction": original,
                        "source_metadata": seed.get("metadata", {}),
                        "generator": "gemini",
                        "model": self.gemini.model,
                        "timestamp": datetime.now().isoformat(),
                    },
                }
                append_jsonl(record, self.output_path)
                self.stats["accepted"] += 1
                logger.info(
                    f"✅ [{used_tech[:15]:15s}] {truncate_text(evolved, 70)}"
                )
            else:
                self.stats["rejected"] += 1
                for r in fails:
                    self.stats["rejection_reasons"][r] = (
                        self.stats["rejection_reasons"].get(r, 0) + 1
                    )
                logger.debug(f"❌ Rejected: {fails} | {truncate_text(evolved, 60)}")
                record = None

            self._checkpoint(seed_id)
            return record

        except Exception as e:
            logger.error(f"Error seed {seed_id}: {e}")
            self.stats["errors"] += 1
            self._checkpoint(seed_id)
            return None

    def _checkpoint(self, seed_id: str):
        self.checkpoint.mark_processed(seed_id)
        self.checkpoint.update_stats("stats", self.stats)
        self.checkpoint.save()

    # ── Run full pipeline ─────────────────────────────────────────

    def run(self, seeds: list[dict], target: int = 0):
        """
        Chạy pipeline trên toàn bộ seeds.

        Args:
            seeds: Danh sách seed dicts.
            target: Dừng khi đủ số records accepted (0 = xử lý tất cả).
        """
        total = len(seeds)
        logger.info("=" * 60)
        logger.info("🚀 GEMINI EVOL-INSTRUCT PIPELINE BẮT ĐẦU")
        logger.info(f"   Seeds: {total} | Target accepted: {target or 'tất cả'}")
        logger.info(f"   Đã checkpoint: {self.checkpoint.processed_count}")
        logger.info(f"   Output: {self.output_path}")
        logger.info("=" * 60)

        for seed in tqdm(seeds, desc="Gemini Evol-Instruct"):
            # Dừng sớm nếu đủ target
            if target > 0 and self.stats["accepted"] >= target:
                logger.info(f"Đạt target {target} records, dừng.")
                break

            self.process_seed(seed)

        self._log_summary(total)

    def _log_summary(self, total: int):
        s = self.stats
        rate = s["accepted"] / max(s["total"], 1) * 100
        logger.info("\n" + "=" * 60)
        logger.info("🏁 PIPELINE HOÀN TẤT")
        logger.info(f"   Total seeds: {total}")
        logger.info(f"   Processed: {s['total']} | Errors: {s['errors']}")
        logger.info(f"   Accepted: {s['accepted']} ({rate:.1f}%)")
        logger.info(f"   Rejected: {s['rejected']}")
        if s["rejection_reasons"]:
            for reason, cnt in sorted(s["rejection_reasons"].items(), key=lambda x: -x[1]):
                logger.info(f"     - {reason}: {cnt}")
        if s["techniques"]:
            logger.info("   Techniques:")
            for tech, cnt in sorted(s["techniques"].items(), key=lambda x: -x[1]):
                logger.info(f"     - {tech}: {cnt}")
        logger.info(f"   Output: {self.output_path}")
        logger.info("=" * 60)


# ── Main ──────────────────────────────────────────────────────────

def build_legal_refs(documents: list[dict]) -> set[str]:
    """Build tập hợp số hiệu luật hợp lệ để check hallucination."""
    refs = set()
    for doc in documents:
        meta = doc.get("metadata", {})
        so = meta.get("so_hieu", "")
        loai = meta.get("loai_van_ban", "")
        if so:
            refs.add(so)
        if so and loai:
            refs.add(f"{loai} {so}")
    return refs


def main():
    parser = argparse.ArgumentParser(
        description="Gemini Evol-Instruct pipeline cho pháp luật Việt Nam",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Pipeline đầy đủ: tạo seeds + evolve (target 500 records)
  python scripts/06_gemini_pipeline.py --target 500

  # Chỉ evolve từ seeds có sẵn trong data/seeds/seeds.jsonl
  python scripts/06_gemini_pipeline.py --skip-seed-gen --target 500

  # Test nhanh với 10 samples
  python scripts/06_gemini_pipeline.py --target 10 --test
        """,
    )
    parser.add_argument(
        "--target", type=int, default=500,
        help="Số records accepted mục tiêu (mặc định: 500)"
    )
    parser.add_argument(
        "--seeds-file", default="seeds.jsonl",
        help="File seeds đầu vào (mặc định: seeds.jsonl)"
    )
    parser.add_argument(
        "--output-file", default="legal_evolved.jsonl",
        help="File output (mặc định: legal_evolved.jsonl)"
    )
    parser.add_argument(
        "--skip-seed-gen", action="store_true",
        help="Bỏ qua tạo seeds, dùng file seeds có sẵn"
    )
    parser.add_argument(
        "--seed-target", type=int, default=1000,
        help="Số seeds cần tạo (nếu không skip-seed-gen, mặc định: 1000)"
    )
    parser.add_argument(
        "--max-docs", type=int, default=0,
        help="Số documents tối đa từ dataset"
    )
    parser.add_argument(
        "--rate-delay", type=float, default=1.0,
        help="Giây đợi giữa các API calls (mặc định: 1.0)"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Test mode: chỉ xử lý tối đa 10 seeds"
    )
    args = parser.parse_args()

    log = setup_logging("06_gemini_pipeline.log")
    ensure_directories()
    validate_config()

    if not GEMINI_API_KEY:
        log.error("❌ GEMINI_API_KEY trống! Thêm vào .env")
        sys.exit(1)

    # ── Khởi tạo Gemini ───────────────────────────────────────────
    log.info("Kiểm tra Gemini API...")
    gemini = GeminiClient()
    if not gemini.health_check():
        log.error("❌ Gemini API không khả dụng!")
        sys.exit(1)

    # ── Bước 1: Tạo seeds (nếu cần) ──────────────────────────────
    if not args.skip_seed_gen:
        log.info(f"\n📌 BƯỚC 1: TẠO SEEDS (target={args.seed_target})")

        from src.data_loader import load_and_preprocess
        from src.seed_generator import save_seeds
        from scripts.seed_gen_helpers import generate_seeds_with_gemini as _gen_gemini_seeds

        documents = load_and_preprocess(max_items=args.max_docs)
        if not documents:
            log.error("❌ Không có documents! Chạy 01_download_data.py trước.")
            sys.exit(1)

        seeds = _gen_gemini_seeds(
            documents, gemini,
            target_seeds=args.seed_target,
            seeds_per_doc=3,
        )
        save_seeds(seeds, args.seeds_file)
        log.info(f"✅ Đã tạo {len(seeds)} seeds → data/seeds/{args.seeds_file}")
    else:
        log.info("⏭️  Bỏ qua seed generation, dùng file có sẵn.")

    # ── Bước 2: Load seeds ────────────────────────────────────────
    seeds_path = SEEDS_DIR / args.seeds_file
    if not seeds_path.exists():
        log.error(f"❌ File seeds không tồn tại: {seeds_path}")
        log.error("   Chạy không có --skip-seed-gen, hoặc chạy 02_generate_seeds.py trước.")
        sys.exit(1)

    seeds = load_jsonl(seeds_path)
    if not seeds:
        log.error(f"❌ File seeds rỗng: {seeds_path}")
        sys.exit(1)

    log.info(f"\n📌 BƯỚC 2: EVOL-INSTRUCT (seeds={len(seeds)})")

    # Test mode
    if args.test:
        seeds = seeds[:10]
        log.info(f"🧪 Test mode: chỉ xử lý {len(seeds)} seeds")

    # ── Bước 3: Xây dựng legal references ────────────────────────
    legal_refs = set()
    try:
        from src.data_loader import load_and_preprocess
        docs = load_and_preprocess(cache=True)
        legal_refs = build_legal_refs(docs)
        log.info(f"Legal refs: {len(legal_refs)} số hiệu")
    except Exception:
        log.warning("Không build được legal refs, bỏ qua hallucination check.")

    # ── Bước 4: Chạy Evol pipeline ───────────────────────────────
    pipeline = GeminiEvolPipeline(
        gemini=gemini,
        output_file=args.output_file,
        legal_refs=legal_refs,
        rate_limit_delay=args.rate_delay,
    )
    pipeline.run(seeds, target=args.target if not args.test else 0)

    log.info("\n✅ PIPELINE HOÀN TẤT!")


if __name__ == "__main__":
    main()
