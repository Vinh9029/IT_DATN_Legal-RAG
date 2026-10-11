"""
Script 15: Routing classifier nên phân loại câu GỐC hay câu ĐÃ VIẾT LẠI?

─── Vì sao cần script này ───

Ở Stage 1 (`src/retrieval/query_evolver.py`), câu hỏi của người dùng được LLM
viết lại theo IRAC ("bổ sung tên Luật", "làm rõ tình huống cụ thể") rồi MỚI đưa
vào RoutingClassifier. Nhưng classifier học trên câu hỏi gốc trong
`data/qa_pairs/final/`. Prompt viết lại cố tình thêm tên luật và tình huống —
đúng hai tín hiệu mà dataset gắn với nhãn narrow — nên nghi là câu broad sau khi
viết lại sẽ bị đẩy sang narrow.

Script đo trực tiếp: lấy mẫu test cân bằng nhãn × nhánh, viết lại bằng ĐÚNG
prompt và model production, rồi so accuracy của classifier trên câu gốc với
trên câu đã viết lại. Bản viết lại được cache để chạy lại không tốn LLM.

─── Cách dùng ───

    cd backend/
    lms load meta-llama-3.1-8b-instruct      # model trong LLM_MODEL_NAME
    python evol_instruct/scripts/15_eval_routing_on_evolved.py
    python evol_instruct/scripts/15_eval_routing_on_evolved.py --per-cell 50
"""

import argparse
import collections
import importlib.util
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from config.settings import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME

ROOT = Path(__file__).resolve().parents[2]          # backend/

# Nạp riêng file query_evolver.py: `import src.retrieval.query_evolver` sẽ chạy
# src/retrieval/__init__.py → kéo cả qdrant/neo4j/reranker, không cần cho phép đo này.
_spec = importlib.util.spec_from_file_location(
    "query_evolver", ROOT / "src" / "retrieval" / "query_evolver.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
QueryEvolver = _mod.QueryEvolver

TEST_PATH = ROOT / "data" / "qa_pairs" / "final" / "test.json"
MODEL_DIR = ROOT / "models" / "routing_classifier"
CACHE_PATH = MODEL_DIR / "evolved_cache.jsonl"
REPORT_PATH = MODEL_DIR / "eval_evolved.json"


def nhan(r: dict) -> str:
    return r.get("final_label") or r.get("specificity")


def nhanh(r: dict) -> str:
    return (r.get("metadata") or {}).get("narrow_mode", "?")


def lay_mau(test: list[dict], per_cell: int, seed: int) -> list[dict]:
    """Mỗi ô (nhãn × nhánh) lấy per_cell câu — tránh số gộp bị một ô kéo lệch."""
    o = collections.defaultdict(list)
    for r in test:
        o[(nhan(r), nhanh(r))].append(r)
    rng = random.Random(seed)
    mau = []
    for k in sorted(o):
        mau += rng.sample(o[k], min(per_cell, len(o[k])))
    return mau


def doc_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    out = {}
    for line in CACHE_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            if d.get("model") == LLM_MODEL_NAME:
                out[d["item_id"]] = d["evolved"]
    return out


def acc(rows: list[dict], key: str) -> dict:
    def a(rs):
        return round(sum(r[key] == r["label"] for r in rs) / len(rs), 4) if rs else None
    out = {"tong": a(rows), "n": len(rows)}
    for lab in ("broad", "narrow"):
        out[f"nhan_{lab}"] = a([r for r in rows if r["label"] == lab])
    for b in sorted({r["branch"] for r in rows}):
        out[f"nhanh_{b}"] = a([r for r in rows if r["branch"] == b])
    out["ty_le_du_doan_narrow"] = round(sum(r[key] == "narrow" for r in rows) / len(rows), 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-cell", type=int, default=25,
                    help="Số câu mỗi ô nhãn × nhánh (4 ô)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    test = json.loads(TEST_PATH.read_text(encoding="utf-8"))
    mau = lay_mau(test, args.per_cell, args.seed)
    logger.info(f"Mẫu: {len(mau)} câu | LLM viết lại: {LLM_MODEL_NAME}")

    evolver = QueryEvolver(base_url=LLM_BASE_URL, api_key=LLM_API_KEY,
                           model=LLM_MODEL_NAME, temperature=0.3, model_dir=MODEL_DIR)
    if not evolver.classifier.is_ready:
        logger.error("Chưa có adapter — chạy script 13 trước.")
        sys.exit(1)

    cache = doc_cache()
    n_moi = n_loi = 0
    with CACHE_PATH.open("a", encoding="utf-8") as f:
        for i, r in enumerate(mau, 1):
            if r["item_id"] in cache:
                continue
            ev = evolver._rewrite(r["question"])
            if ev == r["question"]:
                # _rewrite trả nguyên câu khi LLM lỗi — không cache để lần sau thử lại.
                n_loi += 1
                continue
            cache[r["item_id"]] = ev
            f.write(json.dumps({"item_id": r["item_id"], "model": LLM_MODEL_NAME,
                                "evolved": ev}, ensure_ascii=False) + "\n")
            f.flush()
            n_moi += 1
            if i % 20 == 0:
                logger.info(f"  viết lại {i}/{len(mau)}")
    logger.info(f"Viết lại mới: {n_moi} | lỗi LLM: {n_loi} | từ cache: {len(mau) - n_moi - n_loi}")

    mau = [r for r in mau if r["item_id"] in cache]
    goc = evolver.classifier.predict_batch([r["question"] for r in mau])
    moi = evolver.classifier.predict_batch([cache[r["item_id"]] for r in mau])
    rows = [{"item_id": r["item_id"], "label": nhan(r), "branch": nhanh(r),
             "pred_goc": g, "pred_evolved": m,
             "question": r["question"], "evolved": cache[r["item_id"]]}
            for r, g, m in zip(mau, goc, moi)]

    lat = collections.Counter(f"{x['pred_goc']}→{x['pred_evolved']}"
                              for x in rows if x["pred_goc"] != x["pred_evolved"])
    report = {
        "llm_viet_lai": LLM_MODEL_NAME,
        "per_cell": args.per_cell,
        "cau_goc": acc(rows, "pred_goc"),
        "cau_evolved": acc(rows, "pred_evolved"),
        "doi_nhan": dict(lat),
        "do_dai_tu_tb": {
            "goc": round(sum(len(x["question"].split()) for x in rows) / len(rows), 1),
            "evolved": round(sum(len(x["evolved"].split()) for x in rows) / len(rows), 1),
        },
        "vi_du_doi_nhan": [x for x in rows if x["pred_goc"] != x["pred_evolved"]][:8],
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for k in ("cau_goc", "cau_evolved"):
        logger.info(f"{k:12s}: {report[k]}")
    logger.info(f"Đổi nhãn sau khi viết lại: {dict(lat)}")
    logger.info(f"Độ dài TB (từ): {report['do_dai_tu_tb']}")


if __name__ == "__main__":
    main()
