"""
B1 — Trích xuất trích dẫn từ câu trả lời tự do của LLM.

Không ép format: prompt Stage 5 giữ nguyên, nên phải đọc được các dạng model
thật sự viết (đo trên eval_samples.jsonl của generator):
    "Theo Điều 16 Nghị định số 70/2008/NĐ-CP, ..."
    "khoản 1 Điều 15 Nghị định này"
    "Điều 3 của Luật Nuôi con nuôi số 52/2010/QH12"
    "Điều 34 Bộ luật Dân sự 2015" / "Điều 34 BLDS"
    "Điều 20, 21 và 22 ..." / "Điều 20 đến Điều 22"
    "Bộ luật Dân sự 2015 quy định tại Điều 34 ..."   (văn bản đứng TRƯỚC)

Bộ trích xuất chỉ ghi nhận văn bản được nhắc; việc quy ra doc_id là của resolver
(cần chỉ mục), để phần này test được mà không cần SQLite.
"""

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from src.verification.normalize import (
    ABBREVIATIONS, _CONFUSABLES, _TONE_FIX, _TONE_RE, canon_loai, nfc, normalize_text,
)

LOAI_PATTERN = (
    r"(?:Bộ\s+luật|Hiến\s+pháp|Pháp\s+lệnh|Nghị\s+định|Nghị\s+quyết(?:\s+liên\s+tịch)?|"
    r"Thông\s+tư(?:\s+liên\s+tịch)?|Quyết\s+định|Chỉ\s+thị|Luật|TTLT|NĐ|NQ|QĐ|TT)"
)
# "91/2015/QH13", "70/2008/NĐ-CP", "91-2015-QH13"; kiểu cũ "18-CP", "26-LCT/HĐNN8"
SO_HIEU_PATTERN = (
    r"\d{1,4}[/-](?:\d{4}[/-])?[A-ZĐ][A-ZĐa-z0-9]*(?:[-–/][A-ZĐ0-9][A-ZĐa-z0-9]*)*"
)

ART_RE = re.compile(
    rf"""
    (?<!\w)
    (?:điểm\s+(?P<diem>[a-zđ])\s*,?\s*(?:của\s+)?)?
    (?:khoản\s+(?P<khoan>\d+)\s*,?\s*(?:của\s+)?)?
    điều\s+(?P<dieu>\d+[a-zđ]?)(?![\w/])
    (?P<more>(?:\s*(?:,|và|hoặc|đến|tới|-|–)\s*(?:điều\s+)?\d+[a-zđ]?(?![\w/]))*)
    """,
    re.IGNORECASE | re.VERBOSE,
)
_MORE_ITEM_RE = re.compile(r"(,|và|hoặc|đến|tới|-|–)\s*(?:điều\s+)?(\d+[a-zđ]?)", re.IGNORECASE)

# Loại văn bản không phân biệt hoa/thường ("theo nghị định số ..."), còn số hiệu thì
# vẫn phân biệt — chữ hoa trong số hiệu là thứ tách nó khỏi số đếm/ngày tháng.
SO_HIEU_MENTION_RE = re.compile(
    rf"(?<![\w/])(?:(?P<loai>(?i:{LOAI_PATTERN}))\s+(?:(?P<name>[^\n\d,;:.()\[\]]{{1,80}}?)\s+)?(?:số\s+)?)?"
    rf"(?P<so>{SO_HIEU_PATTERN})(?![\w/])"
)
# Không dùng "^": pattern.match(text, pos) đã neo tại pos, còn "^" chỉ khớp đầu chuỗi
SELF_REF_RE = re.compile(rf"\s*,?\s*(?:của\s+)?(?P<loai>{LOAI_PATTERN}|văn\s+bản)\s+này(?!\w)",
                         re.IGNORECASE)
