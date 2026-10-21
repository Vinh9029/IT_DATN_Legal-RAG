"""
Script 22: Export dữ liệu Evol-Instruct (grounded) thành dataset để publish lên HF.

Split dùng lại `split_by_source` của script 20 (seed 42, 10%) nên `validation`
trùng đúng tập eval lúc fine-tune.

Usage:
    python evol_instruct/scripts/22_export_evol_dataset.py
"""

import argparse
import collections
import importlib.util
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_INPUT = BACKEND_DIR / "data" / "evol_instruct" / "output" / "legal_evolved.jsonl"
DEFAULT_OUT = BACKEND_DIR / "data" / "evol_instruct" / "final"

_DIEU_RE = re.compile(r"#dieu-(\w+)$")


def to_row(rec: dict, scopes: dict[str, str]) -> dict:
    meta = rec["metadata"]
    src = meta.get("source_metadata") or {}
    sid = src.get("source_doc_id", "")
    m = _DIEU_RE.search(sid)
    return {
        "id": meta["seed_id"],
        "instruction": rec["instruction"],
        "input": rec["input"],
        "output": rec["output"],
        "technique": meta["technique"],
        "source_doc_id": sid,
        "document": src.get("so_hieu_luat", ""),
        "dieu": m.group(1) if m else "",
        "scope": scopes.get(sid, ""),
        "seed_instruction": meta["seed_instruction"],
    }


def split_stats(rows: list[dict]) -> dict:
    return {
        "n_items": len(rows),
        "n_source_articles": len({r["source_doc_id"] for r in rows}),
        "technique_counts": dict(collections.Counter(r["technique"] for r in rows).most_common()),
        "scope_counts": dict(collections.Counter(r["scope"] for r in rows).most_common()),
        "words_mean": {f: round(statistics.mean(len(r[f].split()) for r in rows), 1)
                       for f in ("instruction", "input", "output")},
    }


def main():
    ap = argparse.ArgumentParser(description="Export dataset Evol-Instruct grounded")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    from loguru import logger
    from evol_instruct.src.qa_specificity.corpus_filter import load_scoped_corpus

    spec = importlib.util.spec_from_file_location(
        "ft20", Path(__file__).resolve().parent / "20_finetune_generator.py")
    ft20 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ft20)

    records = ft20.load_records(args.input)
    train_recs, eval_recs = ft20.split_by_source(records, eval_ratio=0.1, seed=42)

    # `linh_vuc` của seed lẫn lộn nhiều kiểu → lấy `scope` từ corpus cho đồng nhất với dataset QA.
    scopes = {d["source_doc_id"]: d.get("scope", "") for d in load_scoped_corpus()}
    train = [to_row(r, scopes) for r in train_recs]
    val = [to_row(r, scopes) for r in eval_recs]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("train.json", train), ("val.json", val)):
        (args.output_dir / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    stats = {
        "total_items": len(train) + len(val),
        "total_source_articles": len({r["source_doc_id"] for r in train + val}),
        "split_by": "source_doc_id",
        "splits": {"train": split_stats(train), "validation": split_stats(val)},
        "all": split_stats(train + val),
    }
    (args.output_dir / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"train {len(train)} / validation {len(val)} → {args.output_dir}")


if __name__ == "__main__":
    main()
