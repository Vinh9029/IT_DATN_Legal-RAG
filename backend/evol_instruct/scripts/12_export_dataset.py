"""
Script 12: Chia train/val/test theo group và export dataset cuối.

Bước 4 của Phần 3.

Split BẮT BUỘC theo group `source_doc_id`, không được random split: hai câu
trong một cặp cùng sinh từ một văn bản nên nội dung chồng lấn rất nhiều. Câu
broad rơi vào train mà câu narrow rơi vào test thì model đã "thấy" điều luật đó
lúc train — data leakage, metric cao giả tạo, và không có thông báo lỗi nào cả.

Usage:
    python evol_instruct/scripts/12_export_dataset.py
    python evol_instruct/scripts/12_export_dataset.py --input data/qa_pairs/labeled/pairs_verified.jsonl
    python evol_instruct/scripts/12_export_dataset.py --seed 7
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.qa_settings import (
    BASE_DIR,
    QA_FINAL_DIR,
    RANDOM_SEED,
    STATS_FILE,
    TEST_FILE,
    TEST_RATIO,
    TRAIN_FILE,
    TRAIN_RATIO,
    VAL_FILE,
    VAL_RATIO,
    VERIFIED_FILE,
    ensure_qa_directories,
    validate_qa_config,
)
from evol_instruct.src.qa_specificity.dataset_builder import (
    build_stats,
    export,
    group_split,
    save_json,
)
from evol_instruct.src.qa_specificity.schema import QAItem, Specificity
from evol_instruct.src.utils import load_jsonl, setup_logging


def relative_to_base(path: Path) -> str:
    try:
        return path.resolve().relative_to(BASE_DIR).as_posix()
    except ValueError:
        return path.name


def main():
    parser = argparse.ArgumentParser(description="Chia tập và export dataset QA specificity")
    parser.add_argument("--input", type=Path, default=VERIFIED_FILE,
                        help="File pairs_verified.jsonl từ script 11")
    parser.add_argument("--output-dir", type=Path, default=QA_FINAL_DIR)
    parser.add_argument("--train-ratio", type=float, default=TRAIN_RATIO)
    parser.add_argument("--val-ratio", type=float, default=VAL_RATIO)
    parser.add_argument("--test-ratio", type=float, default=TEST_RATIO)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()

    logger = setup_logging("12_export_dataset.log")
    ensure_qa_directories()
    for warning in validate_qa_config():
        logger.warning(warning)

    logger.info("=" * 60)
    logger.info("📦 BƯỚC 4 — CHIA TẬP & EXPORT DATASET")
    logger.info("=" * 60)

    # ── Load ──────────────────────────────────────────────────────
    records = load_jsonl(args.input)
    if not records:
        logger.error(f"❌ Không đọc được item nào từ {args.input}. Chạy script 11 trước.")
        sys.exit(1)

    items = [QAItem.from_dict(r) for r in records]

    # Chỉ nhận item đã có nhãn cuối thật sự. `pairs_verified.jsonl` lẽ ra chỉ
    # chứa loại này, nhưng kiểm lại vẫn hơn — một item lọt lưới với
    # final_label=None sẽ âm thầm phá thống kê cân bằng nhãn.
    usable = [i for i in items if isinstance(i.final_label, Specificity) and i.final_label.is_decided]
    if len(usable) != len(items):
        logger.warning(f"Bỏ qua {len(items) - len(usable)} item không có final_label hợp lệ")
    if not usable:
        logger.error("❌ Không còn item nào dùng được.")
        sys.exit(1)

    logger.info(
        f"Đầu vào: {len(usable)} câu | {len({i.pair_id for i in usable})} cặp | "
        f"{len({i.source_doc_id for i in usable})} văn bản nguồn"
    )

    # ── Split ─────────────────────────────────────────────────────
    logger.info(f"\nGroup split theo source_doc_id (seed={args.seed}):")
    try:
        splits = group_split(
            usable,
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            test_ratio=args.test_ratio,
            seed=args.seed,
        )
    except (ValueError, AssertionError) as e:
        logger.error(f"❌ {e}")
        sys.exit(1)

    logger.info("✅ Bất biến chống rò rỉ: PASSED (không source_doc_id nào nằm ở 2 split)")

    # ── Export ────────────────────────────────────────────────────
    paths = {
        "train": args.output_dir / TRAIN_FILE.name,
        "val": args.output_dir / VAL_FILE.name,
        "test": args.output_dir / TEST_FILE.name,
    }
    logger.info("")
    export(splits, paths)

    stats = build_stats(splits)
    stats["source_file"] = relative_to_base(args.input)
    stats["random_seed"] = args.seed
    save_json(stats, args.output_dir / STATS_FILE.name)

    # ── Tổng kết ──────────────────────────────────────────────────
    logger.info("\n📊 THỐNG KÊ DATASET:")
    for name in ("train", "val", "test"):
        split_stats = stats["splits"][name]
        logger.info(
            f"   {name:5s}: {split_stats['n_items']:4d} câu | "
            f"{split_stats['n_pairs']:4d} cặp | "
            f"{split_stats['n_source_docs']:4d} văn bản | "
            f"nhãn={split_stats['label_counts']}"
        )

    logger.info(f"\n✅ HOÀN TẤT! Output → {args.output_dir}")
    logger.info("\n📋 Còn lại để hoàn thành Phần 3:")
    logger.info("   - Bước 3 (nếu chưa làm): gán tay ~100 câu và tính Cohen's kappa")
    logger.info("     python evol_instruct/scripts/11_verify_labels.py --export-manual-sample 100")


if __name__ == "__main__":
    main()