# Khoảng chữ được phép nằm giữa "Điều N" và tên văn bản ngay sau nó
_GAP_OK_RE = re.compile(r"^[\s,(]*(?:(?:của|thuộc|tại|trong)\s+)?(?:văn\s+bản\s+hợp\s+nhất\s+)?$",
                        re.IGNORECASE)
# "Khoản 3 Điều 34 hoặc điểm a khoản 1 Điều 35 của Nghị định này": văn bản ở cuối
# áp cho cả hai cụm nối nhau bằng "và/hoặc/,"
_JOIN_RE = re.compile(r"^\s*(?:,|;|và|hoặc|cùng)\s*$", re.IGNORECASE)
# Tên kẹp giữa loại văn bản và số hiệu không được chứa các từ này (dấu hiệu đã sang câu khác)
_NAME_REJECT_RE = re.compile(
    r"(?<!\w)(?:theo|tại|quy định|nêu|như sau|là|thì|bộ luật|nghị định|thông tư|quyết định|"
    r"nghị quyết|pháp lệnh|chỉ thị)(?!\w)", re.IGNORECASE)
_QUOTE_RE = re.compile(r"[“\"]([^”\"\n]{20,800})[”\"]")
_MAX_RANGE = 15

# Nhãn trình bày và ngày tháng — không phải nội dung nhận định
_LABEL_RE = re.compile(
    r"(?i)(?:trích dẫn|căn cứ pháp lý|cơ sở pháp lý|căn cứ|quy tắc|vấn đề|áp dụng|kết luận|"
    r"\b(?:issue|rule|application|conclusion)\b|ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}|"
    r"năm\s+\d{4})")
# Từ không mang nội dung khi đếm xem câu có phải nhận định thật không
_NON_CONTENT = {
    "theo", "quy", "định", "tại", "của", "và", "các", "số", "này", "về", "trong", "đó", "được",
    "điều", "khoản", "điểm", "luật", "bộ", "nghị", "thông", "tư", "quyết", "văn", "bản", "pháp",
    "lý", "hiện", "hành", "như", "sau", "có", "là", "với", "những", "một", "cũng", "ban",
}
MIN_CONTENT_WORDS = 5


@dataclass
class DocMention:
    start: int
    end: int
    kind: str                       # "so_hieu" | "alias"
    so_hieu: str = ""
    loai: str = ""
    name: str = ""                  # tên gọi đã normalize (alias) hoặc tên kẹp trước số hiệu


@dataclass
class Citation:
    start: int
    end: int
    text: str                       # nguyên văn cụm trích dẫn trong câu trả lời
    dieu: str
    khoan: Optional[str] = None
    diem: Optional[str] = None
    # Văn bản được nhắc rõ ngay sau cụm "Điều N" (nếu có)
    ref: Optional[DocMention] = None
    self_ref: Optional[str] = None  # "Nghị định này" → loai
    # Các văn bản được nhắc TRƯỚC trích dẫn, gần nhất trước (để kế thừa khi thiếu ref)
    preceding: list = field(default_factory=list)
    claim: str = ""                 # câu chứa trích dẫn, đã bỏ các token trích dẫn
    quote: Optional[str] = None     # đoạn trích nguyên văn trong ngoặc kép (nếu có)
    group: int = 0                  # các trích dẫn cùng một cụm "Điều 20, 21 và 22"
    # False khi câu chỉ là dòng liệt kê nguồn ("Trích dẫn: Bộ luật Dân sự 2015") —
    # không có nhận định thì không có gì để kiểm "nội dung khớp"
    substantive: bool = True


