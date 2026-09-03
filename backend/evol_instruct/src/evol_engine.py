"""
Evol-Instruct Engine - Core pipeline tiến hóa câu hỏi pháp lý.

Quy trình:
1. Chọn random kỹ thuật tiến hóa (6 techniques)
2. Gọi LLM để rewrite seed → evolved instruction
3. Gọi LLM để sinh IRAC response (temp thấp)
4. Chạy Instruction Eliminator filters
5. Lưu kết quả Alpaca JSONL format
"""

import json
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
from evol_instruct.src.llm_client import LLMClient
from evol_instruct.src.filters import instruction_eliminator
from evol_instruct.src.utils import (
    append_jsonl,
    Checkpoint,
    generate_item_id,
    truncate_text,
)


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
        checkpoint_file: str = "evolution_checkpoint.json",
        legal_references: set[str] = None,
    ):
        self.llm = llm_client or LLMClient()
        self.output_path = OUTPUT_DIR / output_file
        self.checkpoint = Checkpoint(OUTPUT_DIR / checkpoint_file)
        self.legal_references = legal_references or set()

        # Danh sách technique keys
        self.technique_keys = list(EVOL_TECHNIQUES.keys())

        # Thống kê
        self.stats = {
            "total_processed": 0,
            "total_accepted": 0,
            "total_rejected": 0,
            "rejection_reasons": {},
            "techniques_used": {},
        }

        logger.info(
            f"EvolPipeline initialized | "
            f"output={self.output_path} | "
            f"techniques={len(self.technique_keys)} | "
            f"legal_refs={len(self.legal_references)}"
        )

    def evolve_instruction(self, seed_instruction: str, technique_key: str = None) -> str:
        """
        Bước 1: Tiến hóa instruction bằng kỹ thuật được chọn.

        Args:
            seed_instruction: Câu hỏi gốc (seed).
            technique_key: Key của kỹ thuật (None = random).

        Returns:
            Evolved instruction string.
        """
        if not technique_key:
            technique_key = random.choice(self.technique_keys)

        technique = EVOL_TECHNIQUES[technique_key]
        user_prompt = technique["prompt"].format(seed_instruction=seed_instruction)

        messages = [
            {"role": "system", "content": SYSTEM_EVOL_REWRITER},
            {"role": "user", "content": user_prompt},
        ]

        evolved = self.llm.chat(
            messages=messages,
            temperature=EVOL_TEMPERATURE,
        )

        logger.debug(
            f"Evolved [{technique['name']}]: "
            f"{truncate_text(evolved, 150)}"
        )

        return evolved

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
        )

        logger.debug(f"IRAC response: {truncate_text(response, 150)}")
        return response

    def process_single(self, seed: dict, technique_key: str = None) -> dict | None:
        """
        Xử lý một seed: evolve → respond → filter → save.

        Returns:
            Record dict nếu accepted, None nếu rejected.
        """
        seed_instruction = seed["instruction"]
        item_id = seed.get("id", generate_item_id(seed_instruction))

        # Kiểm tra checkpoint
        if self.checkpoint.is_processed(item_id):
            logger.debug(f"Skipped (checkpoint): {item_id}")
            return None

        # Chọn technique
        if not technique_key:
            technique_key = random.choice(self.technique_keys)

        try:
            # Bước 1: Evolve
            evolved = self.evolve_instruction(seed_instruction, technique_key)

            # Bước 2: Generate IRAC response
            response = self.generate_irac_response(evolved)

            # Bước 3: Filter
            passed, failed = instruction_eliminator(
                original_prompt=seed_instruction,
                evolved_prompt=evolved,
                response=response,
                legal_refs=self.legal_references,
            )

            self.stats["total_processed"] += 1
            self.stats["techniques_used"][technique_key] = (
                self.stats["techniques_used"].get(technique_key, 0) + 1
            )

            if passed:
                # Bước 4: Lưu (Alpaca JSONL format)
                record = {
                    "instruction": evolved,
                    "input": "",
                    "output": response,
                    "metadata": {
                        "technique": technique_key,
                        "seed_id": item_id,
                        "seed_instruction": seed_instruction,
                        "timestamp": datetime.now().isoformat(),
                        "source_metadata": seed.get("metadata", {}),
                    },
                }
                append_jsonl(record, self.output_path)
                self.stats["total_accepted"] += 1
                logger.info(f"✅ ACCEPTED [{technique_key}] → {item_id}")
            else:
                self.stats["total_rejected"] += 1
                for reason in failed:
                    self.stats["rejection_reasons"][reason] = (
                        self.stats["rejection_reasons"].get(reason, 0) + 1
                    )
                logger.info(f"❌ REJECTED [{technique_key}] → {failed}")
                record = None

            # Cập nhật checkpoint
            self.checkpoint.mark_processed(item_id)
            self.checkpoint.update_stats("pipeline_stats", self.stats)
            self.checkpoint.save()

            return record

        except Exception as e:
            logger.error(f"Error processing {item_id}: {e}")
            return None

    def run(self, seeds: list[dict], batch_size: int = None):
        """
        Chạy pipeline trên toàn bộ danh sách seeds.

        Args:
            seeds: Danh sách seed dicts.
            batch_size: Kích thước batch (logging checkpoint mỗi batch).
        """
        batch_size = batch_size or BATCH_SIZE
        total = len(seeds)
        skipped = 0

        logger.info(f"{'='*60}")
        logger.info(f"🚀 BẮT ĐẦU EVOL-INSTRUCT PIPELINE")
        logger.info(f"   Seeds: {total} | Batch: {batch_size}")
        logger.info(f"   Already processed: {self.checkpoint.processed_count}")
        logger.info(f"   Output: {self.output_path}")
        logger.info(f"{'='*60}")

        for i, seed in enumerate(tqdm(seeds, desc="Evol-Instruct")):
            item_id = seed.get("id", generate_item_id(seed["instruction"]))
            if self.checkpoint.is_processed(item_id):
                skipped += 1
                continue

            self.process_single(seed)

            # Log batch summary
            if (i + 1) % batch_size == 0:
                self._log_progress(i + 1, total, skipped)

        # Final summary
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
