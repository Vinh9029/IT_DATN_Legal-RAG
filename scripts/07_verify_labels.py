"""
Script 07: Kiểm chứng nhãn 3 tầng và lọc mẫu đồng thuận.

Bước 2 của Phần 3. Ba tầng nhãn độc lập:
    1. Provenance — có sẵn từ script 06 (câu sinh ở nhánh nào)
    2. Heuristic  — rule-based theo guideline §6, không tốn gì
    3. LLM judge  — model KHÁC, không biết provenance, 1 lượt gọi/câu

Provenance một mình không đủ: nó chỉ nói "ta đã YÊU CẦU model sinh câu broad",
không nói "model đã sinh ra câu broad thật". Model 8B thường xuyên không tuân
thủ. Ba tầng độc lập hội tụ cùng một nhãn là bằng chứng mạnh hơn hẳn.

Usage:
    python scripts/07_verify_labels.py --input data/qa_pairs/raw/pairs.jsonl
    python scripts/07_verify_labels.py --no-judge          # chỉ chạy heuristic, không tốn API
    python scripts/07_verify_labels.py --strict-consensus  # heuristic ambiguous = bất đồng
    python scripts/07_verify_labels.py --export-manual-sample 100
    python scripts/07_verify_labels.py --compute-kappa data/qa_pairs/labeled/manual_sample_blind.jsonl
"""

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.qa_settings import (
    JUDGE_CACHE_FILE,
    JUDGE_MODEL_NAME,
    MANUAL_SAMPLE_FILE,
    MANUAL_SAMPLE_SIZE,
    PAIRS_FILE,
    PASS_RATE_ABORT,
    PASS_RATE_GOOD,
    RANDOM_SEED,
    REJECTED_FILE,
    VERIFICATION_STATS_FILE,
    VERIFIED_FILE,
    ensure_qa_directories,
    validate_qa_config,
)
from src.qa_specificity.dataset_builder import (
    build_verification_stats,
    compute_kappa,
    filter_consensus,
    save_json,
)
from src.qa_specificity.llm_judge import JudgeClient, judge_batch
from src.qa_specificity.schema import QAItem, Specificity
from src.qa_specificity.weak_labeler import label_items
from src.utils import load_jsonl, save_jsonl, setup_logging


def cmd_export_manual_sample(args, logger):
    """
    Xuất mẫu ĐÃ ẨN NHÃN cho vòng gán tay ở Bước 3.

    Nhãn máy bị loại bỏ hoàn toàn khỏi file: nhìn thấy nhãn máy trước khi gán
    tay gây anchoring bias, và hệ số κ tính ra sau đó không có giá trị gì.
    """
    items = [QAItem.from_dict(r) for r in load_jsonl(args.input_verified)]
    if not items:
        logger.error(f"❌ Không đọc được item nào từ {args.input_verified}")
        sys.exit(1)

    n = min(args.export_manual_sample, len(items))
    rng = random.Random(RANDOM_SEED)
    sample = rng.sample(items, n)

    save_jsonl([i.blinded_dict() for i in sample], args.manual_sample, mode="w")

    logger.info(f"✅ Đã xuất {n} câu ĐÃ ẨN NHÃN → {args.manual_sample}")
    logger.info("\n📋 Việc cần làm bằng tay:")
    logger.info("   1. Mở file, điền trường `manual_label` cho từng dòng:")
    logger.info("      broad | narrow | ambiguous")
    logger.info("   2. Chấm theo 3 trục ở docs/specificity-guideline.md §3, tổng hợp theo §4")
    logger.info("   3. TUYỆT ĐỐI không mở pairs_verified.jsonl trong lúc gán")
    logger.info("   4. Gán xong toàn bộ rồi mới chạy:")
    logger.info(f"      python scripts/07_verify_labels.py --compute-kappa {args.manual_sample}")


