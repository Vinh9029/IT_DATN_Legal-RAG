"""
Script 17: Đánh giá retrieval cho bài báo (§5 — RQ2, RQ3, ablation).

─── Vì sao cần script này ───

Pipeline online chỉ trả câu trả lời, không đo được gì. Script này chạy lại đúng
các stage retrieval của `src/api/routers/query.py` (viết lại → BM25 + dense →
RRF → rerank) trên tập val/test của dataset QA, với Điều nguồn làm gold
(`data/qa_pairs/eval/gold_map.json`, script 16), rồi đo Recall@K và MRR khi chỉ
thay đổi kích thước pool ứng viên.

Graph expansion (Neo4j) KHÔNG chạy: bài báo không mô tả nó, và routing trong bài
chỉ đổi kích thước pool.

─── Bốn bước, mỗi bước cache riêng (chạy lại được, bỏ dở được) ───

    cd backend/
    lms load meta-llama-3.1-8b-instruct
    python evol_instruct/scripts/17_eval_retrieval.py rewrite           # Llama viết lại câu (lâu nhất)
    python evol_instruct/scripts/17_eval_retrieval.py retrieve          # phân loại q/q̃ + BM25/dense top-200
    G:/venv_ft/Scripts/python evol_instruct/scripts/17_eval_retrieval.py rerank   # cross-encoder, cần GPU
    python evol_instruct/scripts/17_eval_retrieval.py report            # bảng, hình, bootstrap

Thêm `--limit 20` để chạy thử trên vài câu mỗi split.

`rerank` chạy bằng venv khác vì `venv/` gốc là torch bản CPU: bge-reranker-large
trên CPU ~0,5 s/cặp, quét pool tới 200 ứng viên thì không chạy nổi.

─── Hai chỗ khác production, có chủ đích ───

1. BM25 chấm điểm bằng ma trận thưa thay vì `BM25Okapi.get_scores` (vòng Python
   qua 518k văn bản cho mỗi token, ~33 s/câu với câu đã viết lại). Cùng công
   thức, cùng idf, cùng cách xếp hạng khi bằng điểm; lần đầu dựng cache sẽ đối
   chiếu với `get_scores` trên vài câu.
2. Rerank gọi thẳng transformers (logit, không qua sigmoid) thay vì FlagReranker
   — sigmoid đơn điệu nên thứ hạng không đổi; truncation `only_second` ở 512
   token như FlagReranker khi câu hỏi ngắn hơn 3/4 max_length.
"""

import argparse
import collections
import importlib.util
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # backend/
sys.path.insert(0, str(ROOT))

from loguru import logger

FINAL_DIR = ROOT / "data" / "qa_pairs" / "final"
EVAL_DIR = ROOT / "data" / "qa_pairs" / "eval"
CACHE_DIR = EVAL_DIR / "_cache"                      # file trung gian lớn — xoá sau khi chốt số
GOLD_PATH = EVAL_DIR / "gold_map.json"
REWRITE_PATH = CACHE_DIR / "rewrites.jsonl"
ROUTING_PATH = CACHE_DIR / "routing.json"
CAND_PATH = CACHE_DIR / "candidates.jsonl"
RERANK_PATH = CACHE_DIR / "rerank.jsonl"
BM25_CSC_PATH = CACHE_DIR / "bm25_csc.npz"
BM25_META_PATH = CACHE_DIR / "bm25_meta.json"
RESULT_PATH = EVAL_DIR / "retrieval_results.json"
FIG_PATH = ROOT.parent / "docs" / "figures" / "poolsize.pdf"

CHUNKS_PATH = ROOT / "data" / "rag" / "processed" / "chunks" / "chunks.jsonl"
BM25_DIR = ROOT / "data" / "rag" / "indexes" / "bm25"
CLASSIFIER_DIR = ROOT / "models" / "routing_classifier"

N_MAX = 200                                          # pool lớn nhất cần quét
POOL_GRID = (5, 10, 20, 50, 100, 200)
K = 5                                                # top_k mặc định của /api/query
RRF_K = 60


