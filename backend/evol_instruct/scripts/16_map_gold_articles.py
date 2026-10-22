"""
Script 16: Map Điều nguồn của mỗi câu hỏi sang chunk trong knowledge base 518k.

─── Vì sao cần script này ───

`source_doc_id` của dataset QA là id của corpus dân sự (`doc_xxx#dieu-34`), còn
KB online dùng doc_id của HF dataset — hai bộ id không chung nhau. Muốn đo
Recall@K thì phải biết Điều gold nằm ở chunk nào trong KB. Khoá chung duy nhất
là (số hiệu văn bản, số Điều):

  - Số hiệu lấy từ metadata.so_hieu; 5 phần PDF của BLDS/BLTTDS để trống trường
    này nên tách từ title ("(91-2015-QH13)" → "91/2015/QH13").
  - Văn bản không chia Điều (source_doc_id không có "#dieu-") thì mọi chunk của
    văn bản đó đều tính là gold.
  - Chuẩn hoá chữ Cyrillic lẫn vào số hiệu (vd "TT-BTС" dùng С Cyrillic).

Câu nào không tìm thấy gold trong KB (văn bản đã bị lọc vì hết hiệu lực, hoặc
ban hành sau snapshot của HF dataset) bị loại khỏi đánh giá retrieval.

─── Cách dùng ───

    cd backend/
    python evol_instruct/scripts/16_map_gold_articles.py
    → data/qa_pairs/eval/gold_map.json  ({item_id: [chunk_id, ...]}) + thống kê
"""

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from loguru import logger

FINAL_DIR = ROOT / "data" / "qa_pairs" / "final"
CHUNKS_PATH = ROOT / "data" / "rag" / "processed" / "chunks" / "chunks.jsonl"
OUT_PATH = ROOT / "data" / "qa_pairs" / "eval" / "gold_map.json"

RE_TITLE_SO_HIEU = re.compile(r"\((\d+)-(\d{4})-([A-ZĐ0-9]+)\)")
CYRILLIC = str.maketrans("АВСЕНКМОРТХ", "ABCEHKMOPTX")


def norm_so_hieu(s: str) -> str:
    return (s or "").translate(CYRILLIC).strip().upper()


def so_hieu_cua(r: dict) -> str:
    md = r["metadata"]
    if md.get("so_hieu"):
        return norm_so_hieu(md["so_hieu"])
    m = RE_TITLE_SO_HIEU.search(md.get("title", ""))
    return norm_so_hieu("/".join(m.groups())) if m else ""


def main():
    rows = []
    for split in ("train", "val", "test"):
        for r in json.loads((FINAL_DIR / f"{split}.json").read_text(encoding="utf-8")):
            r["_split"] = split
            rows.append(r)

    can = {so_hieu_cua(r) for r in rows} - {""}
    logger.info(f"{len(rows)} câu, {len(can)} số hiệu cần tìm trong KB")

    # (so_hieu, dieu) -> chunk_ids ; so_hieu -> mọi chunk_id
    theo_dieu = collections.defaultdict(set)
    theo_vb = collections.defaultdict(set)
    with CHUNKS_PATH.open(encoding="utf-8") as f:
        for line in f:
            if '"so_hieu"' not in line:
                continue
            d = json.loads(line)
            sh = norm_so_hieu((d.get("metadata") or {}).get("so_hieu", ""))
            if sh not in can:
                continue
            theo_vb[sh].add(d["chunk_id"])
            theo_dieu[(sh, str(d.get("dieu", "")))].add(d["chunk_id"])

    gold, thong_ke = {}, collections.Counter()
    vb_thieu = collections.Counter()
    for r in rows:
        sh = so_hieu_cua(r)
        if "#dieu-" in r["source_doc_id"]:
            ids = theo_dieu.get((sh, str(r["metadata"].get("dieu", ""))), set())
        else:
            ids = theo_vb.get(sh, set())
        if ids:
            gold[r["item_id"]] = sorted(ids)
            thong_ke[(r["_split"], "co")] += 1
        else:
            thong_ke[(r["_split"], "thieu")] += 1
            vb_thieu[(sh, sh in theo_vb)] += 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")

    for split in ("train", "val", "test"):
        co, thieu = thong_ke[(split, "co")], thong_ke[(split, "thieu")]
        logger.info(f"{split:5s}: có gold {co:5d} | không có {thieu:4d}")
    nhieu = sum(len(v) > 1 for v in gold.values())
    logger.info(f"Câu có >1 chunk gold (văn bản trùng số hiệu / không chia Điều): {nhieu}")
    logger.info("Thiếu theo văn bản (số hiệu, văn bản có trong KB?):")
    for (sh, co_vb), n in vb_thieu.most_common(25):
        logger.info(f"   {n:4d}  {sh or '(không tách được số hiệu)'}  {'có VB, thiếu Điều' if co_vb else 'không có VB'}")
    logger.info(f"→ {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
