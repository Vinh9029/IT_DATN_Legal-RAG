"""
D3 — Citation Verification trên câu trả lời THẬT của hệ thống.

Dựng lại đúng top-5 của production cho các câu hỏi trong tập TEST của dataset QA
(cache của scripts 17: candidates dense/BM25 + điểm rerank; pool 10 narrow / 20
broad theo routing trên câu đã viết lại, rerank, K=5) → sinh câu trả lời bằng
LegalGenerator thật (LM Studio, cùng prompt/nhiệt độ production) → chạy Stage 6
qua đúng hàm production `run_citation_stage` (kiểm chứng + sửa một lần).

Lệnh (chạy theo thứ tự, từ backend/):
    python scripts/citation_eval/03_real_answers.py contexts --n 200
    python scripts/citation_eval/03_real_answers.py generate
    python scripts/citation_eval/03_real_answers.py verify       # cần verifier_eval.json (ngưỡng từ D2)
    python scripts/citation_eval/03_real_answers.py annotate     # xuất phiếu gán nhãn tay
    python scripts/citation_eval/03_real_answers.py agreement    # sau khi 2 người điền phiếu

Mỗi câu hỏi gọi `clear_history()` trước khi sinh: history của LegalGenerator dùng
chung giữa các request, để nguyên thì câu sau bị lẫn ngữ cảnh câu trước.
"""

import argparse
import csv
import json
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger

from config.settings import (
    ANSWER_TEMPERATURE, BASE_DIR, INDEXES_DIR, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME, MAX_TOKENS,
    PROCESSED_DATA_DIR,
)

OUT_DIR = BASE_DIR / "data" / "citation_eval"
CACHE_DIR = OUT_DIR / "_cache"
EVAL_CACHE = BASE_DIR / "data" / "qa_pairs" / "eval" / "_cache"
FINAL_DIR = BASE_DIR / "data" / "qa_pairs" / "final"
CTX_PATH = CACHE_DIR / "real_contexts.jsonl"
ANS_PATH = CACHE_DIR / "real_answers.jsonl"
VER_PATH = CACHE_DIR / "real_verified.jsonl"
SUMMARY_PATH = OUT_DIR / "real_answers_eval.json"
LAT_PATH = CACHE_DIR / "latency_verify_cpu.json"
SHEET_DIR = OUT_DIR / "annotation"
K, RRF_K, POOL = 5, 60, {"narrow": 10, "broad": 20}


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


def rrf_pool(dense, bm25, n):
    """Giống 17_eval_retrieval.rrf_pool (= rrf_fusion production với top_k=n)."""
    score = {}
    for lst in (dense[:n], bm25[:n]):
        for rank, cid in enumerate(lst):
            score[cid] = score.get(cid, 0.0) + 1 / (RRF_K + rank + 1)
    return sorted(score, key=score.get, reverse=True)[:n]


