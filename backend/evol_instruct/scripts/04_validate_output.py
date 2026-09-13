"""
Script 04: Kiểm tra và đánh giá chất lượng output.

Usage:
    python evol_instruct/scripts/04_validate_output.py
    python evol_instruct/scripts/04_validate_output.py --input data/evol_instruct/output/legal_evolved.jsonl
"""

import argparse
import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.settings import ensure_directories, OUTPUT_DIR
from evol_instruct.src.utils import setup_logging, load_jsonl
from evol_instruct.src.filters import filter_irac_structure, filter_min_length


def analyze_output(records: list[dict]) -> dict:
    """Phân tích chất lượng output JSONL."""
    stats = {
        "total_records": len(records),
        "avg_instruction_len": 0,
        "avg_output_len": 0,
        "min_output_len": float("inf"),
        "max_output_len": 0,
        "irac_pass_count": 0,
        "length_pass_count": 0,
        "techniques": Counter(),
        "linh_vuc": Counter(),
    }

    total_inst_len = 0
    total_out_len = 0

    for rec in records:
        inst = rec.get("instruction", "")
        output = rec.get("output", "")
        meta = rec.get("metadata", {})

        total_inst_len += len(inst)
        total_out_len += len(output)
        stats["min_output_len"] = min(stats["min_output_len"], len(output))
        stats["max_output_len"] = max(stats["max_output_len"], len(output))

        if filter_irac_structure(output):
            stats["irac_pass_count"] += 1
        if filter_min_length(output):
            stats["length_pass_count"] += 1

        tech = meta.get("technique", "unknown")
        stats["techniques"][tech] += 1

        src_meta = meta.get("source_metadata", {})
        lv = src_meta.get("linh_vuc", "unknown")
        if lv:
            stats["linh_vuc"][lv] += 1

    if records:
        stats["avg_instruction_len"] = total_inst_len / len(records)
        stats["avg_output_len"] = total_out_len / len(records)
    else:
        stats["min_output_len"] = 0

    return stats


def main():
    parser = argparse.ArgumentParser(description="Kiểm tra chất lượng output")
    parser.add_argument("--input", default=None, help="File JSONL đầu vào")
    args = parser.parse_args()

    logger = setup_logging("04_validate.log")
    ensure_directories()

    input_path = Path(args.input) if args.input else OUTPUT_DIR / "legal_evolved.jsonl"

    logger.info("=" * 60)
    logger.info("🔍 KIỂM TRA CHẤT LƯỢNG OUTPUT")
    logger.info(f"   File: {input_path}")
    logger.info("=" * 60)

    records = load_jsonl(input_path)
    if not records:
        logger.error(f"❌ File rỗng hoặc không tồn tại: {input_path}")
        sys.exit(1)

    stats = analyze_output(records)

    # Report
    logger.info(f"\n📊 BÁO CÁO CHẤT LƯỢNG:")
    logger.info(f"   Tổng records: {stats['total_records']}")
    logger.info(f"   Avg instruction length: {stats['avg_instruction_len']:.0f} chars")
    logger.info(f"   Avg output length: {stats['avg_output_len']:.0f} chars")
    logger.info(f"   Min/Max output: {stats['min_output_len']}/{stats['max_output_len']} chars")
    logger.info(f"   IRAC structure pass: {stats['irac_pass_count']}/{stats['total_records']} "
                f"({stats['irac_pass_count']/max(stats['total_records'],1)*100:.1f}%)")
    logger.info(f"   Length filter pass: {stats['length_pass_count']}/{stats['total_records']} "
                f"({stats['length_pass_count']/max(stats['total_records'],1)*100:.1f}%)")

    logger.info(f"\n   Techniques distribution:")
    for tech, count in stats["techniques"].most_common():
        pct = count / stats["total_records"] * 100
        logger.info(f"     - {tech}: {count} ({pct:.1f}%)")

    if stats["linh_vuc"]:
        logger.info(f"\n   Top lĩnh vực:")
        for lv, count in stats["linh_vuc"].most_common(10):
            logger.info(f"     - {lv}: {count}")

    # Lưu report JSON
    report_path = OUTPUT_DIR / "quality_report.json"
    report = {
        "total_records": stats["total_records"],
        "avg_instruction_len": round(stats["avg_instruction_len"], 1),
        "avg_output_len": round(stats["avg_output_len"], 1),
        "irac_pass_rate": round(
            stats["irac_pass_count"] / max(stats["total_records"], 1) * 100, 1
        ),
        "techniques": dict(stats["techniques"]),
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info(f"\n📄 Report saved → {report_path}")
    logger.info("\n✅ HOÀN TẤT!")


if __name__ == "__main__":
    main()
