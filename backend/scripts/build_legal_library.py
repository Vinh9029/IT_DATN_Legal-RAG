"""
build_legal_library.py — Dựng dữ liệu cho trang Thư viện pháp luật
===================================================================
Chạy từ thư mục backend/:
    python scripts/build_legal_library.py                       # dựng + nạp mọi văn bản lên Supabase
    python scripts/build_legal_library.py --only bo-luat-dan-su-2015
    python scripts/build_legal_library.py --dry-run             # chỉ đọc + kiểm tra số Điều
    python scripts/build_legal_library.py --sql-out <thư mục>   # chưa có service key: xuất .sql dán vào SQL Editor

Đầu vào : data/library/manifest.json (danh mục + metadata) và file gốc mà
          manifest trỏ tới (đường dẫn tương đối so với data/).
Đầu ra  : bảng "LegalRAG".library_documents (metadata + mục lục) và
          "LegalRAG".library_articles (từng Điều) — schema ở frontend/src/database/library_schema.sql.
          Ghi bằng SUPABASE_SERVICE_ROLE_KEY trong backend/.env (bỏ qua RLS; khách chỉ đọc được).

Thêm một văn bản: thả file gốc vào data/, thêm một mục vào manifest, chạy lại.
Thêm một ĐỊNH DẠNG: viết một hàm `path -> list[Line]` rồi đăng ký vào `READERS`;
phần dựng cây phía sau không cần biết file gốc là gì.

Vì sao không dùng lại `corpus_loader._read_pdf`: loader đó phục vụ sinh QA nên
chỉ cần text phẳng, và bước nối dòng của nó dính tiêu đề Điều vào câu đầu thân
Điều ở ~20% số Điều ("Điều 11. Các phương thức bảo vệ quyền dân sự Khi quyền...").
Hiển thị cho người đọc thì không chấp nhận được, nên ở đây đọc theo FONT: bản
Công báo in đậm mọi tiêu đề, còn thụt lề đầu dòng đánh dấu đầu đoạn.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
MANIFEST_PATH = DATA_DIR / "library" / "manifest.json"

SCHEMA_VERSION = 1


# ══════════════════════════════════════════════════════════════════
# Đọc file gốc → danh sách dòng
# ══════════════════════════════════════════════════════════════════

@dataclass
class Line:
    text: str
    bold: bool          # cả dòng in đậm → ứng viên tiêu đề
    indent: bool        # thụt lề đầu dòng → mở đầu một đoạn mới
    source_index: int   # thứ tự file trong `sources` (phần 1, 2, 3...)


# Chữ ký số của Cổng TTĐT Chính phủ in cỡ ~5pt ở góc trang; chữ thân văn bản 13-14pt
_MIN_FONT_SIZE = 9
# Lệch so với lề trái của trang quá ngưỡng này (pt) mới tính là thụt đầu dòng
_INDENT_THRESHOLD = 10

# Dòng của bản in, không phải của văn bản luật
_NOISE_RE = re.compile(
    r"^(?:CÔNG BÁO\s*/\s*Số"
    r"|\d{1,4}$"
    r"|\((?:Xem tiếp|Tiếp theo) Công báo"
    r"|PHẦN VĂN BẢN QUY PHẠM PHÁP LUẬT$"
    r"|CHỦ TỊCH NƯỚC\s*-\s*QUỐC HỘI$"
    r"|Ký bởi:|Email:|Cơ quan:|Thời gian ký:)",
    re.IGNORECASE,
)
# Dòng nhắc lại số hiệu ở đầu mỗi phần Công báo nối tiếp:
# "Luật số 91/2015/QH13 ngày 24 tháng 11 năm 2015 Bộ luật dân sự"
_CONTINUATION_BANNER_RE = re.compile(r"^Luật số \S+ ngày \d{1,2} tháng \d{1,2} năm \d{4}\b")


def _span_is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or "bold" in span["font"].lower()


def read_pdf_lines(path: Path, source_index: int) -> list[Line]:
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf

    out: list[Line] = []
    with pymupdf.open(str(path)) as document:
        margin = None
        for page in document:
            raw: list[tuple[str, bool, float]] = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    spans = [s for s in line["spans"] if s["size"] >= _MIN_FONT_SIZE and s["text"].strip()]
                    if not spans:
                        continue
                    text = re.sub(r"\s+", " ", "".join(s["text"] for s in spans)).strip()
                    # Bản gốc có chỗ thiếu dấu cách sau điểm ("g)Thay đổi họ...")
                    text = re.sub(r"^([a-zđ])\)(?=\S)", r"\1) ", text)
                    if not text or _NOISE_RE.match(text):
                        continue
                    raw.append((text, all(_span_is_bold(s) for s in spans), spans[0]["bbox"][0]))

            # Lề trái đo theo dòng DÀI (căn đều hai bên nên luôn chạm lề), từng
            # trang một vì trang chẵn/lẻ của Công báo lệch lề nhau.
            long_x = [x for text, _, x in raw if len(text) >= 60]
            if long_x:
                margin = min(long_x)
            for text, bold, x in raw:
                indent = margin is not None and x - margin > _INDENT_THRESHOLD
                out.append(Line(text, bold, indent, source_index))
    return out


# Thêm định dạng mới (docx, html...) = thêm một reader trả về list[Line]
READERS = {
    ".pdf": read_pdf_lines,
}


# ══════════════════════════════════════════════════════════════════
# Dòng → cây cấu trúc
# ══════════════════════════════════════════════════════════════════

# Cấp cấu trúc từ ngoài vào trong. Văn bản nào thiếu cấp nào (Luật thường không
# có Phần, Nghị định thường chỉ có Chương) thì cây tự bỏ qua cấp đó.
LEVELS: list[tuple[str, re.Pattern]] = [
    ("part", re.compile(r"^Phần thứ\s+[\wÀ-ỹ]+(?:\s+[\wÀ-ỹ]+)?$", re.IGNORECASE)),
    ("chapter", re.compile(r"^Chương\s+[IVXLCDM]+[a-z]?$")),
    ("section", re.compile(r"^Mục\s+\d+[a-z]?$")),
    ("subsection", re.compile(r"^Tiểu mục\s+\d+[a-z]?$")),
]
_LEVEL_RANK = {name: rank for rank, (name, _) in enumerate(LEVELS)}

_ARTICLE_RE = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*[.:]\s*(.*)$")
# Câu kết "Bộ luật này đã được Quốc hội ... thông qua" mở đầu phần chữ ký
_CLOSING_RE = re.compile(r"^(?:Bộ luật|Luật|Pháp lệnh|Nghị quyết) này đã được .{0,40}(?:Quốc hội|Ủy ban)")
# Đầu khoản/điểm/gạch đầu dòng luôn mở đoạn mới, kể cả khi PDF không thụt lề
_PARAGRAPH_START_RE = re.compile(r"^(?:\d+[a-z]?\.\s|[a-zđ]\)\s|[-–—•]\s)")


def _heading_level(line: Line) -> str | None:
    if not line.bold:
        return None
    for name, pattern in LEVELS:
        if pattern.match(line.text):
            return name
    return None


@dataclass
class Builder:
    root: list = field(default_factory=list)
    stack: list = field(default_factory=list)  # [(level, node)]
    preamble: list = field(default_factory=list)
    closing: list = field(default_factory=list)
    article: dict | None = None
    seen_structure: bool = False
    mode: str = "preamble"  # preamble | body | closing

    # ── chỗ gắn node mới ────────────────────────────────────
    def _container(self) -> list:
        return self.stack[-1][1]["children"] if self.stack else self.root

    def open_heading(self, level: str, label: str) -> dict:
        rank = _LEVEL_RANK[level]
        # Mỗi phần Công báo nối tiếp in lại "Phần thứ ba / Chương XV" đang dở:
        # trùng nhãn với node đang mở ở cùng cấp thì là nhắc lại, không mở mới.
        for open_level, node in self.stack:
            if open_level == level and node["label"] == label:
                return node
        while self.stack and _LEVEL_RANK[self.stack[-1][0]] >= rank:
            self.stack.pop()
        node = {"type": level, "label": label, "title": "", "children": []}
        self._container().append(node)
        self.stack.append((level, node))
        self.article = None
        return node

    def open_article(self, number: str, title: str) -> dict:
        node = {"type": "article", "number": number, "title": title, "paragraphs": []}
        self._container().append(node)
        self.article = node
        return node


def _append_text(paragraphs: list[str], line: Line) -> None:
    if not paragraphs or line.indent or _PARAGRAPH_START_RE.match(line.text):
        paragraphs.append(line.text)
    else:
        paragraphs[-1] = f"{paragraphs[-1]} {line.text}"


def build_tree(lines: list[Line]) -> Builder:
    b = Builder()
    # Node vừa mở mà tiêu đề có thể còn tràn sang dòng in đậm kế tiếp
    title_target: dict | None = None
    title_key = ""

    for line in lines:
        text = line.text
        if line.source_index > 0 and _CONTINUATION_BANNER_RE.match(text):
            continue

        if b.mode == "closing":
            _append_text(b.closing, line)
            continue
        if _CLOSING_RE.match(text):
            b.mode = "closing"
            title_target = None
            _append_text(b.closing, line)
            continue

        level = _heading_level(line)
        if level:
            title_target = b.open_heading(level, text)
            # Nhắc lại ở phần nối tiếp: tiêu đề đã có, bỏ qua dòng tiêu đề lặp
            title_key = "skip" if title_target["title"] else "title"
            b.mode = "body"
            continue

        match = _ARTICLE_RE.match(text) if line.bold else None
        if match:
            title_target = b.open_article(match.group(1), match.group(2).strip())
            title_key = "title"
            b.mode = "body"
            continue

        if line.bold and title_target is not None:
            if title_key == "title":
                title_target["title"] = f"{title_target['title']} {text}".strip()
            continue
        title_target = None

        if b.mode == "preamble":
            # Bỏ khối quốc hiệu/tên cơ quan; phần dẫn chiếu bắt đầu từ "Căn cứ"
            if b.preamble or text.startswith("Căn cứ"):
                _append_text(b.preamble, line)
            continue
        if b.article is not None:
            _append_text(b.article["paragraphs"], line)
        # Dòng thường nằm giữa tiêu đề cấu trúc và Điều đầu tiên: không có ở bản
        # Công báo; nếu có thì bỏ qua thay vì đoán nhét vào đâu.

    return b


# ══════════════════════════════════════════════════════════════════
# Kiểm tra + xuất
# ══════════════════════════════════════════════════════════════════

def _walk_articles(nodes: list):
    for node in nodes:
        if node["type"] == "article":
            yield node
        else:
            yield from _walk_articles(node["children"])


def _count(nodes: list, level: str) -> int:
    total = 0
    for node in nodes:
        if node["type"] == level:
            total += 1
        if node["type"] != "article":
            total += _count(node["children"], level)
    return total


def _article_sort_key(number: str) -> tuple[int, str]:
    m = re.match(r"(\d+)(.*)", number)
    return (int(m.group(1)), m.group(2)) if m else (0, number)


def validate(law_id: str, tree: list, expected: int | None) -> list[str]:
    warnings: list[str] = []
    articles = list(_walk_articles(tree))
    numbers = [a["number"] for a in articles]

    if expected and len(numbers) != expected:
        warnings.append(f"có {len(numbers)} Điều, manifest khai {expected}")
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1}, key=_article_sort_key)
    if duplicates:
        warnings.append(f"Điều trùng số: {', '.join(duplicates[:10])}")
    plain = [int(n) for n in numbers if n.isdigit()]
    missing = sorted(set(range(1, max(plain) + 1)) - set(plain)) if plain else []
    if missing:
        warnings.append(f"thiếu Điều: {', '.join(map(str, missing[:15]))}")
    empty = [a["number"] for a in articles if not a["paragraphs"]]
    if empty:
        warnings.append(f"Điều không có nội dung: {', '.join(empty[:10])}")
    untitled = [a["number"] for a in articles if not a["title"]]
    if untitled:
        warnings.append(f"Điều không có tiêu đề: {', '.join(untitled[:10])}")

    for w in warnings:
        logger.warning(f"[{law_id}] {w}")
    return warnings


# Trường của manifest được chép sang dữ liệu xuất (cột của library_documents)
META_FIELDS = (
    "id", "title", "short_title", "so_hieu", "loai_van_ban", "co_quan_ban_hanh",
    "ngay_ban_hanh", "ngay_hieu_luc", "tinh_trang", "linh_vuc", "summary",
    "version_note", "aliases",
)


def build_law(entry: dict) -> dict:
    lines: list[Line] = []
    for index, rel in enumerate(entry["sources"]):
        path = DATA_DIR / rel
        if not path.exists():
            raise FileNotFoundError(f"[{entry['id']}] không thấy file nguồn: data/{rel}")
        reader = READERS.get(path.suffix.lower())
        if reader is None:
            raise ValueError(f"[{entry['id']}] chưa hỗ trợ định dạng {path.suffix} ({rel})")
        lines.extend(reader(path, index))

    built = build_tree(lines)
    articles = list(_walk_articles(built.root))
    stats = {
        "articles": len(articles),
        "parts": _count(built.root, "part"),
        "chapters": _count(built.root, "chapter"),
        "sections": _count(built.root, "section"),
        "characters": sum(len(p) for a in articles for p in a["paragraphs"]),
    }
    warnings = validate(entry["id"], built.root, entry.get("expected_articles"))

    meta = {k: entry[k] for k in META_FIELDS if k in entry}
    return {
        "schema_version": SCHEMA_VERSION,
        **meta,
        "stats": stats,
        "first_article": articles[0]["number"] if articles else None,
        "last_article": articles[-1]["number"] if articles else None,
        "preamble": built.preamble,
        "structure": built.root,
        "closing": built.closing,
        "_warnings": warnings,
    }


# ══════════════════════════════════════════════════════════════════
# Văn bản đã dựng → dòng của bảng Supabase
# ══════════════════════════════════════════════════════════════════
# Bảng + RLS + hàm tìm kiếm: frontend/src/database/library_schema.sql

SCHEMA = "LegalRAG"


def _toc(nodes: list) -> list:
    """Cây cấu trúc nhưng lá Điều chỉ giữ số — nội dung nằm ở library_articles"""
    out = []
    for node in nodes:
        if node["type"] == "article":
            out.append({"type": "article", "number": node["number"]})
        else:
            out.append({k: node[k] for k in ("type", "label", "title")} | {"children": _toc(node["children"])})
    return out


def _article_rows(law_id: str, nodes: list) -> list[dict]:
    rows: list[dict] = []

    def walk(items: list, path: list[dict]) -> None:
        for node in items:
            if node["type"] == "article":
                rows.append({
                    "document_id": law_id,
                    "number": node["number"],
                    "ordinal": len(rows),
                    "title": node["title"],
                    "paragraphs": node["paragraphs"],
                    "path": path,
                    # search_title/search_body do Postgres tự sinh (cột GENERATED, hàm library_fold)
                })
            else:
                walk(node["children"], path + [{k: node[k] for k in ("type", "label", "title")}])

    walk(nodes, [])
    return rows


def to_rows(law: dict, sort_order: int) -> tuple[dict, list[dict]]:
    document = {k: law.get(k) for k in META_FIELDS}
    document.update({
        "aliases": law.get("aliases") or [],
        "stats": law["stats"],
        "first_article": law["first_article"],
        "last_article": law["last_article"],
        "preamble": law["preamble"],
        "closing": law["closing"],
        "toc": _toc(law["structure"]),
        "sort_order": sort_order,
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return document, _article_rows(law["id"], law["structure"])


# ── Ghi thẳng lên Supabase (REST + service_role) ─────────────────

class SupabaseWriter:
    """
    Nạp lại một văn bản theo 3 bước để người đang đọc không thấy văn bản dở dang:
    ẩn (published=false) → xoá hết Điều cũ, chèn Điều mới → hiện lại.
    Điều bị bỏ khỏi văn bản ở lần dựng mới cũng biến mất theo nhờ bước xoá.
    """

    BATCH = 200

    def __init__(self, url: str, service_key: str):
        import requests

        self.base = f"{url.rstrip('/')}/rest/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
            "Accept-Profile": SCHEMA,
            "Content-Profile": SCHEMA,
        })

    @staticmethod
    def _check(response, what: str) -> None:
        if response.status_code >= 300:
            raise RuntimeError(f"Supabase từ chối {what}: HTTP {response.status_code} {response.text[:300]}")

    def _send(self, method: str, table: str, what: str, body=None, params=None, prefer="return=minimal") -> None:
        response = self.session.request(
            method,
            f"{self.base}/{table}",
            params=params,
            data=None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Prefer": prefer},
            timeout=60,
        )
        self._check(response, what)

    def upload(self, document: dict, articles: list[dict], publish: bool) -> None:
        doc_id = document["id"]
        self._send("POST", "library_documents", f"ghi văn bản {doc_id}", {**document, "published": False},
                   params={"on_conflict": "id"}, prefer="resolution=merge-duplicates,return=minimal")
        self._send("DELETE", "library_articles", f"xoá Điều cũ của {doc_id}", params={"document_id": f"eq.{doc_id}"})
        for i in range(0, len(articles), self.BATCH):
            self._send("POST", "library_articles", f"chèn Điều {i + 1}-{i + self.BATCH} của {doc_id}", articles[i:i + self.BATCH])
        if publish:
            self._send("PATCH", "library_documents", f"công bố {doc_id}", {"published": True}, params={"id": f"eq.{doc_id}"})


# ── Hoặc xuất file SQL để dán vào Supabase SQL Editor ───────────

# Cột kiểu text[] (còn lại list/dict là jsonb)
_TEXT_ARRAY_COLUMNS = {"aliases", "preamble", "closing", "paragraphs"}


def _sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_value(column: str, value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if column in _TEXT_ARRAY_COLUMNS:
        return "ARRAY[" + ", ".join(_sql_text(v) for v in value) + "]::text[]" if value else "'{}'::text[]"
    if isinstance(value, (dict, list)):
        return _sql_text(json.dumps(value, ensure_ascii=False)) + "::jsonb"
    return _sql_text(str(value))


def to_sql(document: dict, articles: list[dict], publish: bool) -> str:
    table = f'"{SCHEMA}"'
    doc = {**document, "published": False}
    cols = list(doc)
    lines = [
        f"-- {document['title']} ({document['id']}) — sinh bởi scripts/build_legal_library.py",
        "BEGIN;",
        f"INSERT INTO {table}.library_documents ({', '.join(cols)}) VALUES ("
        + ", ".join(_sql_value(c, doc[c]) for c in cols)
        + ") ON CONFLICT (id) DO UPDATE SET "
        + ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id") + ";",
        f"DELETE FROM {table}.library_articles WHERE document_id = {_sql_text(document['id'])};",
    ]
    article_cols = list(articles[0]) if articles else []
    for i in range(0, len(articles), 100):
        values = ",\n".join("(" + ", ".join(_sql_value(c, a[c]) for c in article_cols) + ")" for a in articles[i:i + 100])
        lines.append(f"INSERT INTO {table}.library_articles ({', '.join(article_cols)}) VALUES\n{values};")
    if publish:
        lines.append(f"UPDATE {table}.library_documents SET published = TRUE WHERE id = {_sql_text(document['id'])};")
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


# ══════════════════════════════════════════════════════════════════

def _supabase_credentials() -> tuple[str, str]:
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR / ".env")
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url:
        # Cùng project với frontend — không bắt khai URL hai nơi
        load_dotenv(BACKEND_DIR.parent / "frontend" / ".env")
        url = os.getenv("VITE_SUPABASE_URL", "").strip()
    url = re.sub(r"/rest/v1/?$", "", url.rstrip("/"))
    return url, key


def main() -> int:
    parser = argparse.ArgumentParser(description="Dựng dữ liệu Thư viện pháp luật và nạp lên Supabase")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--only", nargs="*", help="Chỉ dựng các id này")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Chỉ đọc + kiểm tra, không ghi đi đâu")
    mode.add_argument("--sql-out", type=Path, help="Không gọi Supabase, ghi file .sql vào thư mục này để dán vào SQL Editor")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    known = {e["id"] for e in manifest["laws"]}
    if args.only and set(args.only) - known:
        logger.error(f"Không thấy trong manifest: {sorted(set(args.only) - known)}")
        return 1

    writer = None
    if not args.dry_run and not args.sql_out:
        url, key = _supabase_credentials()
        if not url or not key:
            logger.error(
                "Thiếu SUPABASE_SERVICE_ROLE_KEY (và/hoặc SUPABASE_URL) trong backend/.env. "
                "Lấy ở Supabase → Project Settings → API Keys → service_role. "
                "Chưa có key thì chạy với --sql-out <thư mục> rồi dán file .sql vào SQL Editor."
            )
            return 1
        writer = SupabaseWriter(url, key)
    if args.sql_out:
        args.sql_out.mkdir(parents=True, exist_ok=True)

    failed = 0
    # sort_order theo thứ tự trong manifest — xếp lại danh mục = đổi thứ tự trong manifest
    for order, entry in enumerate(manifest["laws"]):
        if args.only and entry["id"] not in args.only:
            continue
        try:
            law = build_law(entry)
        except (FileNotFoundError, ValueError, ImportError) as exc:
            logger.error(str(exc))
            failed += 1
            continue

        warnings = law.pop("_warnings")
        document, articles = to_rows(law, order)
        publish = entry.get("published", True)
        summary = f"[{law['id']}] {law['stats']['articles']} Điều, {law['stats']['chapters']} Chương"
        summary += f" — {len(warnings)} cảnh báo" if warnings else " — OK"

        try:
            if writer:
                writer.upload(document, articles, publish)
                summary += " → đã nạp lên Supabase" + ("" if publish else " (chưa công bố)")
            elif args.sql_out:
                target = args.sql_out / f"{law['id']}.sql"
                target.write_text(to_sql(document, articles, publish), encoding="utf-8")
                summary += f" → {target.name} ({target.stat().st_size / 1024:.0f} KB)"
        except Exception as exc:  # lỗi mạng/quyền: báo rõ văn bản nào hỏng, văn bản khác vẫn chạy
            logger.error(f"[{law['id']}] {exc}")
            failed += 1
            continue
        logger.info(summary)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