class CitationExtractor:
    def __init__(self, alias_names: Iterable[str] = ()):
        names = sorted({a for a in alias_names if a}, key=len, reverse=True)
        names += [a for a in sorted(ABBREVIATIONS, key=len, reverse=True) if a not in names]
        self._alias_re = (
            re.compile(r"(?<!\w)(" + "|".join(re.escape(a) for a in names) + r")"
                       r"(?:\s+(?:năm\s+)?(?P<year>(?:19|20)\d{2}))?(?!\w)")
            if names else None
        )

    # ── tiện ích ──────────────────────────────────────────────
    @staticmethod
    def _search_text(text: str) -> Optional[str]:
        """Bản chữ thường giữ nguyên độ dài để dò tên gọi mà vẫn dùng được offset."""
        s = text.translate(_CONFUSABLES).lower()
        s = _TONE_RE.sub(lambda m: _TONE_FIX[m.group(0)], s)
        return s if len(s) == len(text) else None

    def _doc_mentions(self, text: str) -> list[DocMention]:
        out: list[DocMention] = []
        for m in SO_HIEU_MENTION_RE.finditer(text):
            # regex tên là lazy nên "Nghị định số 70/..." cho name="số"
            name = re.sub(r"(?:^|\s)số$", "", (m.group("name") or "").strip()).strip()
            if name and _NAME_REJECT_RE.search(name):
                # "Luật quy định ... 70/2008/NĐ-CP": phần tên không phải tên văn bản
                start = m.start("so")
                out.append(DocMention(start, m.end(), "so_hieu", so_hieu=m.group("so")))
                continue
            out.append(DocMention(m.start(), m.end(), "so_hieu", so_hieu=m.group("so"),
                                  loai=canon_loai(m.group("loai") or ""),
                                  name=normalize_text(name)))
        search = self._search_text(text) if self._alias_re else None
        if search is not None:
            for m in self._alias_re.finditer(search):
                if any(o.start <= m.start() < o.end for o in out):
                    continue                     # đã nằm trong một mention có số hiệu
                is_abbr = m.group(1) in ABBREVIATIONS
                # Tên ngắn viết thường dễ là danh từ chung ("luật giá", "luật đầu tư"):
                # chỉ nhận khi viết hoa như tên riêng, hoặc tên đủ dài, hoặc là viết tắt
                if not (is_abbr or text[m.start()].isupper() or len(m.group(1).split()) >= 4):
                    continue
                name = ABBREVIATIONS.get(m.group(1), m.group(1))
                if m.group("year"):
                    name = f"{name} {m.group('year')}"
                out.append(DocMention(m.start(), m.end(), "alias", name=name))
        out.sort(key=lambda d: d.start)
        return out

    @staticmethod
    def _sentence_bounds(text: str, pos: int) -> tuple[int, int]:
        """Câu chứa vị trí pos. Dấu chấm sau "Điều 34." / "khoản 2." không phải hết câu."""
        def is_boundary(i: int) -> bool:
            ch = text[i]
            if ch == "\n":
                return True
            if ch in ".!?;" and (i + 1 >= len(text) or text[i + 1].isspace()):
                tail = text[max(0, i - 20):i]
                return not re.search(r"(?:điều|khoản|điểm)\s+\w{1,4}$", tail, re.IGNORECASE)
            return False

        start = pos
        while start > 0 and not is_boundary(start - 1):
            start -= 1
        end = pos
        while end < len(text) and not is_boundary(end):
            end += 1
        return start, min(len(text), end + 1)

    def _strip_citation_tokens(self, s: str) -> str:
        s = ART_RE.sub(" ", s)
        s = SO_HIEU_MENTION_RE.sub(lambda m: " " if m.group("so") else m.group(0), s)
        # tên văn bản ("Bộ luật Dân sự 2015") không phải nội dung nhận định
        search = self._search_text(s) if self._alias_re else None
        if search is not None:
            spans = [(m.start(), m.end()) for m in self._alias_re.finditer(search)]
            for a, b in reversed(spans):
                s = s[:a] + " " + s[b:]
        s = _LABEL_RE.sub(" ", s)
        s = re.sub(r"\[\d+\]|\*\*|__|^#+|^[\s>*•\-–+]+|\(\s*\)", " ", s, flags=re.MULTILINE)
        return re.sub(r"\s+", " ", s).strip(" ,.:;()")

    @staticmethod
    def is_substantive(claim: str) -> bool:
        words = [w for w in re.findall(r"[^\W\d_]+", claim.lower()) if w not in _NON_CONTENT]
        return len(words) >= MIN_CONTENT_WORDS

    def _claim(self, text: str, start: int, end: int) -> tuple[str, Optional[str]]:
        s0, s1 = self._sentence_bounds(text, start)
        s1 = max(s1, self._sentence_bounds(text, max(start, end - 1))[1])
        region = text[s0:s1]
        claim = self._strip_citation_tokens(region)
        # "Căn cứ Điều 34 BLDS 2015:" — nội dung nằm ở các dòng sau
        while len(claim) < 60 and s1 < len(text):
            n0, n1 = self._sentence_bounds(text, s1)
            if n1 <= s1:
                break
            region = text[s0:n1]
            s1 = n1
            claim = self._strip_citation_tokens(region)
            if len(region) > 600:
                break
        q = _QUOTE_RE.search(region)
        return claim[:600], (q.group(1).strip() if q else None)

    # ── API ──────────────────────────────────────────────────
    def extract(self, answer: str) -> list[Citation]:
        text = nfc(answer or "")
        mentions = self._doc_mentions(text)
        citations: list[Citation] = []

        for gi, m in enumerate(ART_RE.finditer(text)):
            dieu_list = [m.group("dieu").lower()]
            for sep, num in _MORE_ITEM_RE.findall(m.group("more") or ""):
                num = num.lower()
                if sep in ("đến", "tới", "-", "–") and dieu_list[-1].isdigit() and num.isdigit():
                    a, b = int(dieu_list[-1]), int(num)
                    if 0 < b - a <= _MAX_RANGE:
                        dieu_list += [str(x) for x in range(a + 1, b + 1)]
                        continue
                dieu_list.append(num)

            # Văn bản nhắc NGAY SAU cụm Điều
            ref, self_ref = None, None
            sr = SELF_REF_RE.match(text, m.end())
            if sr:
                self_ref = canon_loai(sr.group("loai"))
            else:
                for d in mentions:
                    if d.start < m.end():
                        continue
                    if _GAP_OK_RE.match(text[m.end():d.start]):
                        ref = d
                        # Tên gọi rồi số hiệu ngay sau: "Luật Nuôi con nuôi số 52/2010/QH12"
                        nxt = next((x for x in mentions if x.start >= d.end and x.kind == "so_hieu"), None)
                        if d.kind == "alias" and nxt and re.fullmatch(r"[\s,(]*(?:số\s*)?",
                                                                     text[d.end:nxt.start]):
                            ref = DocMention(d.start, nxt.end, "so_hieu", so_hieu=nxt.so_hieu,
                                             loai=nxt.loai, name=d.name)
                    break

            preceding = [d for d in mentions if d.end <= m.start()][::-1][:3]
            claim, quote = self._claim(text, m.start(), m.end())
            for dieu in dict.fromkeys(dieu_list):
                citations.append(Citation(
                    start=m.start(), end=m.end(), text=m.group(0).strip(), dieu=dieu,
                    khoan=m.group("khoan") if len(dieu_list) == 1 else None,
                    diem=(m.group("diem") or None) if len(dieu_list) == 1 else None,
                    ref=ref, self_ref=self_ref, preceding=preceding,
                    claim=claim, quote=quote, group=gi,
                    substantive=self.is_substantive(claim),
                ))

        # Lan ngược văn bản từ cụm sau sang cụm trước khi hai cụm nối trực tiếp
        for i in range(len(citations) - 2, -1, -1):
            a, b = citations[i], citations[i + 1]
            if (a.group != b.group and a.ref is None and a.self_ref is None
                    and (b.ref is not None or b.self_ref) and _JOIN_RE.match(text[a.end:b.start])):
                for c in citations:
                    if c.group == a.group:
                        c.ref, c.self_ref = b.ref, b.self_ref
        return citations