def cmd_compute_kappa(args, logger):
    """Tính Cohen's kappa giữa nhãn tay và judge_label — deliverable #3."""
    manual_records = load_jsonl(args.compute_kappa)
    if not manual_records:
        logger.error(f"❌ Không đọc được file nhãn tay: {args.compute_kappa}")
        sys.exit(1)

    machine_by_id = {
        r["item_id"]: r for r in load_jsonl(args.input_verified) if r.get("item_id")
    }

    manual_labels, machine_labels, skipped = [], [], 0
    for record in manual_records:
        manual = Specificity.parse(record.get("manual_label"))
        machine_record = machine_by_id.get(record.get("item_id"))

        if manual is None or machine_record is None:
            skipped += 1
            continue
        # Câu gán tay là `ambiguous` bị loại khỏi phép tính: dataset đã ẩn định
        # là nhị phân, đưa lớp thứ ba vào làm κ không so sánh được với thang
        # đọc ở guideline §7.
        if manual == Specificity.AMBIGUOUS:
            skipped += 1
            continue

        machine = Specificity.parse(machine_record.get("judge_label"))
        if machine is None:
            skipped += 1
            continue

        manual_labels.append(manual.value)
        machine_labels.append(machine.value)

    if not manual_labels:
        logger.error("❌ Không có cặp nhãn nào hợp lệ để tính kappa. Đã điền `manual_label` chưa?")
        sys.exit(1)

    result = compute_kappa(manual_labels, machine_labels)
    result["skipped"] = skipped
    result["compared_against"] = "judge_label"

    logger.info("\n📐 COHEN'S KAPPA (nhãn tay vs judge_label)")
    logger.info(f"   n mẫu so sánh : {result['n_samples']} (bỏ qua {skipped})")
    logger.info(f"   κ             : {result['cohen_kappa']}")
    logger.info(f"   Trùng khớp thô: {result['raw_agreement']:.1%}")
    logger.info(f"   Nhãn          : {result['labels']}")
    logger.info(f"   Confusion     : {result['confusion_matrix']}  (hàng=tay, cột=máy)")
    logger.info(f"   → {result['interpretation']}")

    out_path = Path(args.compute_kappa).parent / "kappa_report.json"
    save_json(result, out_path)