def load_module(name: str, rel_path: str):
    """Nạp riêng một file — import qua package `src.retrieval` sẽ kéo cả qdrant/neo4j/reranker."""
    spec = importlib.util.spec_from_file_location(name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def label_of(r: dict) -> str:
    return r.get("final_label") or r.get("specificity")


def load_items(limit: int | None) -> list[dict]:
    """Câu val + test có gold trong KB. `limit` lấy mẫu cố định mỗi split để chạy thử."""
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    items = []
    for split in ("val", "test"):
        rows = [r for r in json.loads((FINAL_DIR / f"{split}.json").read_text(encoding="utf-8"))
                if r["item_id"] in gold]
        if limit:
            rows = random.Random(42).sample(rows, min(limit, len(rows)))
        for r in rows:
            items.append({"item_id": r["item_id"], "pair_id": r["pair_id"], "split": split,
                          "question": r["question"], "label": label_of(r),
                          "mode": (r.get("metadata") or {}).get("narrow_mode"),
                          "gold": set(gold[r["item_id"]])})
    return items


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_rewrites(model: str) -> dict:
    return {d["item_id"]: d["evolved"] for d in read_jsonl(REWRITE_PATH) if d.get("model") == model}


# ══════════════════════════════════════════════════════════════════
# 1. Viết lại câu hỏi
# ══════════════════════════════════════════════════════════════════

def cmd_rewrite(args):
    from config.settings import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME

    items = load_items(args.limit)
    evolver_mod = load_module("query_evolver", "src/retrieval/query_evolver.py")
    # model_dir trỏ chỗ không có adapter: chỉ cần _rewrite, khỏi nạp PhoBERT.
    evolver = evolver_mod.QueryEvolver(base_url=LLM_BASE_URL, api_key=LLM_API_KEY,
                                       model=LLM_MODEL_NAME, temperature=0.3,
                                       model_dir=CACHE_DIR / "_no_classifier")
    done = load_rewrites(LLM_MODEL_NAME)
    todo = [it for it in items if it["item_id"] not in done]
    logger.info(f"{len(items)} câu | đã có {len(items) - len(todo)} | cần viết lại {len(todo)}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    n_err = 0
    with REWRITE_PATH.open("a", encoding="utf-8") as f:
        for i, it in enumerate(todo, 1):
            ev = evolver._rewrite(it["question"])
            if ev == it["question"]:
                # _rewrite trả nguyên câu khi LLM lỗi — không cache để lần sau thử lại.
                n_err += 1
                continue
            f.write(json.dumps({"item_id": it["item_id"], "model": LLM_MODEL_NAME,
                                "evolved": ev}, ensure_ascii=False) + "\n")
            f.flush()
            if i % 50 == 0:
                logger.info(f"  {i}/{len(todo)} (lỗi {n_err})")
    logger.info(f"Xong | lỗi LLM {n_err} (chạy lại lệnh để thử lại các câu lỗi)")


# ══════════════════════════════════════════════════════════════════
# 2. Phân loại + truy hồi ứng viên
# ══════════════════════════════════════════════════════════════════

class FastBM25:
    """
    Cùng điểm với `BM25Okapi.get_scores` (rank_bm25), tính trên ma trận thưa.

    get_scores lặp qua TỪNG token của câu hỏi (kể cả token lặp) và cộng
    idf·tf·(k1+1)/(tf + k1·(1−b+b·len/avgdl)); token lặp c lần thì cộng c lần —
    ở đây nhân c. Văn bản có tf = 0 đóng góp 0 nên chỉ cần duyệt phần khác 0.
    """

    def __init__(self):
        import numpy as np
        import scipy.sparse as sp

        if not BM25_CSC_PATH.exists():
            self._build()
        self.tf = sp.load_npz(BM25_CSC_PATH).tocsc()
        meta = json.loads(BM25_META_PATH.read_text(encoding="utf-8"))
        self.vocab = {t: i for i, t in enumerate(meta["vocab"])}
        self.idf = np.asarray(meta["idf"], dtype=np.float64)
        self.k1, self.b = meta["k1"], meta["b"]
        doc_len = np.asarray(meta["doc_len"], dtype=np.float64)
        self.norm = self.k1 * (1 - self.b + self.b * doc_len / meta["avgdl"])
        self.chunk_ids = json.loads((BM25_DIR / "bm25_corpus_ids.json").read_text(encoding="utf-8"))
        self.tokenize = load_module("bm25_builder", "src/indexing/bm25_builder.py").tokenize_vietnamese

    @staticmethod
    def _build():
        """Dựng ma trận tf từ pickle một lần (~vài phút, ~10 GB RAM lúc dựng)."""
        import pickle
        from array import array

        import numpy as np
        import scipy.sparse as sp

        logger.info("Dựng cache BM25 thưa từ bm25_index.pkl (một lần)...")
        with (BM25_DIR / "bm25_index.pkl").open("rb") as f:
            bm25 = pickle.load(f)
        vocab = {}
        # array thay list: ~80M phần tử, list int Python tốn ~3 GB, array 4 byte/phần tử
        indptr, indices, data = array("q", [0]), array("i"), array("i")
        for d in bm25.doc_freqs:
            for t, c in d.items():
                indices.append(vocab.setdefault(t, len(vocab)))
                data.append(c)
            indptr.append(len(indices))
        mat = sp.csr_matrix((np.frombuffer(data, dtype=np.int32).astype(np.float32),
                             np.frombuffer(indices, dtype=np.int32), np.frombuffer(indptr, dtype=np.int64)),
                            shape=(len(bm25.doc_freqs), len(vocab)))
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        sp.save_npz(BM25_CSC_PATH, mat)
        words = [None] * len(vocab)
        for t, i in vocab.items():
            words[i] = t
        BM25_META_PATH.write_text(json.dumps({
            "vocab": words,
            "idf": [bm25.idf.get(t, 0.0) for t in words],
            "k1": bm25.k1, "b": bm25.b, "avgdl": bm25.avgdl, "doc_len": list(bm25.doc_len),
        }, ensure_ascii=False), encoding="utf-8")

        # Đối chiếu với get_scores trên vài câu ngắn trước khi tin cache.
        fast = FastBM25()
        for q in ("quyền thừa kế của con riêng", "thời hiệu khởi kiện vụ án dân sự",
                  "mức phạt vi phạm hợp đồng đặt cọc mua nhà"):
            ref = bm25.get_scores(fast.tokenize(q))
            got = fast.scores(q)
            assert np.allclose(ref, got, rtol=1e-9, atol=1e-9), f"BM25 thưa lệch get_scores ở «{q}»"
            assert fast.top(q, 50) == fast._top_from(ref, 50), f"BM25 thưa lệch thứ hạng ở «{q}»"
        logger.info("✅ BM25 thưa khớp get_scores trên 3 câu đối chiếu")

    def scores(self, query: str):
        import numpy as np

        out = np.zeros(self.tf.shape[0], dtype=np.float64)
        for t, c in collections.Counter(self.tokenize(query)).items():
            j = self.vocab.get(t)
            if j is None or self.idf[j] == 0:
                continue
            lo, hi = self.tf.indptr[j], self.tf.indptr[j + 1]
            rows = self.tf.indices[lo:hi]
            tf = self.tf.data[lo:hi].astype(np.float64)
            out[rows] += c * self.idf[j] * (tf * (self.k1 + 1) / (tf + self.norm[rows]))
        return out

    def _top_from(self, scores, n: int) -> list[str]:
        """Như SparseRetriever.search: sorted ổn định (hoà điểm → index nhỏ trước), bỏ điểm ≤ 0."""
        import numpy as np

        order = np.argsort(-scores, kind="stable")[:n]
        return [self.chunk_ids[i] for i in order if scores[i] > 0]

    def top(self, query: str, n: int) -> list[str]:
        return self._top_from(self.scores(query), n)


def cmd_retrieve(args):
    from config.settings import (EMBEDDING_MODEL, LLM_MODEL_NAME, QDRANT_COLLECTION_NAME,
                                 QDRANT_HOST, QDRANT_PORT)

    items = load_items(args.limit)
    rewrites = load_rewrites(LLM_MODEL_NAME)
    missing = [it["item_id"] for it in items if it["item_id"] not in rewrites]
    if missing:
        logger.error(f"{len(missing)} câu chưa viết lại — chạy `rewrite` trước. Ví dụ: {missing[:3]}")
        sys.exit(1)

    # ── Phân loại q và q̃ ─────────────────────────────────────────
    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8")) if ROUTING_PATH.exists() else {}
    todo = [it for it in items if it["item_id"] not in routing]
    if todo:
        from evol_instruct.src.qa_specificity.routing_classifier import RoutingClassifier

        clf = RoutingClassifier(model_dir=CLASSIFIER_DIR)
        assert clf.is_ready, "Chưa có adapter routing classifier"
        logger.info(f"Phân loại {len(todo)} câu (gốc và đã viết lại)...")
        pred_q = clf.predict_batch([it["question"] for it in todo])
        pred_qt = clf.predict_batch([rewrites[it["item_id"]] for it in todo])
        for it, a, b in zip(todo, pred_q, pred_qt):
            routing[it["item_id"]] = {"q": a, "q_tilde": b}
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        ROUTING_PATH.write_text(json.dumps(routing, ensure_ascii=False), encoding="utf-8")

    # ── BM25 + dense top-N_MAX ───────────────────────────────────
    done = {d["item_id"] for d in read_jsonl(CAND_PATH)}
    todo = [it for it in items if it["item_id"] not in done]
    logger.info(f"Truy hồi: cần {len(todo)} câu (đã có {len(items) - len(todo)})")
    if not todo:
        return

    bm25 = FastBM25()
    dense_mod = load_module("dense_retriever", "src/retrieval/dense_retriever.py")
    dense = dense_mod.DenseRetriever(db_type="qdrant", qdrant_host=QDRANT_HOST, qdrant_port=QDRANT_PORT,
                                     qdrant_collection=QDRANT_COLLECTION_NAME, model_name=EMBEDDING_MODEL)
    with CAND_PATH.open("a", encoding="utf-8") as f:
        for i, it in enumerate(todo, 1):
            q = rewrites[it["item_id"]]
            f.write(json.dumps({
                "item_id": it["item_id"],
                "bm25": bm25.top(q, N_MAX),
                "dense": [h["chunk_id"] for h in dense.search(q, top_k=N_MAX)],
            }, ensure_ascii=False) + "\n")
            f.flush()
            if i % 100 == 0:
                logger.info(f"  {i}/{len(todo)}")
    logger.info("Xong truy hồi")


# ══════════════════════════════════════════════════════════════════
# 3. Rerank (chạy bằng venv có torch CUDA)
# ══════════════════════════════════════════════════════════════════

RE_CHUNK_ID = re.compile(r'"chunk_id"\s*:\s*"([^"]+)"')


def load_chunk_texts(ids: set[str]) -> dict:
    """
    Đọc content của các chunk cần — lọc bằng regex trước khi json.loads cả file 1,5 GB.
    Trùng chunk_id thì bản sau đè bản trước, như `chunks_cache` của production.
    """
    out = {}
    with CHUNKS_PATH.open(encoding="utf-8") as f:
        for line in f:
            m = RE_CHUNK_ID.search(line)
            if m and m.group(1) in ids:
                out[m.group(1)] = json.loads(line).get("content", "")
    return out


def cmd_rerank(args):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from config.settings import LLM_MODEL_NAME

    assert torch.cuda.is_available(), "Cần GPU — chạy bằng G:/venv_ft/Scripts/python"
    items = {it["item_id"]: it for it in load_items(args.limit)}
    rewrites = load_rewrites(LLM_MODEL_NAME)
    done = {d["item_id"] for d in read_jsonl(RERANK_PATH)}
    cands = [c for c in read_jsonl(CAND_PATH) if c["item_id"] in items and c["item_id"] not in done]
    logger.info(f"Rerank: cần {len(cands)} câu (đã có {len(done)})")
    if not cands:
        return

    need = {cid for c in cands for cid in c["bm25"] + c["dense"]}
    logger.info(f"Đọc nội dung {len(need)} chunk...")
    texts = load_chunk_texts(need)
    lost = need - texts.keys()
    if lost:
        logger.warning(f"{len(lost)} chunk không có trong chunks.jsonl — chấm với content rỗng như production")

    name = "BAAI/bge-reranker-large"
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForSequenceClassification.from_pretrained(name, dtype=torch.float16).cuda().eval()

    with RERANK_PATH.open("a", encoding="utf-8") as f:
        for i, c in enumerate(cands, 1):
            q = rewrites[c["item_id"]]
            ids = list(dict.fromkeys(c["dense"] + c["bm25"]))
            scores = []
            for s in range(0, len(ids), args.batch_size):
                batch = ids[s:s + args.batch_size]
                enc = tok([q] * len(batch), [texts.get(x, "") for x in batch], padding=True,
                          truncation="only_second", max_length=512, return_tensors="pt").to("cuda")
                with torch.no_grad():
                    scores += model(**enc).logits.view(-1).float().tolist()
            f.write(json.dumps({"item_id": c["item_id"], "scores": dict(zip(ids, scores))}) + "\n")
            f.flush()
            if i % 50 == 0:
                logger.info(f"  {i}/{len(cands)}")
    logger.info("Xong rerank")


# ══════════════════════════════════════════════════════════════════
# 4. Báo cáo
# ══════════════════════════════════════════════════════════════════

def rrf_pool(dense: list[str], bm25: list[str], n: int) -> list[str]:
    """Như rrf_fusion.reciprocal_rank_fusion(dense[:n], sparse[:n], top_k=n): dense chèn trước, sort ổn định."""
    score = {}
    for lst in (dense[:n], bm25[:n]):
        for rank, cid in enumerate(lst):
            score[cid] = score.get(cid, 0.0) + 1 / (RRF_K + rank + 1)
    return sorted(score, key=score.get, reverse=True)[:n]


def rank_of_gold(ranked: list[str], gold: set) -> int | None:
    for i, cid in enumerate(ranked[:K], 1):
        if cid in gold:
            return i
    return None


class Evaluator:
    def __init__(self, items, cands, rerank):
        self.items, self.cands, self.rerank = items, cands, rerank
        self._memo = {}

    def rank(self, item_id: str, n: int, rerank: bool = True) -> int | None:
        key = (item_id, n, rerank)
        if key not in self._memo:
            c = self.cands[item_id]
            pool = rrf_pool(c["dense"], c["bm25"], n)
            if rerank:
                s = self.rerank[item_id]
                pool = sorted(pool, key=lambda x: s[x], reverse=True)
            self._memo[key] = rank_of_gold(pool, self.items[item_id]["gold"])
        return self._memo[key]


def metrics(ranks: list) -> dict:
    n = len(ranks)
    return {"n": n,
            "recall": round(sum(r is not None for r in ranks) / n, 4) if n else None,
            "mrr": round(sum(1 / r for r in ranks if r) / n, 4) if n else None}


def by_label(items: list[dict], rank_fn) -> dict:
    out = {}
    for lab in ("broad", "narrow", "all"):
        sub = [it for it in items if lab == "all" or it["label"] == lab]
        out[lab] = metrics([rank_fn(it) for it in sub])
    return out


def per_query(items, rank_fn) -> tuple[list, list]:
    """(hit, rr) từng câu — cho bootstrap. Random routing trả kỳ vọng nên là số thực."""
    hit, rr = [], []
    for it in items:
        r = rank_fn(it)
        if isinstance(r, tuple):                      # kỳ vọng của random routing
            hit.append(sum(x is not None for x in r) / len(r))
            rr.append(sum(1 / x for x in r if x) / len(r))
        else:
            hit.append(float(r is not None))
            rr.append(1 / r if r else 0.0)
    return hit, rr


def paired_bootstrap(a: list[float], b: list[float], n_resamples: int, seed: int = 42) -> float:
    """p hai phía cho H0: mean(a) = mean(b), lấy lại mẫu theo câu (Koehn 2004)."""
    import numpy as np

    d = np.asarray(a) - np.asarray(b)
    obs = d.mean()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_resamples, len(d)))
    boot = d[idx].mean(axis=1)
    # Dời phân phối về H0 rồi đếm mức lệch ít nhất bằng quan sát
    return float(((np.abs(boot - obs) >= abs(obs) - 1e-12).sum() + 1) / (n_resamples + 1))


