"""
D1 — Bộ test trích dẫn bị làm sai CÓ KIỂM SOÁT cho Citation Verification.

Nguồn: 1.111 câu trả lời Evol-Instruct grounded (data/evol_instruct/final/{train,val}.json).
Mỗi câu trả lời được sinh từ đúng MỘT Điều nguồn đã biết, nên trích dẫn tới Điều đó
là trích dẫn đúng có nhãn sẵn. Lấy một trích dẫn đích / câu trả lời rồi sửa chữ trong
câu trả lời để tạo biến thể — nhãn đúng/sai biết từ cách tạo, không cần gán nhãn tay.

Biến thể (nhãn kỳ vọng):
    C0_original      giữ nguyên                       → không bị báo invalid
    C1_nonexistent   Điều N → Điều > Điều lớn nhất     → invalid (dieu_out_of_range)
    C2_neighbor      Điều N → Điều N±1..3 có thật     → invalid (nội dung không khớp)
    C3_far           Điều N → Điều xa (|Δ| ≥ 20)      → invalid (nội dung không khớp)
    C4_expired       văn bản → văn bản cùng loại đã hết hiệu lực → invalid (expired)
    C5_fabricated    văn bản → số hiệu không tồn tại  → unverifiable (doc_not_found)

Chia dev/test theo VĂN BẢN NGUỒN (group split) để ngưỡng chọn trên dev không rò sang test.

LƯU Ý vòng lặp: dữ liệu Evol đã được lọc bằng `filter_context_citations` (regex "Điều N"
giống extractor) → tỉ lệ trích xuất được trên tập này bị thổi phồng. Tập này chỉ dùng
để đo bước KIỂM CHỨNG khi đã trích xuất được; recall trích xuất đo trên câu trả lời
thật của hệ thống (D3).

Chạy từ backend/:  python scripts/citation_eval/01_build_corruption_set.py
"""

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger

from config.settings import BASE_DIR, INDEXES_DIR
from src.verification.citation_index import CitationIndex
from src.verification.extractor import SO_HIEU_PATTERN
from src.verification.normalize import canon_loai, normalize_so_hieu
from src.verification.verifier import CitationVerifier, effect_of

OUT_DIR = BASE_DIR / "data" / "citation_eval"
CACHE_DIR = OUT_DIR / "_cache"
EVOL_DIR = BASE_DIR / "data" / "evol_instruct" / "final"
VARIANTS = ["C0_original", "C1_nonexistent", "C2_neighbor", "C3_far", "C4_expired", "C5_fabricated"]
EXPECTED = {"C0_original": "ok", "C1_nonexistent": "invalid", "C2_neighbor": "invalid",
            "C3_far": "invalid", "C4_expired": "invalid", "C5_fabricated": "unverifiable"}


def dieu_numbers(index: CitationIndex, doc_id: str) -> list[int]:
    rows = index._conn().execute("SELECT dieu FROM articles WHERE doc_id = ?", (doc_id,)).fetchall()
    return sorted({int(m.group()) for (d,) in rows if (m := re.match(r"\d+", d)) and d.isdigit()})


def source_doc(index: CitationIndex, rec: dict):
    """'Nghị định 152/2026/NĐ-CP' + dieu → văn bản trong KB có đúng Điều đó."""
    m = re.search(SO_HIEU_PATTERN, rec.get("document") or "")
    if not m:
        return None
    loai = canon_loai(rec["document"][:m.start()].replace("số", "").strip())
    docs = [d for d in index.docs_by_so_hieu(m.group()) if d.in_kb]
    if loai:
        docs = [d for d in docs if d.loai == loai or {d.loai, loai} <= {"Luật", "Bộ luật"}] or docs
    docs = [d for d in docs if index.get_article(d.doc_id, str(rec["dieu"])) is not None]
    return docs[0] if len(docs) == 1 else None          # mơ hồ → bỏ, không đoán


def replace_span(text: str, start: int, end: int, new: str) -> str:
    return text[:start] + new + text[end:]


def expired_pool(index: CitationIndex) -> dict[str, list[str]]:
    """loai → số hiệu đã hết hiệu lực mà KHÔNG trùng với văn bản còn hiệu lực cùng loại."""
    rows = index._conn().execute(
        "SELECT so_hieu, so_hieu_norm, loai, tinh_trang FROM documents "
        "WHERE so_hieu_norm != '' AND loai IN ('Luật','Bộ luật','Nghị định','Thông tư','Nghị quyết','Quyết định')"
    ).fetchall()
    status: dict[tuple, set] = {}
    raw: dict[tuple, str] = {}
    for so, key, loai, tt in rows:
        status.setdefault((key, loai), set()).add(effect_of(tt))
        raw[(key, loai)] = so
    pool: dict[str, list[str]] = {}
    for (key, loai), effs in status.items():
        if effs == {"expired"} and re.fullmatch(r"\d+/\d{4}/[A-Z0-9Đ\-]+", raw[(key, loai)]):
            pool.setdefault(loai, []).append(raw[(key, loai)])
    for v in pool.values():
        v.sort()
    return pool


