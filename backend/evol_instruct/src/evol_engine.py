"""
Evol-Instruct Engine - Core pipeline tiến hóa câu hỏi pháp lý.

Quy trình:
1. Chọn kỹ thuật tiến hóa theo vòng tròn (6 techniques, phân bố đều)
2. Gọi LLM để rewrite seed → evolved instruction (lặp `rounds` vòng)
3. Lọc SỚM trên evolved prompt (tiết kiệm lượt gọi sinh câu trả lời)
4. Gọi LLM để sinh IRAC response (temp thấp)
5. Chạy Instruction Eliminator filters
6. Lưu kết quả Alpaca JSONL format
"""

import random
from pathlib import Path
from datetime import datetime

from loguru import logger
from tqdm import tqdm

from config.settings import (
    EVOL_TEMPERATURE,
    ANSWER_TEMPERATURE,
    OUTPUT_DIR,
    BATCH_SIZE,
)
from config.prompts import (
    SYSTEM_EVOL_REWRITER,
    SYSTEM_IRAC_RESPONDER,
    EVOL_TECHNIQUES,
    FEW_SHOT_IRAC_EXAMPLE,
)
from evol_instruct.src.llm_client import LLMClient, TruncatedResponseError
from evol_instruct.src.filters import (
    instruction_eliminator,
    eliminate_evolved,
    strip_lead_label,
    PoolDeduplicator,
)
from evol_instruct.src.utils import (
    append_jsonl,
    load_jsonl,
    Checkpoint,
    generate_item_id,
    truncate_text,
)


def default_checkpoint_name(output_file: str) -> str:
    """
    Checkpoint phải gắn với output file.

    Nếu dùng chung một tên checkpoint cho mọi output, lần chạy thứ hai với
    --output-file khác sẽ thấy "mọi seed đã xử lý" và sinh ra file RỖNG mà vẫn
    báo hoàn tất.
    """
    return f"{Path(output_file).stem}_checkpoint.json"