def cmd_report(args):
    items_list = load_items(args.limit)
    items = {it["item_id"]: it for it in items_list}
    cands = {c["item_id"]: c for c in read_jsonl(CAND_PATH) if c["item_id"] in items}
    rerank = {r["item_id"]: r["scores"] for r in read_jsonl(RERANK_PATH) if r["item_id"] in items}
    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    ready = [it for it in items_list if it["item_id"] in rerank and it["item_id"] in cands]
    if len(ready) < len(items_list):
        logger.warning(f"Chỉ {len(ready)}/{len(items_list)} câu có đủ cache — báo cáo trên phần đã có")
    ev = Evaluator(items, cands, rerank)
    val = [it for it in ready if it["split"] == "val"]
    test = [it for it in ready if it["split"] == "test"]
    res = {"K": K, "pool_grid": list(POOL_GRID), "n_val": len(val), "n_test": len(test)}

    # ── RQ2: quét pool trên val, theo nhãn gold ──────────────────
    sweep = {n: by_label(val, lambda it, n=n: ev.rank(it["item_id"], n)) for n in POOL_GRID}
    res["val_sweep"] = {str(n): v for n, v in sweep.items()}
    # p (bootstrap, Recall@K) của mỗi n so với n tốt nhất cùng nhãn — để biết đường quét có phẳng không
    res["val_sweep_p_vs_best"] = {}
    for lab in ("broad", "narrow"):
        sub = [it for it in val if it["label"] == lab]
        top = max(POOL_GRID, key=lambda n: (sweep[n][lab]["recall"], sweep[n][lab]["mrr"], -n))
        h_top, _ = per_query(sub, lambda it: ev.rank(it["item_id"], top))
        res["val_sweep_p_vs_best"][lab] = {"best": top, **{
            str(n): round(paired_bootstrap(per_query(sub, lambda it, n=n: ev.rank(it["item_id"], n))[0],
                                           h_top, args.resamples), 4)
            for n in POOL_GRID if n != top}}

    def best(lab):
        # Recall@K cao nhất; hoà thì MRR cao hơn, rồi pool nhỏ hơn (rẻ hơn)
        return max(POOL_GRID, key=lambda n: (sweep[n][lab]["recall"], sweep[n][lab]["mrr"], -n))

    n_narrow = args.n_narrow or best("narrow")
    n_broad = args.n_broad or best("broad")
    res["chosen"] = {"n_narrow": n_narrow, "n_broad": n_broad,
                     "from_val": not (args.n_narrow or args.n_broad)}
    if n_broad <= n_narrow:
        logger.warning(f"Trên val: n_broad={n_broad} ≤ n_narrow={n_narrow} — trái giả thuyết RQ2, "
                       f"truyền --n-narrow/--n-broad để cố định khi đo test")

    # ── RQ3: bảng chính trên test ────────────────────────────────
    pick = {"broad": n_broad, "narrow": n_narrow}
    policies = {
        "fixed_small": lambda it: ev.rank(it["item_id"], n_narrow),
        "fixed_large": lambda it: ev.rank(it["item_id"], n_broad),
        "random": lambda it: (ev.rank(it["item_id"], n_narrow), ev.rank(it["item_id"], n_broad)),
        "routing_q_tilde": lambda it: ev.rank(it["item_id"], pick[routing[it["item_id"]]["q_tilde"]]),
        "routing_q": lambda it: ev.rank(it["item_id"], pick[routing[it["item_id"]]["q"]]),
        "oracle": lambda it: ev.rank(it["item_id"], pick[it["label"]]),
    }
    # Cỡ pool mỗi câu = số cặp re-ranker phải chấm (chi phí)
    pool_of = {
        "fixed_small": lambda it: n_narrow,
        "fixed_large": lambda it: n_broad,
        "random": lambda it: (n_narrow + n_broad) / 2,
        "routing_q_tilde": lambda it: pick[routing[it["item_id"]]["q_tilde"]],
        "routing_q": lambda it: pick[routing[it["item_id"]]["q"]],
        "oracle": lambda it: pick[it["label"]],
    }
    main = {}
    for name, fn in policies.items():
        main[name] = {}
        for lab in ("broad", "narrow", "all"):
            sub = [it for it in test if lab == "all" or it["label"] == lab]
            hit, rr = per_query(sub, fn)
            main[name][lab] = {"n": len(sub), "recall": round(sum(hit) / len(sub), 4),
                               "mrr": round(sum(rr) / len(sub), 4),
                               "mean_pool": round(sum(pool_of[name](it) for it in sub) / len(sub), 2)}
    res["test_main"] = main

    # Paired bootstrap so với fixed-large
    sig = {}
    for name, fn in policies.items():
        if name == "fixed_large":
            continue
        sig[name] = {}
        for lab in ("broad", "narrow", "all"):
            sub = [it for it in test if lab == "all" or it["label"] == lab]
            h1, r1 = per_query(sub, fn)
            h0, r0 = per_query(sub, policies["fixed_large"])
            sig[name][lab] = {"p_recall": round(paired_bootstrap(h1, h0, args.resamples), 4),
                              "p_mrr": round(paired_bootstrap(r1, r0, args.resamples), 4)}
    res["bootstrap"] = {"resamples": args.resamples, "vs": "fixed_large", "p": sig}

    # Tỉ lệ dự đoán narrow — để đọc bảng chính
    res["routing_rate_narrow"] = {
        src: {lab: round(sum(routing[it["item_id"]][src] == "narrow" for it in test if it["label"] == lab)
                         / max(1, sum(it["label"] == lab for it in test)), 4) for lab in ("broad", "narrow")}
        for src in ("q", "q_tilde")}

    # Lệch nhãn do rewriter (đoạn Effect of Query Rewriting): câu broad bị chèn số điều / số văn bản
    # mới vào q̃. Regex khớp cách đếm cũ trên mẫu 200 câu (85/100, 61/71).
    from config.settings import LLM_MODEL_NAME
    rewrites = load_rewrites(LLM_MODEL_NAME)
    pats = (r"Điều\s+\d+", r"\d+/\d{4}/[\wĐđ\-]+")

    def inserted(it):
        q, qt = it["question"], rewrites[it["item_id"]]
        return any(set(re.findall(p, qt, flags=re.I)) - set(re.findall(p, q, flags=re.I)) for p in pats)

    broad = [it for it in test if it["label"] == "broad"]
    misrouted = [it for it in broad if routing[it["item_id"]]["q_tilde"] == "narrow"]
    res["rewrite_shift"] = {
        "acc_q": round(sum(routing[it["item_id"]]["q"] == it["label"] for it in test) / len(test), 4),
        "acc_q_tilde": round(sum(routing[it["item_id"]]["q_tilde"] == it["label"] for it in test) / len(test), 4),
        "broad": len(broad), "broad_to_narrow": len(misrouted),
        "narrow_to_broad": sum(it["label"] == "narrow" and routing[it["item_id"]]["q_tilde"] == "broad"
                               for it in test),
        "broad_inserted": sum(map(inserted, broad)),
        "misrouted_inserted": sum(map(inserted, misrouted)),
        "mean_syllables": {"q": round(sum(len(it["question"].split()) for it in test) / len(test), 1),
                           "q_tilde": round(sum(len(rewrites[it["item_id"]].split()) for it in test) / len(test), 1)},
    }

    # ── Ablation trên test ───────────────────────────────────────
    res["test_ablation"] = {
        "bm25_only": by_label(test, lambda it: rank_of_gold(cands[it["item_id"]]["bm25"], it["gold"])),
        "dense_only": by_label(test, lambda it: rank_of_gold(cands[it["item_id"]]["dense"], it["gold"])),
        "hybrid_rrf": by_label(test, lambda it: ev.rank(it["item_id"], n_broad, rerank=False)),
        "plus_rerank": by_label(test, lambda it: ev.rank(it["item_id"], n_broad)),
        "plus_routing": by_label(test, policies["routing_q_tilde"]),
    }

    # ── Ứng viên case study: cặp mà routing đổi kết quả so với fixed-large ──
    cases = []
    for it in test:
        a, b = policies["routing_q_tilde"](it), policies["fixed_large"](it)
        if (a is None) != (b is None):
            cases.append({"item_id": it["item_id"], "pair_id": it["pair_id"], "label": it["label"],
                          "pred": routing[it["item_id"]]["q_tilde"], "rank_routing": a,
                          "rank_fixed_large": b, "question": it["question"]})
    res["case_candidates"] = cases[:30]
    res["n_case_candidates"] = len(cases)

    if not args.limit:
        RESULT_PATH.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        plot_sweep(sweep)
        logger.info(f"→ {RESULT_PATH.relative_to(ROOT)} | {FIG_PATH.name}")
    print_summary(res)


