"""
Script 10: Sinh cặp câu hỏi đối chứng broad/narrow từ corpus pháp luật.

Bước 1 của Phần 3. Output là nhãn PROVENANCE (câu sinh ở nhánh nào thì mang
nhãn đó) — CHƯA qua kiểm chứng nào, chưa dùng được. Chạy tiếp script 11.

Usage:
    python scripts/10_generate_qa_pairs.py --max-docs 500
    python scripts/10_generate_qa_pairs.py --max-docs 50 --dry-run
    python scripts/10_generate_qa_pairs.py --restart          # bỏ checkpoint cũ
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tqdm import tqdm

from config.qa_settings import (
    GENERATION_CHECKPOINT,
    GEN_LLM_BASE_URL,
    GEN_MODEL_NAME,
    PAIRS_FILE,
    ensure_qa_directories,
    validate_qa_config,
)
from src.llm_client import LLMClient
from src.qa_specificity.corpus_filter import load_scoped_corpus
from src.qa_specificity.pair_generator import generate_pair
from src.utils import Checkpoint, append_jsonl, setup_logging


def main():
    parser = argparse.ArgumentParser(description="Sinh cặp câu hỏi broad/narrow")
    parser.add_argument("--max-docs", type=int, default=0,
                        help="Số document trong phạm vi tối đa (0 = tất cả)")
    parser.add_argument("--output", type=Path, default=PAIRS_FILE,
                        help="File JSONL output")
    parser.add_argument("--checkpoint", type=Path, default=GENERATION_CHECKPOINT,
                        help="File checkpoint để resume")
    parser.add_argument("--restart", action="store_true",
                        help="Xoá checkpoint và output cũ, chạy lại từ đầu")
    parser.add_argument("--dry-run", action="store_true",
                        help="Chỉ lọc corpus và in thống kê, không gọi LLM")
    args = parser.parse_args()

    logger = setup_logging("06_qa_pairs.log")
    ensure_qa_directories()
    for warning in validate_qa_config():
        logger.warning(warning)

    logger.info("=" * 60)
    logger.info("🧩 BƯỚC 1 — SINH CẶP CÂU HỎI ĐỐI CHỨNG (broad / narrow)")
    logger.info("=" * 60)

    # ── Corpus ────────────────────────────────────────────────────
    documents = load_scoped_corpus(max_items=args.max_docs)
    if not documents:
        logger.error("❌ Không có document nào trong phạm vi. Dừng.")
        sys.exit(1)

    if args.dry_run:
        from collections import Counter
        scopes = Counter(d.get("scope", "") or "unknown" for d in documents)
        logger.info(f"[dry-run] {len(documents)} documents trong phạm vi")
        logger.info(f"[dry-run] Phân bố scope: {dict(scopes)}")
        logger.info("[dry-run] Không gọi LLM. Bỏ --dry-run để chạy thật.")
        return

    # ── Checkpoint ────────────────────────────────────────────────
    if args.restart:
        for path in (args.checkpoint, args.output):
            if path.exists():
                path.unlink()
                logger.info(f"Đã xoá {path}")

    checkpoint = Checkpoint(args.checkpoint)
    logger.info(f"Checkpoint: {checkpoint.processed_count} documents đã xử lý trước đó")

    pending = [d for d in documents if not checkpoint.is_processed(d["source_doc_id"])]
    if not pending:
        logger.info("✅ Tất cả documents đã được xử lý. Không còn gì để làm.")
        return
    logger.info(f"Còn {len(pending)}/{len(documents)} documents cần xử lý")

    # ── LLM ───────────────────────────────────────────────────────
    llm = LLMClient()
    logger.info(f"Generator: {GEN_MODEL_NAME} @ {GEN_LLM_BASE_URL}")
    if not llm.health_check():
        logger.error("❌ LM Studio server không khả dụng!")
        logger.error("   Khởi động LM Studio và bật Local Server tại port 1234")
        sys.exit(1)

    # ── Sinh cặp ──────────────────────────────────────────────────
    n_pairs = 0
    n_failed = 0

    try:
        for doc in tqdm(pending, desc="Sinh cặp câu hỏi"):
            doc_id = doc["source_doc_id"]
            items = generate_pair(doc, llm)

            if items:
                # Ghi từng record ngay thay vì gom cuối: mất điện giữa chừng
                # thì phần đã sinh vẫn còn nguyên.
                for item in items:
                    append_jsonl(item.to_dict(), args.output)
                n_pairs += 1
            else:
                n_failed += 1

            checkpoint.mark_processed(doc_id)
            # Lưu checkpoint mỗi 10 doc — đủ dày để không mất nhiều khi crash,
            # đủ thưa để không ghi đĩa liên tục.
            if (n_pairs + n_failed) % 10 == 0:
                checkpoint.update_stats("pairs_generated", n_pairs)
                checkpoint.update_stats("failed_docs", n_failed)
                checkpoint.save()
    except KeyboardInterrupt:
        logger.warning("⚠️  Ngắt bởi người dùng — đang lưu checkpoint...")
    finally:
        checkpoint.update_stats("pairs_generated", n_pairs)
        checkpoint.update_stats("failed_docs", n_failed)
        checkpoint.save()

    # ── Tổng kết ──────────────────────────────────────────────────
    attempted = n_pairs + n_failed
    success_rate = n_pairs / attempted if attempted else 0.0

    logger.info("\n📊 TỔNG KẾT:")
    logger.info(f"   Documents xử lý lượt này: {attempted}")
    logger.info(f"   Cặp sinh thành công:      {n_pairs} ({success_rate:.1%})")
    logger.info(f"   Không parse được cặp:     {n_failed}")
    logger.info(f"   Tổng câu hỏi ghi ra:      {n_pairs * 2}")
    logger.info(f"   Output → {args.output}")

    if attempted and success_rate < 0.5:
        logger.warning(
            "⚠️  Hơn nửa số document không sinh được cặp hợp lệ. Xem log DEBUG để đọc "
            "raw output — thường là model không tuân thủ định dạng [BROAD]/[NARROW]. "
            "Cân nhắc siết lại SYSTEM_PAIR_GENERATOR trong config/qa_prompts.py."
        )

    logger.info("\n⚠️  Nhãn hiện tại mới chỉ là PROVENANCE, chưa qua kiểm chứng.")
    logger.info("   Bước tiếp theo: python scripts/11_verify_labels.py")


if __name__ == "__main__":
    main()