class EvolPipeline:
    """
    Core Evol-Instruct pipeline.

    Tiến hóa seed instructions thành các bài toán pháp lý phức tạp
    theo cấu trúc IRAC, sử dụng 6 kỹ thuật nâng cao.
    """

    def __init__(
        self,
        llm_client: LLMClient = None,
        output_file: str = "legal_evolved.jsonl",
        checkpoint_file: str = None,
        legal_references: set[str] = None,
        rounds: int = 1,
        sim_threshold: float = None,
        dedup_pool: bool = True,
        dedup_threshold: float = None,
        strict_truncation: bool = True,
    ):
        self.llm = llm_client or LLMClient()
        self.output_path = OUTPUT_DIR / output_file
        self.checkpoint = Checkpoint(
            OUTPUT_DIR / (checkpoint_file or default_checkpoint_name(output_file))
        )
        self.legal_references = legal_references or set()
        self.rounds = max(1, rounds)
        self.sim_threshold = sim_threshold
        self.strict_truncation = strict_truncation

        # Danh sách technique keys
        self.technique_keys = list(EVOL_TECHNIQUES.keys())
        self._tech_cycle: list[str] = []

        # Pool chống trùng lặp toàn cục; nạp lại từ output cũ khi resume.
        self.pool = PoolDeduplicator(dedup_threshold) if dedup_pool else None
        if self.pool is not None and self.output_path.exists():
            existing = [r.get("instruction", "") for r in load_jsonl(self.output_path)]
            self.pool.seed_from(existing)
            logger.info(f"Pool dedup: nạp lại {len(self.pool)} instruction đã có")

        # Thống kê
        self.stats = {
            "total_processed": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "total_errors": 0,
            "total_truncated": 0,
            "saved_answer_calls": 0,
            "rejection_reasons": {},
            "techniques_used": {},
        }

        logger.info(
            f"EvolPipeline initialized | "
            f"output={self.output_path} | checkpoint={self.checkpoint.filepath.name} | "
            f"techniques={len(self.technique_keys)} | rounds={self.rounds} | "
            f"legal_refs={len(self.legal_references)} | "
            f"dedup_pool={'on' if self.pool is not None else 'off'}"
        )

    # ── Chọn technique ────────────────────────────────────────────

    def _next_technique(self) -> str:
        """
        Round-robin có xáo trộn trong mỗi chu kỳ.

        `random.choice` cho phân bố lệch đáng kể ở cỡ mẫu vài trăm, làm bảng
        "techniques distribution" của script 04 khó biện luận.
        """
        if not self._tech_cycle:
            self._tech_cycle = self.technique_keys[:]
            random.shuffle(self._tech_cycle)
        return self._tech_cycle.pop()

    # ── Bước 1: Evolve ────────────────────────────────────────────

    def evolve_instruction(self, seed_instruction: str, technique_key: str = None) -> str:
        """
        Bước 1: Tiến hóa instruction bằng kỹ thuật được chọn.

        Args:
            seed_instruction: Câu hỏi gốc (seed).
            technique_key: Key của kỹ thuật (None = round-robin).

        Returns:
            Evolved instruction string.
        """
        if not technique_key:
            technique_key = self._next_technique()

        technique = EVOL_TECHNIQUES[technique_key]
        user_prompt = technique["prompt"].format(seed_instruction=seed_instruction)

        messages = [
            {"role": "system", "content": SYSTEM_EVOL_REWRITER},
            {"role": "user", "content": user_prompt},
        ]

        evolved = self.llm.chat(
            messages=messages,
            temperature=EVOL_TEMPERATURE,
            allow_truncated=not self.strict_truncation,
        )

        logger.debug(
            f"Evolved [{technique['name']}]: "
            f"{truncate_text(evolved, 150)}"
        )

        return evolved

    # ── Bước 2: IRAC ──────────────────────────────────────────────

    def generate_irac_response(self, evolved_instruction: str) -> str:
        """
        Bước 2: Sinh phản hồi chuẩn IRAC (temperature thấp).

        Args:
            evolved_instruction: Câu hỏi đã tiến hóa.

        Returns:
            IRAC response string.
        """
        system_with_example = (
            SYSTEM_IRAC_RESPONDER + "\n\n" + FEW_SHOT_IRAC_EXAMPLE
        )

        messages = [
            {"role": "system", "content": system_with_example},
            {"role": "user", "content": evolved_instruction},
        ]

        response = self.llm.chat(
            messages=messages,
            temperature=ANSWER_TEMPERATURE,
            allow_truncated=not self.strict_truncation,
        )

        logger.debug(f"IRAC response: {truncate_text(response, 150)}")
        return response

    # ── Xử lý 1 seed ──────────────────────────────────────────────

    def process_single(self, seed: dict, technique_key: str = None) -> dict | None:
        """
        Xử lý một seed: evolve → lọc sớm → respond → filter → save.

        Returns:
            Record dict nếu accepted, None nếu rejected.
        """
        seed_instruction = seed["instruction"]
        item_id = seed.get("id", generate_item_id(seed_instruction))

        # Kiểm tra checkpoint
        if self.checkpoint.is_processed(item_id):
            logger.debug(f"Skipped (checkpoint): {item_id}")
            return None

        try:
            # Bước 1: Evolve (lặp `rounds` vòng theo WizardLM)
            current = seed_instruction
            techniques = []
            for _ in range(self.rounds):
                tk = technique_key if (technique_key and not techniques) else self._next_technique()
                current = strip_lead_label(self.evolve_instruction(current, tk))
                techniques.append(tk)
            evolved = current
            used_technique = techniques[-1]

            self.stats["total_processed"] += 1
            for tk in techniques:
                self.stats["techniques_used"][tk] = (
                    self.stats["techniques_used"].get(tk, 0) + 1
                )

            # Bước 2: LỌC SỚM — rớt ở đây thì khỏi tốn lượt sinh IRAC
            ok, failed = eliminate_evolved(
                original_prompt=seed_instruction,
                evolved_prompt=evolved,
                sim_threshold=self.sim_threshold,
                pool=self.pool,
            )
            if not ok:
                self.stats["total_rejected"] += 1
                self.stats["saved_answer_calls"] += 1
                for reason in failed:
                    self.stats["rejection_reasons"][reason] = (
                        self.stats["rejection_reasons"].get(reason, 0) + 1
                    )
                logger.info(f"❌ REJECTED sớm [{used_technique}] → {failed}")
                self._finish(item_id)
                return None

            # Bước 3: Generate IRAC response
            response = self.generate_irac_response(evolved)

            # Bước 4: Filter đầy đủ
            passed, failed = instruction_eliminator(
                original_prompt=seed_instruction,
                evolved_prompt=evolved,
                response=response,
                legal_refs=self.legal_references,
                sim_threshold=self.sim_threshold,
            )

            if passed:
                # Bước 5: Lưu (Alpaca JSONL format)
                record = {
                    "instruction": evolved,
                    "input": "",
                    "output": response,
                    "metadata": {
                        "technique": used_technique,
                        "technique_chain": techniques,
                        "evolution_depth": len(techniques),
                        "seed_id": item_id,
                        "seed_instruction": seed_instruction,
                        "timestamp": datetime.now().isoformat(),
                        "source_metadata": seed.get("metadata", {}),
                    },
                }
                append_jsonl(record, self.output_path)
                if self.pool is not None:
                    self.pool.add(evolved)
                self.stats["total_accepted"] += 1
                logger.info(f"✅ ACCEPTED [{used_technique}] → {item_id}")
            else:
                self.stats["total_rejected"] += 1
                for reason in failed:
                    self.stats["rejection_reasons"][reason] = (
                        self.stats["rejection_reasons"].get(reason, 0) + 1
                    )
                logger.info(f"❌ REJECTED [{used_technique}] → {failed}")
                record = None

            self._finish(item_id)
            return record

        except TruncatedResponseError as e:
            # Không checkpoint: nâng MAX_TOKENS rồi chạy lại là cứu được item này.
            self.stats["total_errors"] += 1
            self.stats["total_truncated"] += 1
            logger.error(f"Bị cắt ở {item_id} (sẽ thử lại lần sau): {e}")
            return None

        except Exception as e:
            # KHÔNG checkpoint: lỗi tạm thời (mạng) phải được thử lại ở lần chạy
            # sau thay vì đốt luôn seed.
            self.stats["total_errors"] += 1
            logger.error(f"Error processing {item_id}: {e}")
            return None

    def _finish(self, item_id: str):
        self.checkpoint.mark_processed(item_id)
        self.checkpoint.update_stats("pipeline_stats", self.stats)
        self.checkpoint.maybe_save(every=10)

    # ── Vòng chạy chính ───────────────────────────────────────────

    def run(self, seeds: list[dict], batch_size: int = None, target: int = 0):
        """
        Chạy pipeline trên toàn bộ danh sách seeds.

        Args:
            seeds: Danh sách seed dicts.
            batch_size: Kích thước batch (logging checkpoint mỗi batch).
            target: Dừng khi đủ số record accepted (0 = chạy hết).
        """
        batch_size = batch_size or BATCH_SIZE
        total = len(seeds)
        skipped = 0
        done = 0

        logger.info(f"{'='*60}")
        logger.info(f"🚀 BẮT ĐẦU EVOL-INSTRUCT PIPELINE")
        logger.info(f"   Seeds: {total} | Batch: {batch_size} | Rounds: {self.rounds}")
        logger.info(f"   Already processed: {self.checkpoint.processed_count}")
        logger.info(f"   Output: {self.output_path}")
        logger.info(f"{'='*60}")

        try:
            for seed in tqdm(seeds, desc="Evol-Instruct"):
                if target > 0 and self.stats["total_accepted"] >= target:
                    logger.info(f"Đạt target {target} records, dừng.")
                    break

                item_id = seed.get("id", generate_item_id(seed["instruction"]))
                if self.checkpoint.is_processed(item_id):
                    skipped += 1
                    continue

                self.process_single(seed)
                done += 1

                # Log batch summary theo số item THỰC SỰ xử lý, không tính seed bỏ qua
                if done % batch_size == 0:
                    self._log_progress(done, total, skipped)
        finally:
            # Luôn ghi checkpoint, kể cả khi Ctrl-C
            self.checkpoint.save()

        self._log_summary(total, skipped)

    def _log_progress(self, current: int, total: int, skipped: int):
        """Log tiến trình mỗi batch."""
        rate = (
            self.stats["total_accepted"] / max(self.stats["total_processed"], 1)
            * 100
        )
        logger.info(
            f"📊 Progress: {current}/{total} | "
            f"Accepted: {self.stats['total_accepted']} | "
            f"Rejected: {self.stats['total_rejected']} | "
            f"Errors: {self.stats['total_errors']} | "
            f"Skipped: {skipped} | "
            f"Rate: {rate:.1f}%"
        )

    def _log_summary(self, total: int, skipped: int):
        """Log tổng kết cuối pipeline."""
        logger.info(f"\n{'='*60}")
        logger.info(f"🏁 EVOL-INSTRUCT PIPELINE HOÀN TẤT")
        logger.info(f"   Total seeds: {total}")
        logger.info(f"   Skipped (checkpoint): {skipped}")
        logger.info(f"   Processed: {self.stats['total_processed']}")
        logger.info(f"   Accepted: {self.stats['total_accepted']}")
        logger.info(f"   Rejected: {self.stats['total_rejected']}")
        logger.info(f"   Errors: {self.stats['total_errors']}")

        trunc = self.stats["total_truncated"]
        if trunc:
            share = trunc / max(self.stats["total_processed"], 1) * 100
            logger.warning(
                f"   ⚠️  {trunc} item bị cắt vì chạm MAX_TOKENS ({share:.0f}%). "
                f"Nâng MAX_TOKENS trong .env, hoặc chạy với --allow-truncated nếu "
                f"chấp nhận câu trả lời cụt (KHÔNG khuyến nghị cho dữ liệu huấn luyện)."
            )
        logger.info(
            f"   Tiết kiệm được {self.stats['saved_answer_calls']} lượt gọi sinh IRAC "
            f"nhờ lọc sớm"
        )

        if self.stats["total_processed"] > 0:
            rate = self.stats["total_accepted"] / self.stats["total_processed"] * 100
            logger.info(f"   Acceptance rate: {rate:.1f}%")

        if self.stats["rejection_reasons"]:
            logger.info(f"   Rejection reasons:")
            for reason, count in sorted(
                self.stats["rejection_reasons"].items(),
                key=lambda x: x[1], reverse=True,
            ):
                logger.info(f"     - {reason}: {count}")

        if self.stats["techniques_used"]:
            logger.info(f"   Techniques used:")
            for tech, count in sorted(
                self.stats["techniques_used"].items(),
                key=lambda x: x[1], reverse=True,
            ):
                logger.info(f"     - {tech}: {count}")

        logger.info(f"   Output: {self.output_path}")
        logger.info(f"{'='*60}")