def plot_sweep(sweep: dict):
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["pdf.fonttype"] = 42      # nhúng TrueType, không Type 3 (Springer từ chối Type 3)
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.6, 2.6))
    for lab, style in (("broad", dict(color="#1f5fa8", marker="o")),
                       ("narrow", dict(color="#c4572a", marker="s", linestyle="--"))):
        ax.plot(POOL_GRID, [sweep[n][lab]["recall"] for n in POOL_GRID], label=lab, **style)
    ax.set_xscale("log")
    ax.set_xticks(POOL_GRID)
    ax.set_xticklabels([str(n) for n in POOL_GRID])
    ax.set_xlabel("Candidate pool size $n$")
    ax.set_ylabel(f"Recall@{K}")
    ax.grid(alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_PATH)


def print_summary(res: dict):
    logger.info(f"val={res['n_val']} test={res['n_test']} | chọn n_narrow={res['chosen']['n_narrow']} "
                f"n_broad={res['chosen']['n_broad']}")
    logger.info("Quét pool trên val (R@K broad / narrow):")
    for n, v in res["val_sweep"].items():
        logger.info(f"   n={n:>3}: {v['broad']['recall']:.3f} / {v['narrow']['recall']:.3f}   "
                    f"MRR {v['broad']['mrr']:.3f} / {v['narrow']['mrr']:.3f}")
    logger.info("Test (R@K / MRR: broad | narrow | all):")
    for name, v in {**res["test_main"], **{f"abl:{k}": v for k, v in res["test_ablation"].items()}}.items():
        logger.info(f"   {name:18s} " + " | ".join(f"{v[l]['recall']:.3f}/{v[l]['mrr']:.3f}"
                                                   for l in ("broad", "narrow", "all")))
    logger.info(f"Tỉ lệ đoán narrow: {res['routing_rate_narrow']}")


def main():
    ap = argparse.ArgumentParser(description="Đánh giá retrieval cho bài báo")
    ap.add_argument("step", choices=("rewrite", "retrieve", "rerank", "report"))
    ap.add_argument("--limit", type=int, default=None, help="Chỉ lấy N câu mỗi split (chạy thử)")
    ap.add_argument("--batch-size", type=int, default=32, help="rerank: số cặp mỗi batch")
    ap.add_argument("--resamples", type=int, default=10000, help="report: số lần bootstrap")
    ap.add_argument("--n-narrow", type=int, default=None, help="report: cố định n_narrow thay vì chọn trên val")
    ap.add_argument("--n-broad", type=int, default=None, help="report: cố định n_broad thay vì chọn trên val")
    args = ap.parse_args()
    {"rewrite": cmd_rewrite, "retrieve": cmd_retrieve, "rerank": cmd_rerank, "report": cmd_report}[args.step](args)


if __name__ == "__main__":
    main()
