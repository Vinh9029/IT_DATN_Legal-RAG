"""
Script 06: Pipeline Evol-Instruct HOÀN CHỈNH dùng Gemini 2.5 Flash.

Pipeline tự động end-to-end:
  Documents → Seeds (Gemini) → Evolved Instructions (Gemini) → IRAC Answers (Gemini) → Filter → JSONL

Usage:
    # Chạy toàn bộ pipeline (khuyến nghị)
    python evol_instruct/scripts/06_gemini_pipeline.py --target 500

    # Chỉ chạy evol từ seeds có sẵn
    python evol_instruct/scripts/06_gemini_pipeline.py --skip-seed-gen --target 500

    # Test với 10 samples
    python evol_instruct/scripts/06_gemini_pipeline.py --target 10 --test
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

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
from evol_instruct.src.gemini_client import (
    GeminiClient, GeminiBlockedError, GeminiTruncatedError,
)
from evol_instruct.src.filters import (
    instruction_eliminator, eliminate_evolved, strip_lead_label, PoolDeduplicator,
)
from evol_instruct.src.evol_engine import default_checkpoint_name
from evol_instruct.src.utils import (
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
        checkpoint_file: str = None,
        legal_refs: set[str] = None,
        rate_limit_delay: float = 1.0,
        rounds: int = 1,
        sim_threshold: float = None,
        dedup_pool: bool = True,
        dedup_threshold: float = None,
        strict_truncation: bool = True,
    ):
        self.gemini = gemini
        self.output_path = OUTPUT_DIR / output_file
        # Checkpoint phải gắn với output file, nếu không lần chạy thứ hai với
        # --output-file khác sẽ thấy "đã xử lý hết" và sinh ra file rỗng.
        self.checkpoint = Checkpoint(
            OUTPUT_DIR / (checkpoint_file or default_checkpoint_name(output_file))
        )
        self.legal_refs = legal_refs or set()
        self.technique_keys = list(EVOL_TECHNIQUES.keys())
        self._tech_cycle: list[str] = []
        self.delay = rate_limit_delay  # giây giữa các API calls
        self.rounds = max(1, rounds)
        self.sim_threshold = sim_threshold
        self.strict_truncation = strict_truncation

        self.pool = PoolDeduplicator(dedup_threshold) if dedup_pool else None
        if self.pool is not None and self.output_path.exists():
            self.pool.seed_from(
                [r.get("instruction", "") for r in load_jsonl(self.output_path)]
            )
            logger.info(f"Pool dedup: nạp lại {len(self.pool)} instruction đã có")

        self.stats = {
            "total": 0,
            "accepted": 0,
            "rejected": 0,
            "errors": 0,
            "truncated": 0,
            "saved_answer_calls": 0,
            "rejection_reasons": {},
            "techniques": {},
        }

        logger.info(
            f"GeminiEvolPipeline | output={self.output_path.name} | "
            f"checkpoint={self.checkpoint.filepath.name} "
            f"({self.checkpoint.processed_count} đã xử lý) | rounds={self.rounds} | "
            f"dedup_pool={'on' if self.pool is not None else 'off'}"
        )

    def _next_technique(self) -> str:
        """Round-robin có xáo trộn — random.choice cho phân bố lệch ở cỡ vài trăm."""
        if not self._tech_cycle:
            self._tech_cycle = self.technique_keys[:]
            random.shuffle(self._tech_cycle)
        return self._tech_cycle.pop()

    # ── Bước 1: Evolve Instruction ────────────────────────────────

    def evolve_instruction(self, seed: str, technique_key: str = None) -> tuple[str, str]:
        """
        Tiến hóa seed instruction bằng Gemini (temperature cao).

        Returns:
            (evolved_prompt, technique_key)
        """
        if not technique_key:
            technique_key = self._next_technique()

        tech = EVOL_TECHNIQUES[technique_key]
        user_prompt = tech["prompt"].format(seed_instruction=seed)

        evolved = self.gemini.evolve(
            SYSTEM_EVOL_REWRITER, user_prompt,
            allow_truncated=not self.strict_truncation,
        )
        return strip_lead_label(evolved), technique_key

    # ── Bước 2: Generate IRAC Response ───────────────────────────

    def generate_irac_response(self, evolved_instruction: str) -> str:
        """
        Sinh phản hồi IRAC bằng Gemini (temperature thấp → chính xác).
        """
        system = SYSTEM_IRAC_RESPONDER + "\n\n" + FEW_SHOT_IRAC_EXAMPLE
        response = self.gemini.answer(
            system, evolved_instruction,
            allow_truncated=not self.strict_truncation,
        )
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
            # Bước 1: Evolve (lặp `rounds` vòng theo WizardLM)
            current, techniques = original, []
            for _ in range(self.rounds):
                tk = technique_key if (technique_key and not techniques) else None
                current, used = self.evolve_instruction(current, tk)
                techniques.append(used)
                time.sleep(self.delay)  # Rate limit
            evolved, used_tech = current, techniques[-1]

            self.stats["total"] += 1
            for tk in techniques:
                self.stats["techniques"][tk] = self.stats["techniques"].get(tk, 0) + 1

            if not evolved or len(evolved) < 20:
                logger.debug(f"Evolved quá ngắn, bỏ qua: {evolved[:50]}")
                self.stats["errors"] += 1
                self._checkpoint(seed_id)
                return None

            # Bước 2: LỌC SỚM — rớt ở đây thì khỏi tốn lượt gọi sinh IRAC
            ok, fails = eliminate_evolved(
                original_prompt=original,
                evolved_prompt=evolved,
                sim_threshold=self.sim_threshold,
                pool=self.pool,
            )
            if not ok:
                self.stats["rejected"] += 1
                self.stats["saved_answer_calls"] += 1
                for r in fails:
                    self.stats["rejection_reasons"][r] = (
                        self.stats["rejection_reasons"].get(r, 0) + 1
                    )
                logger.debug(f"❌ Rejected sớm: {fails} | {truncate_text(evolved, 60)}")
                self._checkpoint(seed_id)
                return None

            # Bước 3: IRAC response
            response = self.generate_irac_response(evolved)
            time.sleep(self.delay)

            # Bước 4: Filter đầy đủ
            passed, fails = instruction_eliminator(
                original_prompt=original,
                evolved_prompt=evolved,
                response=response,
                legal_refs=self.legal_refs,
                sim_threshold=self.sim_threshold,
            )

            if passed:
                record = {
                    "instruction": evolved,
                    "input": "",
                    "output": response,
                    "metadata": {
                        "technique": used_tech,
                        "technique_chain": techniques,
                        "evolution_depth": len(techniques),
                        "seed_id": seed_id,
                        "seed_instruction": original,
                        "source_metadata": seed.get("metadata", {}),
                        "generator": "gemini",
                        "model": self.gemini.model,
                        "timestamp": datetime.now().isoformat(),
                    },
                }
                append_jsonl(record, self.output_path)
                if self.pool is not None:
                    self.pool.add(evolved)
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

        except GeminiBlockedError as e:
            # Lỗi NỘI DUNG: chạy lại cũng chặn tiếp → đánh dấu xong, khỏi thử lại.
            logger.warning(f"Seed {seed_id} bị safety chặn: {e}")
            self.stats["errors"] += 1
            self._checkpoint(seed_id)
            return None

        except Exception as e:
            # Lỗi TẠM THỜI (mạng, quota, bị cắt vì max_tokens): KHÔNG checkpoint,
            # để lần chạy sau thử lại. Bản cũ checkpoint ở đây nên một lần rớt
            # mạng là mất seed vĩnh viễn.
            if isinstance(e, GeminiTruncatedError):
                self.stats["truncated"] += 1
            kind = "bị cắt" if isinstance(e, GeminiTruncatedError) else "tạm thời"
            logger.error(f"Lỗi {kind} ở seed {seed_id} (sẽ thử lại lần sau): {e}")
            self.stats["errors"] += 1
            return None

    def _checkpoint(self, seed_id: str):
        self.checkpoint.mark_processed(seed_id)
        self.checkpoint.update_stats("stats", self.stats)
        self.checkpoint.maybe_save(every=10)

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

        try:
            for seed in tqdm(seeds, desc="Gemini Evol-Instruct"):
                # Dừng sớm nếu đủ target
                if target > 0 and self.stats["accepted"] >= target:
                    logger.info(f"Đạt target {target} records, dừng.")
                    break

                self.process_seed(seed)
        finally:
            # Luôn ghi checkpoint, kể cả khi Ctrl-C giữa chừng
            self.checkpoint.save()

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
        logger.info(
            f"   Tiết kiệm {s['saved_answer_calls']} lượt gọi Gemini nhờ lọc sớm"
        )
        if s["truncated"]:
            logger.warning(
                f"   ⚠️  {s['truncated']} item bị cắt vì chạm max_output_tokens. "
                f"Nâng GEMINI_MAX_OUTPUT_TOKENS trong .env, hoặc chạy với "
                f"--allow-truncated nếu chấp nhận câu trả lời cụt."
            )
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

def build_legal_refs(metadatas) -> set[str]:
    """
    Build tập hợp số hiệu luật hợp lệ để check hallucination.

    Nhận iterable metadata thay vì list document: bản cũ gọi
    `load_and_preprocess()` lần thứ hai chỉ để lấy `so_hieu`, tức nạp lại toàn bộ
    2.6 GB `content` vào RAM một cách vô ích.
    """
    refs = set()
    for meta in metadatas:
        meta = meta or {}
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
  python evol_instruct/scripts/06_gemini_pipeline.py --target 500

  # Chỉ evolve từ seeds có sẵn trong data/evol_instruct/seeds/seeds.jsonl
  python evol_instruct/scripts/06_gemini_pipeline.py --skip-seed-gen --target 500

  # Test nhanh với 10 samples
  python evol_instruct/scripts/06_gemini_pipeline.py --target 10 --test
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
    parser.add_argument(
        "--checkpoint-file", default=None,
        help="File checkpoint (mặc định suy ra từ --output-file)"
    )
    parser.add_argument(
        "--rounds", type=int, default=1,
        help="Số vòng tiến hoá liên tiếp theo WizardLM (mặc định: 1)"
    )
    parser.add_argument(
        "--sim-threshold", type=float, default=None,
        help="Ngưỡng similarity seed↔evolved (mặc định lấy từ .env)"
    )
    parser.add_argument(
        "--no-dedup-pool", action="store_true",
        help="Tắt chống trùng lặp trên toàn bộ pool đã accept"
    )
    parser.add_argument(
        "--dedup-threshold", type=float, default=None,
        help="Ngưỡng trùng lặp pool (mặc định: 0.92)"
    )
    parser.add_argument(
        "--allow-truncated", action="store_true",
        help="Chấp nhận cả response bị cắt vì chạm max_output_tokens"
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Seed cho random để chạy lại tái lập được"
    )
    args = parser.parse_args()

    log = setup_logging("06_gemini_pipeline.log")
    ensure_directories()
    validate_config()

    if args.seed is not None:
        random.seed(args.seed)
        log.info(f"random.seed({args.seed}) — kết quả tái lập được")

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

        from evol_instruct.src.data_loader import load_and_preprocess
        from evol_instruct.src.seed_generator import save_seeds
        from evol_instruct.scripts.seed_gen_helpers import generate_seeds_with_gemini as _gen_gemini_seeds

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
        log.info(f"✅ Đã tạo {len(seeds)} seeds → data/evol_instruct/seeds/{args.seeds_file}")
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
        from evol_instruct.src.data_loader import iter_document_metadata
        legal_refs = build_legal_refs(iter_document_metadata())
        log.info(f"Legal refs: {len(legal_refs)} số hiệu")
    except Exception as e:
        log.warning(f"Không build được legal refs ({e}), bỏ qua hallucination check.")

    if not legal_refs:
        log.error(
            "❌ legal_refs RỖNG → bộ lọc hallucination sẽ KHÔNG hoạt động. "
            "Nhiều khả năng preprocessed_cache.jsonl là cache cũ có metadata rỗng; "
            "xoá cache rồi chạy lại 01_download_data.py."
        )

    # ── Bước 4: Chạy Evol pipeline ───────────────────────────────
    pipeline = GeminiEvolPipeline(
        gemini=gemini,
        output_file=args.output_file,
        checkpoint_file=args.checkpoint_file,
        legal_refs=legal_refs,
        rate_limit_delay=args.rate_delay,
        rounds=args.rounds,
        sim_threshold=args.sim_threshold,
        dedup_pool=not args.no_dedup_pool,
        dedup_threshold=args.dedup_threshold,
        strict_truncation=not args.allow_truncated,
    )
    pipeline.run(seeds, target=args.target if not args.test else 0)

    log.info("\n✅ PIPELINE HOÀN TẤT!")


if __name__ == "__main__":
    main()
