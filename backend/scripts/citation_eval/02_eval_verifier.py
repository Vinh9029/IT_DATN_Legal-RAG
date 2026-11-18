"""
D2 — Đo độ chính xác của Citation Verifier trên bộ test làm sai có kiểm soát (D1).

Ba lệnh, chạy theo thứ tự:
    score   chấm cross-encoder cho trích dẫn đích (cache, chạy tiếp được nếu dừng giữa chừng)
    report  chọn ngưỡng trên DEV, báo cáo trên TEST (một lần), kèm ablation và bootstrap CI

Logic quyết định dùng ĐÚNG hàm của production (`apply_ce_score`, `final_status`);
chỉ khác là chỉ chấm cross-encoder cho trích dẫn đích thay vì mọi trích dẫn trong
câu trả lời (CPU chậm; các trích dẫn khác không ảnh hưởng tới nhãn của trích dẫn đích).

Ablation (trên TEST):
    A_structure  chỉ tồn tại + hiệu lực (bỏ bước nội dung)
    B_quote      A + khớp đoạn trích nguyên văn
    C_full       B + cross-encoder  (= cấu hình production)

Chạy từ backend/:
    python scripts/citation_eval/02_eval_verifier.py score
    python scripts/citation_eval/02_eval_verifier.py report
"""

import argparse
import copy
import json
import random
import sys
import time
from typing import Optional
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger

from config.settings import BASE_DIR, INDEXES_DIR
from src.verification.citation_index import CitationIndex
from src.verification.verifier import (
    CitationVerifier, CrossEncoderScorer, Thresholds, apply_ce_score, article_segments, final_status,
)

OUT_DIR = BASE_DIR / "data" / "citation_eval"
CACHE_DIR = OUT_DIR / "_cache"
SET_PATH = CACHE_DIR / "corruption_set.jsonl"
CE_CACHE = CACHE_DIR / "ce_scores.jsonl"
STRUCT_CACHE = CACHE_DIR / "structural.jsonl"
RESULT_PATH = OUT_DIR / "verifier_eval.json"
VARIANTS = ["C0_original", "C1_nonexistent", "C2_neighbor", "C3_far", "C4_expired", "C5_fabricated"]


def load_rows() -> list[dict]:
    return [json.loads(l) for l in open(SET_PATH, encoding="utf-8")]


def target_result(verifier: CitationVerifier, row: dict):
    """Kết quả của trích dẫn đích (đã kiểm tồn tại + hiệu lực + đoạn trích; chưa chấm CE)."""
    rep = verifier.verify(row["answer"])
    cands = [c for c in rep.citations if c.start == row["target_start"]]
    return cands[0] if cands else None


def ce_key(r) -> str:
    return json.dumps([r.claim, r.doc_id, r.dieu, r.khoan], ensure_ascii=False)


def cmd_structural(verifier: CitationVerifier, rows: list[dict]) -> list[dict]:
    """Bước không cần model — chạy lại mỗi lần (vài giây), lưu để xem lỗi."""
    out = []
    for row in rows:
        r = target_result(verifier, row)
        out.append({"row": row, "res": r})
    lost = sum(1 for o in out if o["res"] is None)
    if lost:
        logger.warning(f"{lost} biến thể không tìm lại được trích dẫn đích")
    return out


