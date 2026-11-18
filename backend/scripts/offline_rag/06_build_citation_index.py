"""
Dựng chỉ mục tra cứu cho Citation Verification (Stage 6).

Nguồn:
- Metadata HF (`th1nhng0/vietnamese-legal-documents`, config `metadata`, 171k văn
  bản, GỒM CẢ văn bản hết hiệu lực) → bảng documents + aliases. Không dùng
  chunks.jsonl cho phần này vì bước chunking đã bỏ văn bản hết hiệu lực: model
  trích một luật đã hết hiệu lực sẽ bị báo "không tồn tại" thay vì "hết hiệu lực".
- chunks.jsonl (KB của retrieval) → bảng articles. Verifier phải tham chiếu ĐÚNG
  corpus mà retrieval đang dùng.

Output: data/rag/indexes/citation_index.sqlite (ghi file tạm rồi đổi tên).

Chạy từ backend/:
    python scripts/offline_rag/06_build_citation_index.py
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger
from tqdm import tqdm

from config.settings import BASE_DIR, HF_DATASET_NAME, INDEXES_DIR, PROCESSED_DATA_DIR
from src.verification.citation_index import INDEXES, SCHEMA
from src.verification.normalize import aliases_for, nfc, normalize_so_hieu

DIEU_RE = re.compile(r"^\d+[a-zđ]?$")


def _clean(v) -> str:
    s = "" if v is None else str(v).strip()
    return "" if s in ("None", "nan") else nfc(s)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return path.name


def load_documents(conn: sqlite3.Connection) -> int:
    from datasets import load_dataset

    logger.info(f"Đọc metadata: {HF_DATASET_NAME} (config=metadata)")
    ds = load_dataset(HF_DATASET_NAME, "metadata")
    split = ds[list(ds.keys())[0]]

    doc_rows, alias_rows = [], []
    for r in tqdm(split, desc="documents"):
        doc_id = _clean(r.get("id"))
        if not doc_id:
            continue
        so_hieu = _clean(r.get("so_ky_hieu"))
        loai = _clean(r.get("loai_van_ban"))
        title = _clean(r.get("title"))
        ngay_bh = _clean(r.get("ngay_ban_hanh"))
        doc_rows.append((
            doc_id, so_hieu, normalize_so_hieu(so_hieu), loai, title,
            _clean(r.get("co_quan_ban_hanh")), ngay_bh,
            _clean(r.get("ngay_co_hieu_luc")), _clean(r.get("ngay_het_hieu_luc")),
            _clean(r.get("tinh_trang_hieu_luc")),
        ))
        for a in aliases_for(title, loai, so_hieu, ngay_bh):
            alias_rows.append((a, doc_id))

    conn.executemany(
        "INSERT OR REPLACE INTO documents (doc_id, so_hieu, so_hieu_norm, loai, title, co_quan, "
        "ngay_ban_hanh, ngay_hieu_luc, ngay_het_hieu_luc, tinh_trang) VALUES (?,?,?,?,?,?,?,?,?,?)",
        doc_rows)
    conn.executemany("INSERT OR IGNORE INTO aliases (alias, doc_id) VALUES (?, ?)", alias_rows)
    conn.commit()
    logger.info(f"documents={len(doc_rows)} | aliases={len(alias_rows)}")
    return len(doc_rows)


def load_articles(conn: sqlite3.Connection, chunks_path: Path) -> dict:
    """
    Một Điều = một dòng. chunks.jsonl có chunk_id trùng (văn bản sửa đổi trích lại
    "Điều N" của luật khác) → nối các nội dung khác nhau thay vì ghi đè, để kiểm
    "nội dung khớp" không báo sai chỉ vì giữ nhầm một đoạn.
    """
    stats = {"lines": 0, "articles": 0, "skipped_non_article": 0, "bad_json": 0}
    batch = []
    upsert = (
        "INSERT INTO articles (doc_id, dieu, content) VALUES (?, ?, ?) "
        "ON CONFLICT(doc_id, dieu) DO UPDATE SET content = articles.content || char(10) || char(10) "
        "|| excluded.content WHERE instr(articles.content, excluded.content) = 0"
    )
    kb_docs = set()
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="articles"):
            stats["lines"] += 1
            try:
                c = json.loads(line)
            except json.JSONDecodeError:
                stats["bad_json"] += 1
                continue
            doc_id = str(c.get("doc_id") or "")
            if not doc_id:
                continue
            kb_docs.add(doc_id)
            dieu = str(c.get("dieu") or "").strip().lower()
            if not DIEU_RE.match(dieu):
                stats["skipped_non_article"] += 1
                continue
            batch.append((doc_id, dieu, nfc(c.get("content") or "")))
            if len(batch) >= 5000:
                conn.executemany(upsert, batch)
                batch.clear()
    if batch:
        conn.executemany(upsert, batch)
    conn.commit()

    conn.execute("CREATE TEMP TABLE kb(doc_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO kb VALUES (?)", ((d,) for d in kb_docs))
    conn.execute("UPDATE documents SET in_kb = 1 WHERE doc_id IN (SELECT doc_id FROM kb)")
    conn.execute(
        "UPDATE documents SET n_articles = (SELECT COUNT(*) FROM articles a "
        "WHERE a.doc_id = documents.doc_id) WHERE in_kb = 1")
    missing = conn.execute(
        "SELECT COUNT(*) FROM kb WHERE doc_id NOT IN (SELECT doc_id FROM documents)").fetchone()[0]
    conn.commit()
    stats["articles"] = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    stats["kb_docs"] = len(kb_docs)
    stats["kb_docs_without_metadata"] = missing
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--chunks", type=Path, default=PROCESSED_DATA_DIR / "chunks" / "chunks.jsonl")
    ap.add_argument("--out", type=Path, default=INDEXES_DIR / "citation_index.sqlite")
    args = ap.parse_args()

    if not args.chunks.exists():
        logger.error(f"Không thấy {args.chunks}")
        sys.exit(1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".sqlite.tmp")
    if tmp.exists():
        tmp.unlink()

    t0 = time.time()
    conn = sqlite3.connect(tmp)
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")
    conn.executescript(SCHEMA)

    n_docs = load_documents(conn)
    stats = load_articles(conn, args.chunks)
    conn.executescript(INDEXES)

    st = args.chunks.stat()
    info = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hf_dataset": HF_DATASET_NAME,
        "chunks_path": _rel(args.chunks),
        "chunks_size": str(st.st_size),
        "chunks_mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
        "n_documents": str(n_docs),
        **{k: str(v) for k, v in stats.items()},
    }
    conn.executemany("INSERT OR REPLACE INTO build_info VALUES (?, ?)", info.items())
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    os.replace(tmp, args.out)

    logger.info(f"Xong trong {time.time() - t0:.0f}s → {_rel(args.out)}")
    for k, v in info.items():
        logger.info(f"  {k}: {v}")


if __name__ == "__main__":
    main()
