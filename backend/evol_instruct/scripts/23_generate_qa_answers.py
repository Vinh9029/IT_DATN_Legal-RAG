"""
Script 23: Sinh câu trả lời cho dataset Vietnamese-Legal-QA (config `answers`).

─── Vì sao cần script này ───

Dataset QA mới có câu hỏi + nhãn độ cụ thể, chưa có câu trả lời. Một Điều nguồn
thường KHÔNG đủ để trả lời: câu broad cần nhiều chế định, còn câu narrow/situation
hay gắn với Điều nguồn lệch chủ đề (trục 2). Nên context = Điều nguồn + top-k
Điều khác lấy từ chính corpus dân sự (`scoped_corpus.jsonl`, ~15k Điều) bằng
BM25 + dense → RRF → rerank. Không đụng stack online (Qdrant/Neo4j).

Teacher: Gemma-4-12B trên LM Studio, reasoning tắt. Teacher trả lời có ba mức
(full / partial / general) theo `config/qa_answer_prompts.py`.

─── Các lệnh (chạy từ backend/) ───

    ../venv/Scripts/python.exe evol_instruct/scripts/23_generate_qa_answers.py retrieve
    ../venv/Scripts/python.exe evol_instruct/scripts/23_generate_qa_answers.py pilot --n 40
    ../venv/Scripts/python.exe evol_instruct/scripts/23_generate_qa_answers.py generate --ids pilot
    ../venv/Scripts/python.exe evol_instruct/scripts/23_generate_qa_answers.py generate --max-items 300
    ../venv/Scripts/python.exe evol_instruct/scripts/23_generate_qa_answers.py check
    ../venv/Scripts/python.exe evol_instruct/scripts/23_generate_qa_answers.py export

Chạy dài thì dùng `run_answers_batched.sh` (mỗi mẻ một tiến trình, nạp lại model
giữa các mẻ để llama-server trả RAM).

─── An toàn ───

- Cache `answers_cache.jsonl` ghi append + fsync từng câu, khoá (item_id, version):
  tắt ngang lúc nào cũng không mất câu đã sinh, chạy lại là tiếp tục.
- Chốt RAM: RAM trống < --min-free-gb thì ngừng nhận câu mới, chờ câu đang chạy
  xong rồi thoát (exit 4) — không để hệ điều hành kill giữa chừng.
- File `data/qa_answers/STOP` tồn tại → dừng êm sau các câu đang chạy (exit 5).
- Timeout từng request; câu cụt (finish_reason=length) hoặc lặp khối → ghi lỗi,
  không đưa vào dataset.

Exit code: 0 = xong mẻ, 3 = không còn câu nào, 4 = chốt RAM, 5 = gặp STOP.
"""

import argparse
import collections
import hashlib
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # backend/
sys.path.insert(0, str(ROOT))

from loguru import logger

from config.qa_answer_prompts import (ANSWER_PROMPT_VERSION, STYLE, TEACHER_SYSTEM,
                                      USER_TEMPLATE, style_key)

FINAL_DIR = ROOT / "data" / "qa_pairs" / "final"
CORPUS_PATH = ROOT / "data" / "qa_pairs" / "raw" / "scoped_corpus.jsonl"
OUT_DIR = ROOT / "data" / "qa_answers"
CACHE_DIR = OUT_DIR / "_cache"
CONTEXTS_PATH = OUT_DIR / "contexts.jsonl"
ANSWERS_PATH = OUT_DIR / "answers_cache.jsonl"
PILOT_PATH = OUT_DIR / "pilot_ids.json"
STOP_PATH = OUT_DIR / "STOP"
EXPORT_DIR = OUT_DIR / "final"

SPLITS = {"train": "train.json", "validation": "val.json", "test": "test.json"}
SOURCE_CHARS = 2000      # Điều nguồn: như `input` của Evol-Instruct
EXTRA_CHARS = 1500       # mỗi Điều lấy thêm