class HFScorer:
    """
    Chỉ cho đánh giá: bge-reranker-large qua `transformers` trên GPU (venv chính chỉ có torch
    CPU, 3,4s/trích dẫn). Cùng phép tính với FlagReranker.compute_score(normalize=True):
    logit của cặp (truy vấn, đoạn), max_length=512, rồi sigmoid. Lệnh `check` đo độ lệch
    so với điểm FlagReranker/CPU đã cache trước khi dùng.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-large"):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.tok = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name).to(self.dev).eval()
        if self.dev == "cuda":
            self.model.half()

    def __call__(self, pairs, bs: int = 32):
        out = []
        with self.torch.no_grad():
            for i in range(0, len(pairs), bs):
                a, b = zip(*pairs[i:i + bs])
                enc = self.tok(list(a), list(b), padding=True, truncation=True, max_length=512,
                               return_tensors="pt").to(self.dev)
                logits = self.model(**enc).logits.view(-1).float()
                out += self.torch.sigmoid(logits).tolist()
        return out


def make_scorer(backend: str):
    return HFScorer() if backend == "hf" else CrossEncoderScorer.load()


def cmd_check(args):
    """So scorer HF/GPU với điểm FlagReranker/CPU đã có trong cache."""
    index = CitationIndex(INDEXES_DIR / "citation_index.sqlite")
    ref = [json.loads(l) for l in open(CE_CACHE, encoding="utf-8")][:args.n]
    scorer = HFScorer()
    diffs = []
    for d in ref:
        claim, doc_id, dieu, khoan = json.loads(d["key"])
        segs = article_segments(index.get_article(doc_id, dieu), khoan)
        s = max(scorer([(claim, x) for x in segs]))
        diffs.append(abs(s - d["score"]))
    diffs.sort()
    logger.info(f"HF/{scorer.dev} so với FlagReranker/CPU trên {len(diffs)} trích dẫn: "
                f"max |Δ|={diffs[-1]:.4f}, median={diffs[len(diffs) // 2]:.4f}")


def cmd_score(args):
    index = CitationIndex(INDEXES_DIR / "citation_index.sqlite")
    verifier = CitationVerifier(index, scorer=None)
    rows = load_rows()
    done = {}
    if CE_CACHE.exists():
        for l in open(CE_CACHE, encoding="utf-8"):
            d = json.loads(l)
            done[d["key"]] = d["score"]
    todo = {}
    for o in cmd_structural(verifier, rows):
        r = o["res"]
        if (r is None or r.exists is not True or not r.substantive
                or len(r.claim) < verifier.th.min_claim_chars):
            continue
        k = ce_key(r)
        if k not in done and k not in todo:
            todo[k] = (r.claim, article_segments(index.get_article(r.doc_id, r.dieu), r.khoan))
    logger.info(f"CE: {len(done)} đã có, {len(todo)} cần chấm")
    if not todo:
        return
    scorer = make_scorer(args.backend)
    t0, keys = time.time(), list(todo)
    with open(CE_CACHE, "a", encoding="utf-8") as f:
        for i in range(0, len(keys), args.batch):
            batch = keys[i:i + args.batch]
            pairs, owner = [], []
            for k in batch:
                claim, segs = todo[k]
                pairs += [(claim, s) for s in segs]
                owner += [k] * len(segs)
            scores = scorer(pairs)
            best = defaultdict(float)
            for k, s in zip(owner, scores):
                best[k] = max(best[k], s)
            for k in batch:
                f.write(json.dumps({"key": k, "score": round(best[k], 6)}, ensure_ascii=False) + "\n")
            f.flush()
            n = i + len(batch)
            logger.info(f"  {n}/{len(keys)} | {(time.time() - t0) / n:.2f}s/trích dẫn")


# ── báo cáo ───────────────────────────────────────────────────
def decide(r, ce: float | None, th: Thresholds, use_quote: bool, use_ce: bool) -> str:
    r = copy.deepcopy(r)
    if not use_quote and r.quote_score is not None:
        r.content, r.quote_score = None, None
        r.reasons = [x for x in r.reasons if x != "quote_mismatch"]
    if use_ce and r.content is None and ce is not None:
        apply_ce_score(r, ce, th)
    return final_status(r)


def outcome(variant: str, status: str) -> bool:
    """Verifier xử lý ĐÚNG biến thể này không."""
    if variant == "C0_original":
        return status not in ("invalid", "unverifiable")
    if variant == "C5_fabricated":
        return status in ("invalid", "unverifiable")
    return status == "invalid"


def auc(pos: list[float], neg: list[float]) -> float | None:
    """P(điểm Điều đúng > điểm Điều sai) — Mann-Whitney, hoà tính 0,5."""
    if not pos or not neg:
        return None
    neg_sorted = sorted(neg)
    import bisect
    total = 0.0
    for p in pos:
        lo, hi = bisect.bisect_left(neg_sorted, p), bisect.bisect_right(neg_sorted, p)
        total += lo + 0.5 * (hi - lo)
    return round(total / (len(pos) * len(neg)), 4)


MAX_FALSE_ALARM = 0.05


def pick_threshold(items: list[tuple[str, float]], max_fa: Optional[float] = None) -> dict:
    """
    Ngưỡng một mức (ce_low = ce_high): C0 ≥ τ là đúng, C2∪C3 < τ là bắt được.
    max_fa=None  → tối đa balanced accuracy (báo nhầm và bỏ sót nặng như nhau).
    max_fa=0.05  → tối đa khả năng bắt lỗi với điều kiện báo nhầm trên dev ≤ 5%. Đây là điểm
                   vận hành của production: báo nhầm làm trích dẫn đúng bị gắn cờ đỏ và kích
                   hoạt viết lại câu trả lời, đắt hơn bỏ sót một lỗi.
    """
    ok = [s for v, s in items if v == "C0_original"]
    bad = [s for v, s in items if v in ("C2_neighbor", "C3_far")]
    best = None
    for tau in sorted({round(s, 4) for _, s in items} | {0.5}):
        tpr = sum(s < tau for s in bad) / len(bad)
        tnr = sum(s >= tau for s in ok) / len(ok)
        if max_fa is not None and 1 - tnr > max_fa:
            continue
        obj = tpr if max_fa is not None else (tpr + tnr) / 2
        if best is None or obj > best["_obj"]:
            best = {"tau": tau, "_obj": obj, "balanced_acc": round((tpr + tnr) / 2, 4),
                    "tpr_bad": round(tpr, 4), "tnr_ok": round(tnr, 4)}
    best.pop("_obj")
    best["criterion"] = f"false_alarm<= {max_fa}" if max_fa is not None else "balanced_accuracy"
    return best


def bootstrap_ci(per_group: dict, n_resamples: int = 2000, seed: int = 42) -> tuple[float, float]:
    """CI 95% cho tỉ lệ đúng, resample theo VĂN BẢN NGUỒN (các biến thể cùng văn bản không độc lập)."""
    rng = random.Random(seed)
    groups = list(per_group)
    vals = []
    for _ in range(n_resamples):
        hit = tot = 0
        for g in (rng.choice(groups) for _ in groups):
            h, t = per_group[g]
            hit, tot = hit + h, tot + t
        vals.append(hit / tot if tot else 0)
    vals.sort()
    return round(vals[int(0.025 * n_resamples)], 4), round(vals[int(0.975 * n_resamples)], 4)


def cmd_report(args):
    index = CitationIndex(INDEXES_DIR / "citation_index.sqlite")
    verifier = CitationVerifier(index, scorer=None)
    rows = load_rows()
    ce = {}
    for l in open(CE_CACHE, encoding="utf-8"):
        d = json.loads(l)
        ce[d["key"]] = d["score"]
    data = cmd_structural(verifier, rows)
    for o in data:
        r = o["res"]
        o["ce"] = ce.get(ce_key(r)) if r is not None else None

    # 1) ngưỡng trên DEV — chỉ các mẫu thực sự tới bước CE (không có đoạn trích quyết định)
    dev_items = [(o["row"]["variant"], o["ce"]) for o in data
                 if o["row"]["split"] == "dev" and o["ce"] is not None and o["res"].content is None
                 and o["row"]["variant"] in ("C0_original", "C2_neighbor", "C3_far")]
    th_pick = pick_threshold(dev_items, max_fa=MAX_FALSE_ALARM)       # điểm vận hành production
    th_bal = pick_threshold(dev_items)                                 # báo cáo kèm để so sánh
    th = Thresholds(ce_high=th_pick["tau"], ce_low=th_pick["tau"])
    th_b = Thresholds(ce_high=th_bal["tau"], ce_low=th_bal["tau"])
    logger.info(f"Ngưỡng chọn trên dev: {th_pick} | balanced: {th_bal}")

    # 2) AUC của cross-encoder (dev và test) — tách khỏi việc chọn ngưỡng
    aucs = {}
    for split in ("dev", "test"):
        s = defaultdict(list)
        for o in data:
            if o["row"]["split"] == split and o["ce"] is not None:
                s[o["row"]["variant"]].append(o["ce"])
        aucs[split] = {"C0_vs_C2_neighbor": auc(s["C0_original"], s["C2_neighbor"]),
                       "C0_vs_C3_far": auc(s["C0_original"], s["C3_far"])}

    # 3) TEST — ba cấu hình ablation
    configs = {"A_structure": (False, False, th), "B_quote": (True, False, th),
               "C_full": (True, True, th), "C_full_balanced_threshold": (True, True, th_b)}
    test = [o for o in data if o["row"]["split"] == "test"]
    report = {}
    for name, (use_q, use_ce, th) in configs.items():
        per_var = {}
        for v in VARIANTS:
            items = [o for o in test if o["row"]["variant"] == v]
            dist, groups = Counter(), defaultdict(lambda: [0, 0])
            for o in items:
                st = "lost" if o["res"] is None else decide(o["res"], o["ce"], th, use_q, use_ce)
                dist[st] += 1
                g = groups[o["row"]["src_doc_id"]]
                g[0] += outcome(v, st)
                g[1] += 1
            n = len(items)
            acc = sum(h for h, _ in groups.values()) / n if n else None
            per_var[v] = {"n": n, "correct_rate": round(acc, 4) if acc is not None else None,
                          "ci95": bootstrap_ci(groups) if n else None,
                          "status_dist": dict(dist)}
        # gộp nhị phân: phát hiện trích dẫn sai (C1–C4 dương, C0 âm)
        tp = sum(1 for o in test if o["row"]["variant"] in ("C1_nonexistent", "C2_neighbor", "C3_far", "C4_expired")
                 and o["res"] is not None and decide(o["res"], o["ce"], th, use_q, use_ce) == "invalid")
        pos = sum(1 for o in test if o["row"]["variant"] in ("C1_nonexistent", "C2_neighbor", "C3_far", "C4_expired"))
        fp = sum(1 for o in test if o["row"]["variant"] == "C0_original"
                 and o["res"] is not None and decide(o["res"], o["ce"], th, use_q, use_ce) == "invalid")
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / pos if pos else None
        f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
        report[name] = {"per_variant": per_var,
                        "invalid_detection": {"precision": round(prec, 4) if prec else None,
                                              "recall": round(rec, 4) if rec else None,
                                              "f1": round(f1, 4) if f1 else None,
                                              "note": "C1–C4 dương, C0 âm; C5 tính riêng (kỳ vọng unverifiable)"}}

    stats = json.loads((OUT_DIR / "corruption_set_stats.json").read_text(encoding="utf-8"))
    result = {
        "dataset": {k: stats[k] for k in ("n_pairs", "n_source_docs", "n_dev_docs", "counts", "seed")},
        "threshold_from_dev": th_pick,
        "threshold_balanced_from_dev": th_bal,
        "ce_auc": aucs,
        "test": report,
        "notes": [
            "Ngưỡng cross-encoder chọn trên dev (group split theo văn bản nguồn), test chạy một lần.",
            "Production dùng điểm vận hành báo nhầm ≤5% trên dev (threshold_from_dev); điểm "
            "balanced accuracy báo cáo kèm (C_full_balanced_threshold). Tiêu chí ≤5% được chọn sau "
            "khi thấy mức báo cờ cao trên câu trả lời thật (D3), không dựa trên số test.",
            "Phiên bản 2 (2026-11-18): bỏ kiểm nội dung với dòng chỉ liệt kê nguồn + điểm cụm "
            "'Điều X và Điều Y' lấy max — sửa lỗi xử lý phát hiện khi chạy D3.",
            "Chỉ chấm cross-encoder cho trích dẫn đích; logic quyết định dùng chung hàm với production.",
            "Dữ liệu Evol đã lọc bằng regex trích Điều → không đo recall trích xuất ở đây (xem D3).",
        ],
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"→ {RESULT_PATH.relative_to(BASE_DIR).as_posix()}")
    print(json.dumps({"threshold": th_pick, "ce_auc": aucs,
                      **{k: {v: (x["correct_rate"], x["ci95"]) for v, x in r["per_variant"].items()}
                         | {"detection": r["invalid_detection"]} for k, r in report.items()}},
                     ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--batch", type=int, default=16, help="số trích dẫn mỗi lô")
    s.add_argument("--backend", choices=["flag", "hf"], default="flag",
                   help="flag = FlagReranker như production; hf = transformers trên GPU (đã kiểm bằng `check`)")
    c = sub.add_parser("check")
    c.add_argument("--n", type=int, default=32)
    sub.add_parser("report")
    args = ap.parse_args()
    {"score": cmd_score, "check": cmd_check, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