# ── contexts ──────────────────────────────────────────────────
def cmd_contexts(args):
    items = json.loads((FINAL_DIR / "test.json").read_text(encoding="utf-8"))
    cands = {r["item_id"]: r for r in read_jsonl(EVAL_CACHE / "candidates.jsonl")}
    rerank = {r["item_id"]: r["scores"] for r in read_jsonl(EVAL_CACHE / "rerank.jsonl")}
    routing = json.loads((EVAL_CACHE / "routing.json").read_text(encoding="utf-8"))
    items = [r for r in items if r["item_id"] in cands and r["item_id"] in rerank]

    rng = random.Random(args.seed)
    by_label = defaultdict(list)
    for r in items:
        by_label[r.get("final_label") or r.get("specificity")].append(r)
    sample = []
    for lab in sorted(by_label):                       # chia đều broad/narrow
        rows = sorted(by_label[lab], key=lambda r: r["item_id"])
        sample += rng.sample(rows, min(len(rows), args.n // len(by_label)))

    plan = []
    for r in sample:
        route = (routing.get(r["item_id"]) or {}).get("q_tilde") or r.get("final_label")
        c = cands[r["item_id"]]
        pool = rrf_pool(c["dense"], c["bm25"], POOL[route])
        s = rerank[r["item_id"]]
        top = sorted(pool, key=lambda x: s.get(x, -1e9), reverse=True)[:K]
        plan.append({"item_id": r["item_id"], "question": r["question"], "label": r.get("final_label"),
                     "route": route, "top": [(cid, s.get(cid)) for cid in top]})

    need = {cid for p in plan for cid, _ in p["top"]}
    chunks = {}
    with open(PROCESSED_DATA_DIR / "chunks" / "chunks.jsonl", encoding="utf-8") as f:
        for line in f:
            j = line.find('"chunk_id": "')
            cid = line[j + 13:line.find('"', j + 13)]
            if cid in need:
                chunks[cid] = json.loads(line)          # trùng chunk_id: bản sau đè, như production
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CTX_PATH, "w", encoding="utf-8") as f:
        for p in plan:
            ctx = []
            for cid, sc in p["top"]:
                ch = dict(chunks.get(cid) or {"chunk_id": cid, "doc_id": cid.split("_")[0], "content": ""})
                ch["rerank_score"] = 1 / (1 + math.exp(-sc)) if sc is not None else 0.0   # normalize=True
                ctx.append(ch)
            f.write(json.dumps({**{k: p[k] for k in ("item_id", "question", "label", "route")},
                                "chunks": ctx}, ensure_ascii=False) + "\n")
    logger.info(f"{len(plan)} câu → {CTX_PATH.relative_to(BASE_DIR).as_posix()} | "
                f"thiếu chunk: {len(need - set(chunks))}")


# ── generate ──────────────────────────────────────────────────
def make_generator():
    from src.retrieval.generator import LegalGenerator
    return LegalGenerator(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, model=LLM_MODEL_NAME,
                          temperature=ANSWER_TEMPERATURE, max_tokens=MAX_TOKENS,
                          gemini_api_key="", gemini_model=None, timeout=300.0)


def cmd_generate(args):
    os.environ["GEMINI_API_KEY"] = ""                  # đo đúng generator LM Studio của production
    gen = make_generator()
    done = {r["item_id"] for r in read_jsonl(ANS_PATH)}
    rows = [r for r in read_jsonl(CTX_PATH) if r["item_id"] not in done]
    logger.info(f"Sinh {len(rows)} câu (đã có {len(done)})")
    with open(ANS_PATH, "a", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            gen.clear_history()
            t0 = time.time()
            ans = gen.generate(query=r["question"], chunks=r["chunks"])
            f.write(json.dumps({"item_id": r["item_id"], "answer": ans,
                                "gen_seconds": round(time.time() - t0, 1)}, ensure_ascii=False) + "\n")
            f.flush()
            logger.info(f"  {i}/{len(rows)} | {time.time() - t0:.1f}s | {len(ans or '')} ký tự")


# ── verify (Stage 6 production) ───────────────────────────────
def cmd_verify(args):
    th = json.loads((OUT_DIR / "verifier_eval.json").read_text(encoding="utf-8"))["threshold_from_dev"]["tau"]
    os.environ["CITATION_CE_LOW"] = os.environ["CITATION_CE_HIGH"] = str(th)
    os.environ["CITATION_VERIFY"] = os.environ["CITATION_REPAIR"] = "1"
    os.environ["GEMINI_API_KEY"] = ""

    import src.verification.stage as stage
    from src.verification.citation_index import CitationIndex
    from src.verification.verifier import CitationVerifier, CrossEncoderScorer

    ce = CrossEncoderScorer.load()
    memo: dict = {}

    def cached_scorer(pairs):
        """Báo cáo trước-khi-sửa và đường production chấm cùng cặp → chấm một lần."""
        todo = [p for p in dict.fromkeys(pairs) if p not in memo]
        for p, s in zip(todo, ce(todo)):
            memo[p] = s
        return [memo[p] for p in pairs]

    verifier = CitationVerifier(CitationIndex(INDEXES_DIR / "citation_index.sqlite"), scorer=cached_scorer)
    stage._verifier = verifier
    gen = make_generator()

    ctx = {r["item_id"]: r for r in read_jsonl(CTX_PATH)}
    done = {r["item_id"] for r in read_jsonl(VER_PATH)}
    rows = [r for r in read_jsonl(ANS_PATH) if r["item_id"] not in done and r["answer"]]
    if args.limit:
        rows = rows[:args.limit]                        # chạy theo mẻ, ghi nối tiếp
    logger.info(f"Kiểm chứng {len(rows)} câu (τ={th}, đã có {len(done)})")
    with open(VER_PATH, "a", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            c = ctx[r["item_id"]]
            gen.clear_history()
            pre = verifier.verify(r["answer"], c["chunks"]).to_dict()   # báo cáo của bản GỐC
            t0 = time.time()
            out = stage.run_citation_stage(c["question"], r["answer"], c["chunks"], generator=gen)
            f.write(json.dumps({"item_id": r["item_id"], "pre_report": pre, "stage": out,
                                "stage_seconds": round(time.time() - t0, 2)}, ensure_ascii=False) + "\n")
            f.flush()
            rep = out["report"] if out else {}
            logger.info(f"  {i}/{len(rows)} | {time.time() - t0:.1f}s | {rep.get('counts')} | "
                        f"repair={rep.get('repair') and rep['repair'].get('accepted')}")
    summarize()


def cmd_latency(args):
    """Độ trễ kiểm chứng KHÔNG cache, cross-encoder CPU như production (bước sửa đo riêng)."""
    from src.verification.citation_index import CitationIndex
    from src.verification.verifier import CitationVerifier, CrossEncoderScorer
    th = json.loads((OUT_DIR / "verifier_eval.json").read_text(encoding="utf-8"))["threshold_from_dev"]["tau"]
    os.environ["CITATION_CE_LOW"] = os.environ["CITATION_CE_HIGH"] = str(th)
    v = CitationVerifier(CitationIndex(INDEXES_DIR / "citation_index.sqlite"), scorer=CrossEncoderScorer.load())
    ctx = {r["item_id"]: r for r in read_jsonl(CTX_PATH)}
    rows = [r for r in read_jsonl(ANS_PATH) if r["answer"]]
    rows = random.Random(args.seed).sample(rows, min(args.n, len(rows)))
    secs, ncit = [], []
    for r in rows:
        t0 = time.time()
        rep = v.verify(r["answer"], ctx[r["item_id"]]["chunks"])
        secs.append(round(time.time() - t0, 3))
        ncit.append(len(rep.citations))
    s = sorted(secs)
    out = {"n_answers": len(s), "device": "cpu", "median": s[len(s) // 2], "p90": s[int(len(s) * 0.9)],
           "max": s[-1], "seconds_per_citation": round(sum(secs) / max(1, sum(ncit)), 3)}
    LAT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    logger.info(out)
    summarize()


def summarize():
    ver = read_jsonl(VER_PATH)
    ans = {r["item_id"]: r for r in read_jsonl(ANS_PATH)}
    first_counts, final_counts, reasons, resol = Counter(), Counter(), Counter(), Counter()
    n_cit, in_ctx, answers_with_invalid, rep_att, rep_acc, secs = 0, 0, 0, 0, 0, []
    pre_counts, pre_reasons, pre_resol, n_pre, pre_in_ctx = Counter(), Counter(), Counter(), 0, 0
    for v in ver:
        for c in (v.get("pre_report") or {}).get("citations", []):
            pre_counts[c["status"]] += 1
            pre_reasons.update(c["reasons"])
            pre_resol[c["resolution"]] += 1
            pre_in_ctx += c["in_context"]
            n_pre += 1
        first_counts[min(1, (v.get("pre_report") or {}).get("n_citations", 0))] += 1
    for v in ver:
        st = v["stage"]
        if not st:
            continue
        rep = st["report"]
        if (rep.get("repair") or {}).get("attempted"):
            # điểm CE đã có trong memo từ báo cáo trước-khi-sửa → thời gian này ≈ chi phí viết lại
            secs.append(v["stage_seconds"])
        repair = rep.get("repair") or {}
        before = repair.get("invalid_before", rep["counts"].get("invalid", 0))
        answers_with_invalid += before > 0
        rep_att += bool(repair.get("attempted"))
        rep_acc += bool(repair.get("accepted"))
        for c in rep["citations"]:
            final_counts[c["status"]] += 1
            reasons.update(c["reasons"])
            resol[c["resolution"]] += 1
            in_ctx += c["in_context"]
            n_cit += 1
    gen_secs = [a["gen_seconds"] for a in ans.values()]
    summary = {
        "n_questions": len(ver),
        "answers_without_any_citation": first_counts[0],
        "before_repair": {
            "n_citations": n_pre,
            "citations_per_answer": round(n_pre / max(1, len(ver)), 2),
            "status": dict(pre_counts),
            "reasons": dict(pre_reasons),
            "resolution": dict(pre_resol),
            "share_in_context": round(pre_in_ctx / max(1, n_pre), 4),
            "answers_with_invalid": answers_with_invalid,
        },
        "repair": {"attempted": rep_att, "accepted": rep_acc,
                   "seconds_when_attempted": {"median": sorted(secs)[len(secs) // 2] if secs else None,
                                              "p90": sorted(secs)[int(len(secs) * 0.9)] if secs else None}},
        "after_repair": {
            "n_citations": n_cit,
            "status": dict(final_counts),
            "reasons": dict(reasons),
            "resolution": dict(resol),
            "share_in_context": round(in_ctx / max(1, n_cit), 4),
        },
        "latency_generation_seconds_median": sorted(gen_secs)[len(gen_secs) // 2] if gen_secs else None,
        "latency_verify_cpu": (json.loads(LAT_PATH.read_text(encoding="utf-8")) if LAT_PATH.exists() else None),
        "note": "Nhãn verifier, CHƯA đối chiếu nhãn người — precision thật xem annotation_agreement.json.",
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(json.dumps(summary, ensure_ascii=False, indent=2))


# ── annotate / agreement ──────────────────────────────────────
SHEET_COLS = ["cid", "question", "sentence", "citation", "resolved_document", "article_text",
              "label_correct_document", "label_article_exists", "label_supports_claim", "note"]


def cmd_annotate(args):
    """
    Phiếu gán nhãn tay: lấy mẫu trích dẫn trên câu trả lời GỐC (trước khi sửa), phân tầng
    theo trạng thái verifier để đủ ca mỗi loại. KHÔNG ghi trạng thái verifier vào phiếu
    (tránh người gán nhãn bị dẫn dắt); khoá trạng thái nằm ở _cache/ (không lên git) cho tới
    khi chạy `agreement`.
    """
    # Chạy lại lệnh này sẽ ghi đè phiếu → mất nhãn đã điền. Chỉ cho phép khi phiếu còn trống.
    for who in ("annotator_A", "annotator_B"):
        p = SHEET_DIR / f"sheet_{who}.csv"
        if p.exists() and not args.force:
            with open(p, encoding="utf-8-sig") as f:
                filled = sum(1 for r in csv.DictReader(f) for col in SHEET_COLS
                             if col.startswith("label_") and (r.get(col) or "").strip())
            if filled:
                logger.error(f"{p.name} đã có {filled} ô nhãn — không ghi đè. Dùng --force nếu thật sự muốn tạo lại.")
                sys.exit(1)
    from src.verification.citation_index import CitationIndex
    th = json.loads((OUT_DIR / "verifier_eval.json").read_text(encoding="utf-8"))["threshold_from_dev"]["tau"]
    index = CitationIndex(INDEXES_DIR / "citation_index.sqlite")
    ctx = {r["item_id"]: r for r in read_jsonl(CTX_PATH)}
    ans = {r["item_id"]: r["answer"] for r in read_jsonl(ANS_PATH) if r["answer"]}
    pre = {r["item_id"]: r["pre_report"] for r in read_jsonl(VER_PATH) if r.get("pre_report")}

    pool = defaultdict(list)
    for item_id in ans:
        for i, c in enumerate((pre.get(item_id) or {}).get("citations", [])):
            pool[c["status"]].append((item_id, i, c))
    rng = random.Random(args.seed)
    quota = {"valid": 30, "warning": 25, "invalid": 25, "unverifiable": 20}
    picked = []
    for s, q in quota.items():
        rows = sorted(pool[s], key=lambda x: (x[0], x[1]))
        picked += rng.sample(rows, min(q, len(rows)))
    rng.shuffle(picked)

    SHEET_DIR.mkdir(parents=True, exist_ok=True)
    key = []
    lines = []
    for n, (item_id, i, c) in enumerate(picked, 1):
        answer = ans[item_id]
        s0 = answer.rfind("\n", 0, c["start"]) + 1
        s1 = answer.find("\n", c["end"])
        art = index.get_article(c["doc_id"], c["dieu"]) if c.get("doc_id") else None
        cid = f"c{n:03d}"
        lines.append({"cid": cid, "question": ctx[item_id]["question"],
                      "sentence": answer[s0:s1 if s1 > 0 else None].strip()[:800],
                      "citation": c["text"],
                      "resolved_document": " | ".join(x for x in (c.get("loai"), c.get("so_hieu"),
                                                                  c.get("title"), c.get("tinh_trang")) if x),
                      "article_text": (art or "(không có trong KB)")[:2500],
                      "label_correct_document": "", "label_article_exists": "",
                      "label_supports_claim": "", "note": ""})
        key.append({"cid": cid, "item_id": item_id, "citation_index": i, "status": c["status"],
                    "reasons": c["reasons"], "ce_score": c.get("ce_score")})
    for who in ("annotator_A", "annotator_B"):
        with open(SHEET_DIR / f"sheet_{who}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SHEET_COLS)
            w.writeheader()
            w.writerows(lines)
    (CACHE_DIR / "annotation_key.json").write_text(json.dumps({"tau": th, "items": key}, ensure_ascii=False,
                                                              indent=2), encoding="utf-8")
    (SHEET_DIR / "HUONG_DAN.md").write_text(GUIDE, encoding="utf-8")
    logger.info(f"{len(lines)} trích dẫn → {SHEET_DIR.relative_to(BASE_DIR).as_posix()}/ "
                f"(phân bố: {Counter(k['status'] for k in key)})")


GUIDE = """# Hướng dẫn gán nhãn trích dẫn (Citation Verification — D3)

Mỗi dòng là MỘT trích dẫn trong câu trả lời của hệ thống. Hai người gán nhãn ĐỘC LẬP
(mỗi người một file), không trao đổi trước khi xong.

Cột cần điền (Y / N / ?):

- `label_correct_document`: `resolved_document` có đúng là văn bản mà câu trả lời muốn trích không?
  `?` nếu câu trả lời không nói rõ văn bản.
- `label_article_exists`: Điều (và khoản, nếu có) được trích có tồn tại trong văn bản đó không?
  Đối chiếu `article_text`; nếu ghi "(không có trong KB)" thì tra văn bản gốc, không tra được thì `?`.
- `label_supports_claim`: nội dung `article_text` có hỗ trợ nhận định trong `sentence` không?
  `Y` = hỗ trợ trực tiếp; `N` = không hỗ trợ / nói chuyện khác; `?` = hỗ trợ một phần.

Không cần xét hiệu lực: hiệu lực lấy từ metadata, không phải phán đoán của người gán nhãn.
"""


_LABEL_ALIASES = {"TRUE": "Y", "FALSE": "N", "YES": "Y", "NO": "N", "CÓ": "Y", "KHÔNG": "N", "1": "Y", "0": "N"}


def norm_label(v: str) -> str:
    """Y/N/? hoặc rỗng. Google Sheets/Excel dạng checkbox xuất TRUE/FALSE — quy về Y/N."""
    s = (v or "").strip().upper()
    return _LABEL_ALIASES.get(s, s)


def cmd_agreement(args):
    """
    Chạy SAU khi cả hai phiếu đã điền xong. Lần chạy đầu chép khoá chấm từ _cache/ ra cạnh
    phiếu (annotation/annotation_key.json) để commit cùng nhãn — người khác tính lại được
    mà không cần _cache/. Trước lúc này khoá nằm trong _cache/ để người gán nhãn không thấy.
    """
    from sklearn.metrics import cohen_kappa_score
    published = SHEET_DIR / "annotation_key.json"
    src = CACHE_DIR / "annotation_key.json"
    if src.exists():
        published.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    key = {k["cid"]: k for k in json.loads(published.read_text(encoding="utf-8"))["items"]}
    sheets = {}
    for who in ("annotator_A", "annotator_B"):
        with open(SHEET_DIR / f"sheet_{who}.csv", encoding="utf-8-sig") as f:
            sheets[who] = {r["cid"]: r for r in csv.DictReader(f)}
    out = {}
    for col in ("label_correct_document", "label_article_exists", "label_supports_claim"):
        a = [norm_label(sheets["annotator_A"][c][col]) for c in key]
        b = [norm_label(sheets["annotator_B"][c][col]) for c in key]
        both = [(x, y) for x, y in zip(a, b) if x and y]
        if both:
            raw = round(sum(x == y for x, y in both) / len(both), 4)
            if len({v for pair in both for v in pair}) < 2:
                # cả hai người dùng đúng một nhãn cho mọi dòng → κ không xác định (không ghi NaN vào JSON)
                out[col] = {"n": len(both), "kappa": None, "raw_agreement": raw,
                            "note": "chỉ có một nhãn duy nhất — κ không xác định"}
            else:
                out[col] = {"n": len(both), "kappa": round(cohen_kappa_score(*zip(*both)), 4),
                            "raw_agreement": raw}
    # verifier so với nhãn đồng thuận: "sai" = sai văn bản hoặc Điều không tồn tại hoặc không hỗ trợ
    agree = []
    for c, k in key.items():
        la, lb = sheets["annotator_A"][c], sheets["annotator_B"][c]
        labs = []
        for r in (la, lb):
            vals = [norm_label(r[col]) for col in ("label_correct_document", "label_article_exists",
                                                       "label_supports_claim")]
            labs.append(None if "" in vals or "?" in vals else ("bad" if "N" in vals else "ok"))
        if labs[0] and labs[0] == labs[1]:
            agree.append((labs[0], k["status"]))
    tp = sum(1 for h, s in agree if h == "bad" and s == "invalid")
    fp = sum(1 for h, s in agree if h == "ok" and s == "invalid")
    fn = sum(1 for h, s in agree if h == "bad" and s != "invalid")

    # Mẫu lấy PHÂN TẦNG theo trạng thái verifier (quota cố định) → muốn suy ra cho toàn bộ
    # trích dẫn thì mỗi mẫu mang trọng số = số trích dẫn của tầng trong toàn bộ / số mẫu của tầng.
    # Precision của cờ "invalid" chỉ dùng tầng invalid nên không đổi; recall thì phải có trọng số.
    pop = Counter(c["status"] for r in read_jsonl(VER_PATH) for c in (r.get("pre_report") or {}).get("citations", []))
    sampled = Counter(k["status"] for k in key.values())
    w = {s: pop[s] / sampled[s] for s in sampled if sampled[s]}
    wtp = sum(w[s] for h, s in agree if h == "bad" and s == "invalid")
    wfn = sum(w[s] for h, s in agree if h == "bad" and s != "invalid")
    wbad = sum(w[s] for h, s in agree if h == "bad")
    wall = sum(w[s] for _, s in agree)
    out["verifier_vs_consensus"] = {
        "n_consensus": len(agree),
        "confusion": dict(Counter(f"{h}->{s}" for h, s in agree)),
        "sample": {"precision_invalid": round(tp / (tp + fp), 4) if tp + fp else None,
                   "recall_invalid": round(tp / (tp + fn), 4) if tp + fn else None},
        "population_weighted": {
            "precision_invalid": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall_invalid": round(wtp / (wtp + wfn), 4) if wtp + wfn else None,
            "share_bad_citations": round(wbad / wall, 4) if wall else None,
            "stratum_weights": {s: round(x, 3) for s, x in w.items()},
        },
        "note": "Báo cáo population_weighted cho toàn bộ trích dẫn D3; 'sample' chỉ để đối chiếu.",
    }
    (OUT_DIR / "annotation_agreement.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                       encoding="utf-8")
    logger.info(json.dumps(out, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("contexts")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    sub.add_parser("generate")
    p = sub.add_parser("verify")
    p.add_argument("--limit", type=int, default=0, help="chỉ kiểm N câu chưa làm (0 = tất cả)")
    p = sub.add_parser("annotate")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--force", action="store_true", help="ghi đè cả khi phiếu đã có nhãn")
    sub.add_parser("agreement")
    sub.add_parser("summary")
    p = sub.add_parser("latency")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    {"contexts": cmd_contexts, "generate": cmd_generate, "verify": cmd_verify, "latency": cmd_latency,
     "annotate": cmd_annotate, "agreement": cmd_agreement, "summary": lambda a: summarize()}[args.cmd](args)


if __name__ == "__main__":
    main()