TEACHER_MODEL = os.getenv("ANSWER_MODEL_NAME", "google/gemma-4-12b-qat")
TEACHER_URL = os.getenv("ANSWER_BASE_URL", "http://localhost:1234/v1")


# ══════════════════════════════════════════════════════════════════
# Dữ liệu
# ══════════════════════════════════════════════════════════════════

def load_items() -> list[dict]:
    items = []
    for split, fname in SPLITS.items():
        with open(FINAL_DIR / fname, encoding="utf-8") as f:
            for r in json.load(f):
                r["_split"] = split
                items.append(r)
    return items


EXPIRED = {"Hết hiệu lực toàn bộ", "Ngưng hiệu lực"}
RE_PART = re.compile(r"\s*-\s*Phần\s+\d+\s*$")


def load_corpus() -> list[dict]:
    """Một bản ghi / source_doc_id; gộp các Điều trùng nội dung (BLDS PDF vs HF)."""
    docs, seen_id, seen_hash = [], set(), {}
    with open(CORPUS_PATH, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            sid = r.get("source_doc_id")
            if not sid or sid in seen_id:
                continue
            seen_id.add(sid)
            content = (r.get("content") or "").strip()
            meta = r.get("metadata") or {}
            h = hashlib.md5(" ".join(content.split()).encode("utf-8")).hexdigest()
            status = meta.get("tinh_trang_hieu_luc") or ""
            docs.append({
                "id": sid,
                # PDF cục bộ chia "BLDS 2015 (...) - Phần 1/2" → bỏ hậu tố phần
                "title": RE_PART.sub("", (meta.get("title") or "").strip()),
                "content": content,
                "status": status,
                # 55% corpus là văn bản hết hiệu lực (BLTTDS 2004, BLDS 2005...) —
                # không bao giờ là Điều nguồn của QA, và không được lấy vào context
                "retrievable": status not in EXPIRED,
                "dup_of": seen_hash.get(h),     # Điều đầu tiên có cùng nội dung
            })
            seen_hash.setdefault(h, sid)
    return docs


def doc_block(doc: dict, limit: int) -> str:
    text = doc["content"]
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " …"
    return f"{doc['title']}\n{text}" if doc["title"] else text


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:      # dòng cuối ghi dở khi bị tắt ngang
                    pass
    return out


# ══════════════════════════════════════════════════════════════════
# retrieve: BM25 + dense → RRF → rerank, trên corpus dân sự
# ══════════════════════════════════════════════════════════════════

TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tok(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class BM25:
    """BM25 Okapi trên unigram + bigram âm tiết (từ tiếng Việt thường 2 âm tiết)."""

    def __init__(self, texts: list[str], k1=1.5, b=0.75):
        import numpy as np
        from sklearn.feature_extraction.text import CountVectorizer
        self.vec = CountVectorizer(tokenizer=_tok, lowercase=False, ngram_range=(1, 2),
                                   min_df=2, token_pattern=None)
        tf = self.vec.fit_transform(texts).tocsc().astype(np.float32)
        n = tf.shape[0]
        df = np.diff(tf.indptr)
        self.idf = np.log((n - df + 0.5) / (df + 0.5) + 1).astype(np.float32)
        dl = np.asarray(tf.sum(axis=1)).ravel()
        norm = k1 * (1 - b + b * dl / dl.mean())
        tf = tf.tocoo()
        data = tf.data * (k1 + 1) / (tf.data + norm[tf.row])
        import scipy.sparse as sp
        self.m = sp.csr_matrix((data, (tf.row, tf.col)), shape=tf.shape).tocsc()

    def top(self, query: str, k: int):
        import numpy as np
        q = self.vec.transform([query])
        cols = q.indices
        if len(cols) == 0:
            return []
        scores = np.asarray(self.m[:, cols] @ self.idf[cols]).ravel()
        idx = np.argpartition(-scores, min(k, len(scores) - 1))[:k]
        return sorted(idx.tolist(), key=lambda i: -scores[i])


def cmd_retrieve(args):
    import numpy as np
    import torch
    from sentence_transformers import CrossEncoder, SentenceTransformer

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    items = load_items()
    if args.limit:
        items = random.Random(0).sample(items, args.limit)
    done = {r["item_id"] for r in read_jsonl(CONTEXTS_PATH)}
    todo = [it for it in items if it["item_id"] not in done]
    logger.info(f"{len(items)} câu, đã có context {len(items) - len(todo)}, còn {len(todo)}")
    if not todo:
        return 3

    docs = load_corpus()
    by_id = {d["id"]: i for i, d in enumerate(docs)}
    texts = [f"{d['title']}\n{d['content'][:EXTRA_CHARS]}" for d in docs]
    logger.info(f"Corpus {len(docs)} Điều; dựng BM25…")
    bm25 = BM25(texts)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    emb_path = CACHE_DIR / f"doc_emb_{len(docs)}.npy"
    bi = SentenceTransformer("bkai-foundation-models/vietnamese-bi-encoder", device=device)
    if emb_path.exists():
        emb = np.load(emb_path)
    else:
        logger.info("Encode corpus (một lần, lưu cache)…")
        emb = bi.encode(texts, batch_size=64, normalize_embeddings=True,
                        show_progress_bar=True, convert_to_numpy=True).astype(np.float32)
        np.save(emb_path, emb)
    emb_t = torch.from_numpy(emb).to(device)
    # Văn bản hết hiệu lực: trừ điểm dense đi rất xa để topk không bao giờ chọn
    dead = torch.tensor([0.0 if d["retrievable"] else -1e4 for d in docs], device=device)
    logger.info(f"Lấy thêm được từ {sum(d['retrievable'] for d in docs)}/{len(docs)} Điều còn hiệu lực")
    ce = CrossEncoder("BAAI/bge-reranker-large", device=device, max_length=512,
                      model_kwargs={"torch_dtype": torch.float16} if device == "cuda" else {})

    pool, keep = args.pool, args.keep
    t0 = time.time()
    with open(CONTEXTS_PATH, "a", encoding="utf-8") as out:
        for n, it in enumerate(todo, 1):
            q = it["question"]
            src = it["source_doc_id"]
            src_i = by_id.get(src)
            src_hash_root = docs[src_i]["dup_of"] or src if src_i is not None else None

            qv = torch.from_numpy(bi.encode([q], normalize_embeddings=True,
                                            convert_to_numpy=True)).to(device)
            dense = torch.topk((emb_t @ qv[0]) + dead, pool).indices.tolist()
            sparse = [i for i in bm25.top(q, pool * 3) if docs[i]["retrievable"]][:pool]
            rrf = collections.defaultdict(float)
            for lst in (dense, sparse):
                for rank, i in enumerate(lst):
                    rrf[i] += 1 / (60 + rank)
            cand = []
            for i, _ in sorted(rrf.items(), key=lambda x: -x[1]):
                d = docs[i]
                root = d["dup_of"] or d["id"]
                if d["id"] == src or root == src_hash_root:
                    continue                  # Điều nguồn (hoặc bản trùng của nó) luôn có sẵn
                cand.append(i)
            cand = cand[:pool]
            scores = ce.predict([(q, texts[i]) for i in cand], batch_size=32,
                                show_progress_bar=False, activation_fn=torch.nn.Sigmoid())
            ranked = sorted(zip(cand, scores.tolist()), key=lambda x: -x[1])
            # Bỏ bản trùng nội dung giữa các Điều lấy thêm
            picked, roots = [], set()
            for i, s in ranked:
                root = docs[i]["dup_of"] or docs[i]["id"]
                if root in roots:
                    continue
                roots.add(root)
                picked.append({"id": docs[i]["id"], "score": round(float(s), 4)})
                if len(picked) >= keep:
                    break
            src_score = None
            if src_i is not None:
                src_score = round(float(ce.predict([(q, texts[src_i])],
                                                   activation_fn=torch.nn.Sigmoid())[0]), 4)
            out.write(json.dumps({"item_id": it["item_id"], "source_doc_id": src,
                                  "source_score": src_score, "extra": picked},
                                 ensure_ascii=False) + "\n")
            if n % 200 == 0:
                out.flush()
                rate = n / (time.time() - t0)
                logger.info(f"  {n}/{len(todo)} — {rate:.1f} câu/s, "
                            f"còn ~{(len(todo) - n) / rate / 60:.0f} phút")
    logger.info(f"Xong retrieve → {CONTEXTS_PATH}")
    return 0


# ══════════════════════════════════════════════════════════════════
# Dựng prompt
# ══════════════════════════════════════════════════════════════════

def build_context(ctx: dict, docs_by_id: dict, min_score: float, max_extra: int) -> tuple[str, list[str]]:
    """Điều nguồn luôn đứng đầu; thêm các Điều có điểm rerank ≥ min_score."""
    blocks, ids = [], []
    src = docs_by_id.get(ctx["source_doc_id"])
    if src:
        blocks.append(doc_block(src, SOURCE_CHARS))
        ids.append(src["id"])
    for e in ctx["extra"]:
        if len(ids) - 1 >= max_extra:
            break
        if e["score"] < min_score:
            continue
        d = docs_by_id.get(e["id"])
        if d:
            blocks.append(doc_block(d, EXTRA_CHARS))
            ids.append(d["id"])
    return "\n\n---\n\n".join(blocks), ids


def teacher_messages(item: dict, context: str) -> list[dict]:
    key = style_key(item["final_label"], item["metadata"]["narrow_mode"])
    return [
        {"role": "system", "content": TEACHER_SYSTEM.format(style=STYLE[key])},
        {"role": "user", "content": USER_TEMPLATE.format(context=context, question=item["question"])},
    ]


LEVEL_RE = re.compile(r"\n?\s*\**\s*MỨC\s*(?:ĐỘ)?\s*\**\s*:\s*\**\s*(full|partial|general)\b\**\s*$",
                      re.IGNORECASE)


def parse_answer(raw: str) -> tuple[str, str | None]:
    text = (raw or "").strip()
    m = LEVEL_RE.search(text)
    if not m:
        return text, None
    return text[:m.start()].rstrip(), m.group(1).lower()


# Lộ nhãn prompt hoặc lời chào/xưng hô — student sẽ học lại y nguyên, nên coi là lỗi
# (câu bị lỗi được sinh lại, tối đa 2 lần).
STYLE_BAD_RE = re.compile(
    r"\[CONTEXT\]|ngữ cảnh|(?:điều luật|quy định|tài liệu|văn bản)[^.\n]{0,20}được cung cấp"
    r"|^\s*(?:Chào|Xin chào|Kính gửi)|với tư cách là luật sư|\btôi xin\b",
    re.IGNORECASE | re.MULTILINE)


# Gemma vẫn viết "[CONTEXT]" dù prompt cấm (~16% câu, gần hết là mức partial).
# Loại cả câu thì dataset mất đúng loại câu trả lời "thiếu căn cứ" → thay chữ.
_CTX_FIX = [
    (re.compile(r"(trong|tại|theo|ở)\s+(?:phần\s+)?\[CONTEXT\]", re.IGNORECASE), r"\1 các quy định nêu trên"),
    (re.compile(r"\[CONTEXT\]", re.IGNORECASE), "các quy định nêu trên"),
]


_DOUBLE = re.compile(
    r"(?:các\s+|những\s+)?(?:quy định|điều luật|điều khoản|văn bản)(?:\s+pháp luật)?\s+"
    r"(?:có\s+)?(?:trong|tại|ở)\s+các quy định nêu trên", re.IGNORECASE)


def sanitize(text: str) -> tuple[str, bool]:
    new = text
    for pat, rep in _CTX_FIX:
        new = pat.sub(rep, new)
    # "các quy định trong [CONTEXT]" → "các quy định trong các quy định nêu trên" → gộp lại
    new = _DOUBLE.sub("các quy định nêu trên", new)
    # đầu câu thì viết hoa
    new = re.sub(r"(^|[.!?:]\s+|\n\s*(?:[-*]\s+)?)(các quy định nêu trên)",
                 lambda m: m.group(1) + "C" + m.group(2)[1:], new)
    return new, new != text


def has_block_loop(text: str) -> bool:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= 80]
    return any(c >= 3 for c in collections.Counter(paras).values())


# ══════════════════════════════════════════════════════════════════
# generate
# ══════════════════════════════════════════════════════════════════

def _free_gb() -> float:
    import psutil
    return psutil.virtual_memory().available / 2**30


def cmd_generate(args):
    import openai

    items = {it["item_id"]: it for it in load_items()}
    ctxs = {c["item_id"]: c for c in read_jsonl(CONTEXTS_PATH)}
    done = {(r["item_id"], r["version"]) for r in read_jsonl(ANSWERS_PATH) if r.get("answer")}
    failed = collections.Counter(r["item_id"] for r in read_jsonl(ANSWERS_PATH)
                                 if not r.get("answer") and r.get("version") == ANSWER_PROMPT_VERSION)

    if args.ids == "pilot":
        order = json.loads(PILOT_PATH.read_text(encoding="utf-8"))
    else:
        # test cuối cùng: train/val là dữ liệu huấn luyện, cần trước
        rank = {"train": 0, "validation": 1, "test": 2}
        order = sorted(items, key=lambda i: (rank[items[i]["_split"]], i))
    todo = [i for i in order
            if (i, ANSWER_PROMPT_VERSION) not in done and i in ctxs and failed[i] < 3]
    missing_ctx = sum(1 for i in order if i not in ctxs)
    if missing_ctx:
        logger.warning(f"{missing_ctx} câu chưa có context (chạy `retrieve` trước) — bỏ qua")
    logger.info(f"Cần sinh {len(todo)} câu (version {ANSWER_PROMPT_VERSION}); "
                f"đã có {len(done)}; mẻ này tối đa {args.max_items or 'hết'}")
    if not todo:
        return 3
    if args.max_items:
        todo = todo[:args.max_items]

    docs_by_id = {d["id"]: d for d in load_corpus()}
    client = openai.OpenAI(base_url=TEACHER_URL, api_key="lm-studio",
                           timeout=args.timeout, max_retries=1)
    lock = threading.Lock()
    out = open(ANSWERS_PATH, "a", encoding="utf-8")

    def write(rec):
        with lock:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            os.fsync(out.fileno())

    def run_one(iid):
        it = items[iid]
        context, ctx_ids = build_context(ctxs[iid], docs_by_id, args.min_score, args.max_extra)
        msgs = teacher_messages(it, context)
        rec = {"item_id": iid, "version": ANSWER_PROMPT_VERSION, "model": TEACHER_MODEL,
               "context_ids": ctx_ids, "answer": None, "level": None, "error": None}
        t = time.time()
        try:
            resp = client.chat.completions.create(
                model=TEACHER_MODEL, messages=msgs, temperature=args.temperature,
                max_tokens=args.max_tokens, extra_body={"reasoning_effort": "none"})
            ch = resp.choices[0]
            text, level = parse_answer(ch.message.content or "")
            text, rec["sanitized"] = sanitize(text)
            rec["seconds"] = round(time.time() - t, 1)
            if resp.usage:
                rec["tokens"] = [resp.usage.prompt_tokens, resp.usage.completion_tokens]
            if ch.finish_reason == "length":
                rec["error"] = "truncated"
            elif has_block_loop(text):
                rec["error"] = "loop"
            elif len(text) < 60:
                rec["error"] = "too_short"
            elif level is None:
                rec["error"] = "no_level"
            elif STYLE_BAD_RE.search(text):
                rec["error"] = "style:" + STYLE_BAD_RE.search(text).group(0)[:30]
            if rec["error"]:
                rec["raw"] = (ch.message.content or "")[-500:]
            else:
                rec["answer"], rec["level"] = text, level
        except Exception as e:                       # noqa: BLE001 — ghi lại, không dừng cả mẻ
            rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            rec["seconds"] = round(time.time() - t, 1)
        write(rec)
        return rec

    rc, n_ok, n_err, t0 = 0, 0, 0, time.time()
    queue = list(todo)
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        running = set()
        while queue or running:
            while queue and len(running) < args.parallel and rc == 0:
                if STOP_PATH.exists():
                    logger.warning("Thấy file STOP — không nhận câu mới")
                    rc = 5
                    break
                free = _free_gb()
                if free < args.min_free_gb:
                    logger.warning(f"RAM trống {free:.1f} GB < {args.min_free_gb} — dừng mẻ")
                    rc = 4
                    break
                running.add(ex.submit(run_one, queue.pop(0)))
            if not running:
                break
            fin, running = wait(running, return_when=FIRST_COMPLETED)
            for f in fin:
                r = f.result()
                if r["answer"]:
                    n_ok += 1
                else:
                    n_err += 1
                    logger.warning(f"  {r['item_id']}: {r['error']}")
                n = n_ok + n_err
                if n % 10 == 0:
                    el = time.time() - t0
                    logger.info(f"  {n}/{len(todo)} — ok {n_ok}, lỗi {n_err}, "
                                f"{el / n:.1f}s/câu, RAM trống {_free_gb():.1f} GB")
    out.close()
    el = time.time() - t0
    logger.info(f"Mẻ xong: ok {n_ok}, lỗi {n_err}, {el / 60:.1f} phút "
                f"({el / max(1, n_ok + n_err):.1f}s/câu)")
    return rc


# ══════════════════════════════════════════════════════════════════
# pilot / check / export
# ══════════════════════════════════════════════════════════════════

def cmd_pilot(args):
    """Chọn n câu train, chia đều 4 nhóm (broad/narrow × citation/situation)."""
    items = [it for it in load_items() if it["_split"] == "train"]
    groups = collections.defaultdict(list)
    for it in items:
        groups[(it["final_label"], it["metadata"]["narrow_mode"])].append(it["item_id"])
    rng = random.Random(args.seed)
    ids = []
    for key in sorted(groups):
        ids += rng.sample(sorted(groups[key]), args.n // len(groups))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PILOT_PATH.write_text(json.dumps(ids, indent=1), encoding="utf-8")
    logger.info(f"{len(ids)} câu pilot → {PILOT_PATH}")
    return 0


RE_DIEU = re.compile(r"Điều\s+(\d+[a-zđ]?)", re.IGNORECASE)


def citation_check(answer: str, context: str) -> dict:
    """Số Điều nhắc trong câu trả lời có xuất hiện trong context không (thô, chỉ xét số)."""
    cited = set(RE_DIEU.findall(answer))
    in_ctx = set(RE_DIEU.findall(context))
    bad = sorted(cited - in_ctx)
    return {"n_cited": len(cited), "not_in_context": bad}


def latest_answers() -> dict:
    best = {}
    for r in read_jsonl(ANSWERS_PATH):
        if r.get("version") != ANSWER_PROMPT_VERSION:
            continue
        if r.get("answer") or r["item_id"] not in best:
            best[r["item_id"]] = r
    return best


def cmd_check(args):
    items = {it["item_id"]: it for it in load_items()}
    docs_by_id = {d["id"]: d for d in load_corpus()}
    ans = latest_answers()
    if args.ids == "pilot":
        keep = set(json.loads(PILOT_PATH.read_text(encoding="utf-8")))
        ans = {k: v for k, v in ans.items() if k in keep}
    stat = collections.defaultdict(collections.Counter)
    secs, words, bad_cite = [], collections.defaultdict(list), collections.Counter()
    for iid, r in ans.items():
        it = items[iid]
        g = style_key(it["final_label"], it["metadata"]["narrow_mode"])
        if not r.get("answer"):
            stat[g]["error:" + str(r.get("error"))[:30]] += 1
            continue
        stat[g][r["level"]] += 1
        secs.append(r.get("seconds", 0))
        words[g].append(len(r["answer"].split()))
        ctx = "\n".join(doc_block(docs_by_id[i], SOURCE_CHARS) for i in r["context_ids"] if i in docs_by_id)
        cc = citation_check(r["answer"], ctx)
        if cc["not_in_context"]:
            bad_cite[g] += 1
    print(f"\n{len(ans)} câu, version {ANSWER_PROMPT_VERSION}")
    for g in sorted(stat):
        w = words[g]
        print(f"  {g:18s} {dict(stat[g])}  | từ TB {sum(w) / max(1, len(w)):.0f}"
              f" | trích Điều ngoài context: {bad_cite[g]}")
    if secs:
        secs.sort()
        print(f"  thời gian/câu: trung vị {secs[len(secs) // 2]}s, max {secs[-1]}s")
    return 0


def cmd_export(args):
    items = load_items()
    ans = latest_answers()
    docs_by_id = {d["id"]: d for d in load_corpus()}
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stats = {}
    for split, fname in SPLITS.items():
        rows, dropped = [], collections.Counter()
        for it in items:
            if it["_split"] != split:
                continue
            r = ans.get(it["item_id"])
            if not r or not r.get("answer"):
                dropped["no_answer"] += 1
                continue
            ctx_docs = [docs_by_id[i] for i in r["context_ids"] if i in docs_by_id]
            context = "\n\n---\n\n".join(
                doc_block(d, SOURCE_CHARS if k == 0 else EXTRA_CHARS) for k, d in enumerate(ctx_docs))
            cc = citation_check(r["answer"], context)
            if cc["not_in_context"]:
                dropped["citation_outside_context"] += 1
                continue
            rows.append({
                "item_id": it["item_id"], "pair_id": it["pair_id"],
                "question": it["question"], "context": context,
                "answer": sanitize(r["answer"])[0], "answer_level": r["level"],
                "final_label": it["final_label"],
                "narrow_mode": it["metadata"]["narrow_mode"],
                "scope": it["metadata"].get("scope", ""),
                "source_doc_id": it["source_doc_id"],
                "context_doc_ids": r["context_ids"],
                "teacher_model": r["model"],
            })
        with open(EXPORT_DIR / fname, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
        stats[split] = {"n": len(rows), "dropped": dict(dropped),
                        "levels": dict(collections.Counter(r["answer_level"] for r in rows))}
        logger.info(f"{split}: {len(rows)} câu, loại {dict(dropped)}")
    (EXPORT_DIR / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("retrieve")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--pool", type=int, default=30, help="Ứng viên mỗi nhánh BM25/dense")
    p.add_argument("--keep", type=int, default=5, help="Số Điều lấy thêm lưu lại (lọc lúc generate)")

    p = sub.add_parser("pilot")
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--seed", type=int, default=42)

    p = sub.add_parser("generate")
    p.add_argument("--ids", default="all", choices=["all", "pilot"])
    p.add_argument("--max-items", type=int, default=0)
    p.add_argument("--parallel", type=int, default=2)
    p.add_argument("--min-score", type=float, default=0.3, help="Ngưỡng rerank cho Điều lấy thêm")
    p.add_argument("--max-extra", type=int, default=3)
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--max-tokens", type=int, default=1800)
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--min-free-gb", type=float, default=4.0)

    p = sub.add_parser("check")
    p.add_argument("--ids", default="all", choices=["all", "pilot"])

    sub.add_parser("export")

    args = ap.parse_args()
    fn = {"retrieve": cmd_retrieve, "pilot": cmd_pilot, "generate": cmd_generate,
          "check": cmd_check, "export": cmd_export}[args.cmd]
    sys.exit(fn(args) or 0)


if __name__ == "__main__":
    main()
