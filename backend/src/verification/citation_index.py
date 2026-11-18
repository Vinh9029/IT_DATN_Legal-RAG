"""
Chỉ mục tra cứu cho verifier (SQLite, read-only).

Ba bảng, dựng bởi `scripts/offline_rag/06_build_citation_index.py`:
- documents: MỌI văn bản trong metadata HF (171k, gồm cả văn bản hết hiệu lực —
  retrieval đã lọc bỏ chúng nên verifier không thể chỉ tra trên chunks.jsonl).
- articles: nội dung từng Điều của các văn bản có trong KB (chunks.jsonl) —
  đúng corpus mà retrieval đang dùng.
- aliases: tên gọi → doc_id ("bộ luật dân sự 2015" → 95942).
"""

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.verification.normalize import normalize_so_hieu, normalize_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    so_hieu TEXT,
    so_hieu_norm TEXT,
    loai TEXT,
    title TEXT,
    co_quan TEXT,
    ngay_ban_hanh TEXT,
    ngay_hieu_luc TEXT,
    ngay_het_hieu_luc TEXT,
    tinh_trang TEXT,
    in_kb INTEGER DEFAULT 0,
    n_articles INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS articles (
    doc_id TEXT NOT NULL,
    dieu TEXT NOT NULL,
    content TEXT,
    PRIMARY KEY (doc_id, dieu)
);
CREATE TABLE IF NOT EXISTS aliases (
    alias TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    PRIMARY KEY (alias, doc_id)
);
CREATE TABLE IF NOT EXISTS build_info (key TEXT PRIMARY KEY, value TEXT);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_documents_so_hieu ON documents(so_hieu_norm);
"""


@dataclass(frozen=True)
class DocRecord:
    doc_id: str
    so_hieu: str
    loai: str
    title: str
    co_quan: str
    ngay_hieu_luc: str
    ngay_het_hieu_luc: str
    tinh_trang: str
    in_kb: bool
    n_articles: int


_DOC_COLS = ("doc_id, so_hieu, loai, title, co_quan, ngay_hieu_luc, "
             "ngay_het_hieu_luc, tinh_trang, in_kb, n_articles")


def _doc(row) -> DocRecord:
    return DocRecord(row[0], row[1] or "", row[2] or "", row[3] or "", row[4] or "",
                     row[5] or "", row[6] or "", row[7] or "", bool(row[8]), int(row[9] or 0))


class CitationIndex:
    """Truy vấn read-only; an toàn khi gọi từ nhiều thread (mỗi thread một connection)."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Chưa có chỉ mục trích dẫn: {self.db_path}. "
                "Chạy scripts/offline_rag/06_build_citation_index.py trước."
            )
        self._local = threading.local()
        self._alias_names: Optional[list[str]] = None

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True,
                                   check_same_thread=False)
            self._local.conn = conn
        return conn

    # ── Văn bản ───────────────────────────────────────────────
    def get_doc(self, doc_id: str) -> Optional[DocRecord]:
        row = self._conn().execute(
            f"SELECT {_DOC_COLS} FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        return _doc(row) if row else None

    def docs_by_so_hieu(self, so_hieu: str) -> list[DocRecord]:
        key = normalize_so_hieu(so_hieu)
        if not key:
            return []
        rows = self._conn().execute(
            f"SELECT {_DOC_COLS} FROM documents WHERE so_hieu_norm = ?", (key,)).fetchall()
        return [_doc(r) for r in rows]

    def docs_by_alias(self, alias: str) -> list[DocRecord]:
        rows = self._conn().execute(
            f"SELECT {', '.join('d.' + c.strip() for c in _DOC_COLS.split(','))} "
            "FROM aliases a JOIN documents d ON d.doc_id = a.doc_id WHERE a.alias = ?",
            (normalize_text(alias),)).fetchall()
        return [_doc(r) for r in rows]

    def alias_names(self) -> list[str]:
        """Mọi tên gọi, dài trước — để dò tên văn bản trong câu trả lời (khớp dài nhất)."""
        if self._alias_names is None:
            rows = self._conn().execute("SELECT DISTINCT alias FROM aliases").fetchall()
            self._alias_names = sorted((r[0] for r in rows), key=len, reverse=True)
        return self._alias_names

    # ── Điều ─────────────────────────────────────────────────
    def get_article(self, doc_id: str, dieu: str) -> Optional[str]:
        row = self._conn().execute(
            "SELECT content FROM articles WHERE doc_id = ? AND dieu = ?",
            (doc_id, str(dieu))).fetchone()
        return row[0] if row else None

    def build_info(self) -> dict:
        return dict(self._conn().execute("SELECT key, value FROM build_info").fetchall())