def cmd_verify(args, logger):
    """Luồng chính: heuristic + judge → lọc đồng thuận."""
    records = load_jsonl(args.input)
    if not records:
        logger.error(f"❌ Không đọc được item nào từ {args.input}. Chạy script 06 trước.")
        sys.exit(1)

    items = [QAItem.from_dict(r) for r in records]
    logger.info(f"Đọc {len(items)} câu hỏi từ {len({i.pair_id for i in items})} cặp")

    # ── Tầng 2: heuristic ─────────────────────────────────────────
    logger.info("\n[Tầng 2] Heuristic rule-based (guideline §6)...")
    label_items(items)
    from collections import Counter
    heuristic_dist = Counter(
        i.heuristic_label.value if i.heuristic_label else "none" for i in items
    )
    logger.info(f"   Phân bố: {dict(heuristic_dist)}")

    # ── Tầng 3: LLM judge ─────────────────────────────────────────
    if args.no_judge:
        logger.warning(
            "\n[Tầng 3] BỎ QUA judge (--no-judge). Kết quả CHỈ để thử nhanh heuristic, "
            "KHÔNG dùng làm dataset thật: thiếu tầng độc lập thì không có kiểm chứng nào cả."
        )
    else:
        logger.info(f"\n[Tầng 3] LLM judge — model: {JUDGE_MODEL_NAME}")
        judge = JudgeClient()
        if not judge.health_check():
            logger.error("❌ Judge model không phản hồi. Kiểm tra JUDGE_* trong .env")
            sys.exit(1)
        judge_batch(items, judge=judge, cache_path=args.judge_cache)

    # ── Lọc đồng thuận ────────────────────────────────────────────
    logger.info("\n[Hợp nhất] Lọc mẫu đồng thuận...")
    verified, rejected = filter_consensus(
        items,
        strict=args.strict_consensus,
        require_complete_pairs=not args.allow_incomplete_pairs,
    )

    # Chạy lại theo cách đọc chặt để có số đối chiếu cho phần Limitations.
    # Phải deep-copy vì resolve_item ghi đè tại chỗ.
    strict_count = None
    if not args.strict_consensus:
        import copy
        strict_items = copy.deepcopy(items)
        strict_verified, _ = filter_consensus(
            strict_items, strict=True, require_complete_pairs=not args.allow_incomplete_pairs
        )
        strict_count = len(strict_verified)

    stats = build_verification_stats(items, verified, rejected, strict_verified_count=strict_count)

    save_jsonl([i.to_dict() for i in verified], args.output_verified, mode="w")
    save_jsonl([i.to_dict() for i in rejected], args.output_rejected, mode="w")
    save_json(stats, args.output_stats)

    # ── Checkpoint quyết định (spec §4 bước 2) ────────────────────
    pass_rate = stats["pass_rate"]
    logger.info("\n📊 TỔNG KẾT KIỂM CHỨNG:")
    logger.info(f"   Tổng câu vào    : {stats['total_items']}")
    logger.info(f"   Giữ lại         : {stats['verified_items']} ({pass_rate:.1%})")
    logger.info(f"   Loại            : {stats['rejected_items']}")
    logger.info(f"   Lý do loại      : {stats['reject_reasons']}")
    logger.info(f"   Đồng thuận từng đôi: {stats['pairwise_agreement']}")
    if strict_count is not None:
        logger.info(f"   (đọc chặt sẽ giữ: {strict_count} câu)")
    logger.info(f"   Nhãn cuối       : {stats['label_distribution']['final_verified']}")

    logger.info("")
    if pass_rate > PASS_RATE_GOOD:
        logger.info("✅ Pass rate > 70% — prompt tốt, model tuân thủ. Đi tiếp Bước 3/4:")
        logger.info(f"   python scripts/07_verify_labels.py --export-manual-sample {MANUAL_SAMPLE_SIZE}")
        logger.info("   python scripts/08_export_dataset.py")
    elif pass_rate >= PASS_RATE_ABORT:
        logger.warning(
            f"⚠️  Pass rate {pass_rate:.1%} (40-70%) — chấp nhận được nhưng còn lãng phí. "
            f"Đọc {args.output_rejected}, tìm pattern lỗi, tinh chỉnh prompt rồi chạy lại 06."
        )
    else:
        logger.error(
            f"🛑 Pass rate {pass_rate:.1%} < 40% — DỪNG LẠI. Prompt hoặc tiêu chí có vấn đề "
            f"nghiêm trọng. Chạy tiếp chỉ tổ đốt thời gian trên pipeline hỏng. "
            f"Quay về xem lại docs/specificity-guideline.md và config/qa_prompts.py."
        )
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Kiểm chứng nhãn độ cụ thể 3 tầng")
    parser.add_argument("--input", type=Path, default=PAIRS_FILE,
                        help="File pairs.jsonl từ script 06")
    parser.add_argument("--input-verified", type=Path, default=VERIFIED_FILE,
                        help="File verified (dùng cho --export-manual-sample / --compute-kappa)")
    parser.add_argument("--output-verified", type=Path, default=VERIFIED_FILE)
    parser.add_argument("--output-rejected", type=Path, default=REJECTED_FILE)
    parser.add_argument("--output-stats", type=Path, default=VERIFICATION_STATS_FILE)
    parser.add_argument("--judge-cache", type=Path, default=JUDGE_CACHE_FILE,
                        help="Cache kết quả judge để chạy lại không tốn API")
    parser.add_argument("--manual-sample", type=Path, default=MANUAL_SAMPLE_FILE)

    parser.add_argument("--no-judge", action="store_true",
                        help="Bỏ tầng judge (chỉ để thử nhanh heuristic)")
    parser.add_argument("--strict-consensus", action="store_true",
                        help="Coi heuristic 'ambiguous' là bất đồng thay vì abstain")
    parser.add_argument("--allow-incomplete-pairs", action="store_true",
                        help="Giữ cả câu mà cặp của nó đã mất vế kia")

    parser.add_argument("--export-manual-sample", type=int, metavar="N",
                        help="Xuất N câu đã ẩn nhãn cho vòng gán tay (Bước 3)")
    parser.add_argument("--compute-kappa", type=Path, metavar="FILE",
                        help="Tính Cohen's kappa từ file nhãn tay đã điền")
    args = parser.parse_args()

    logger = setup_logging("07_verify_labels.log")
    ensure_qa_directories()
    for warning in validate_qa_config():
        logger.warning(warning)

    logger.info("=" * 60)
    logger.info("🔍 BƯỚC 2 — KIỂM CHỨNG NHÃN 3 TẦNG")
    logger.info("=" * 60)

    if args.export_manual_sample:
        cmd_export_manual_sample(args, logger)
    elif args.compute_kappa:
        cmd_compute_kappa(args, logger)
    else:
        cmd_verify(args, logger)


if __name__ == "__main__":
    main()