def fabricated_so_hieu(index: CitationIndex, real: str, rng: random.Random) -> str:
    m = re.match(r"(\d+)/(\d{4})/(.+)", real)
    suffix, year = (m.group(3), m.group(2)) if m else ("NĐ-CP", "2015")
    for _ in range(200):
        cand = f"{rng.randint(300, 999)}/{year}/{suffix}"
        if not index.docs_by_so_hieu(cand):
            return cand
    raise RuntimeError("không sinh được số hiệu giả")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dev-frac", type=float, default=0.5)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    index = CitationIndex(INDEXES_DIR / "citation_index.sqlite")
    verifier = CitationVerifier(index, scorer=None)
    pool = expired_pool(index)
    logger.info("Văn bản hết hiệu lực dùng cho C4: " + ", ".join(f"{k}={len(v)}" for k, v in pool.items()))

    records = []
    for split in ("train", "val"):
        records += json.loads((EVOL_DIR / f"{split}.json").read_text(encoding="utf-8"))

    skip = Counter()
    pairs = []
    for rec in records:
        doc = source_doc(index, rec)
        if doc is None:
            skip["source_not_in_kb_or_ambiguous"] += 1
            continue
        dieu = str(rec["dieu"])
        answer = rec["output"]
        cites = verifier.extractor.extract(answer)
        report = verifier.verify(answer)
        target = None
        for c, r in zip(cites, report.citations):
            if (r.doc_id == doc.doc_id and r.dieu == dieu and r.resolution in ("so_hieu", "alias")
                    and r.status in ("valid", "warning") and c.ref is not None
                    and sum(1 for x in cites if x.group == c.group) == 1
                    and c.substantive and len(c.claim) >= verifier.th.min_claim_chars):
                target = c
                break
        if target is None:
            skip["no_clean_target_citation"] += 1
            continue

        nums = dieu_numbers(index, doc.doc_id)
        n = int(re.match(r"\d+", dieu).group())
        art_m = re.search(rf"(?i)(điều\s+){re.escape(dieu)}(?![\w/])", answer[target.start:target.end])
        # vị trí của riêng con số N trong "Điều N" của trích dẫn đích
        a0 = target.start + art_m.start() + len(art_m.group(1))
        a1 = target.start + art_m.end()

        def with_dieu(new_n: int) -> str:
            return replace_span(answer, a0, a1, str(new_n))

        def has_khoan(new_n: int) -> bool:
            if not target.khoan:
                return True
            art = index.get_article(doc.doc_id, str(new_n)) or ""
            return re.search(rf"(?m)^\s*{target.khoan}\.\s", art) is not None

        variants = {"C0_original": answer, "C1_nonexistent": with_dieu(max(nums) + rng.randint(3, 30))}
        near = [n + d for d in (1, -1, 2, -2, 3, -3) if (n + d) in nums and has_khoan(n + d)]
        if near:
            variants["C2_neighbor"] = with_dieu(near[0])
        far = [x for x in nums if abs(x - n) >= 20 and has_khoan(x)]
        if far:
            variants["C3_far"] = with_dieu(rng.choice(far))
        ref = target.ref
        if pool.get(doc.loai):
            variants["C4_expired"] = replace_span(answer, ref.start, ref.end,
                                                  f"{doc.loai} số {rng.choice(pool[doc.loai])}")
        variants["C5_fabricated"] = replace_span(answer, ref.start, ref.end,
                                                 f"{doc.loai} số {fabricated_so_hieu(index, doc.so_hieu, rng)}")

        pairs.append({"rec_id": rec["id"], "src_doc_id": doc.doc_id, "src_so_hieu": doc.so_hieu,
                      "src_loai": doc.loai, "src_dieu": dieu, "target_start": target.start,
                      "target_text": target.text, "khoan": target.khoan, "has_quote": bool(target.quote),
                      "variants": variants})

    # group split theo văn bản nguồn
    groups = sorted({p["src_doc_id"] for p in pairs})
    rng.shuffle(groups)
    dev_groups = set(groups[:int(len(groups) * args.dev_frac)])

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / "corruption_set.jsonl"
    counts = Counter()
    with open(out, "w", encoding="utf-8") as f:
        for p in pairs:
            split = "dev" if p["src_doc_id"] in dev_groups else "test"
            for v, text in p.pop("variants").items():
                counts[(split, v)] += 1
                f.write(json.dumps({**p, "split": split, "variant": v, "expected": EXPECTED[v],
                                    "answer": text}, ensure_ascii=False) + "\n")

    summary = {
        "n_source_records": len(records),
        "n_pairs": len(pairs),
        "skipped": dict(skip),
        "n_source_docs": len(groups),
        "n_dev_docs": len(dev_groups),
        "counts": {f"{s}/{v}": counts[(s, v)] for s in ("dev", "test") for v in VARIANTS},
        "seed": args.seed,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "corruption_set_stats.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                      encoding="utf-8")
    logger.info(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
