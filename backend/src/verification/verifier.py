"""
B2 + B3 — Quy trích dẫn về văn bản trong corpus và kiểm ba điều kiện.

Mỗi trích dẫn nhận một trong bốn trạng thái:
- valid         : văn bản + Điều tồn tại, còn hiệu lực, nội dung Điều hỗ trợ nhận định
- warning       : tồn tại nhưng hiệu lực một phần / chưa có hiệu lực / không rõ,
                  hoặc điểm khớp nội dung nằm ở vùng xám
- invalid       : Điều/khoản không tồn tại, văn bản hết hiệu lực, hoặc nội dung Điều
                  không hỗ trợ nhận định
- unverifiable  : không quy được về văn bản nào trong corpus (luật mới hơn corpus,
                  số hiệu sai, trích "Điều N" trống không), hoặc văn bản không có trong KB

"unverifiable" KHÔNG đồng nghĩa với "bịa": corpus có giới hạn (vd Luật Đất đai 2024
không có trong metadata), báo "bịa" ở đây là khẳng định sai.
"""

import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Sequence

from loguru import logger

from src.verification.citation_index import CitationIndex, DocRecord
from src.verification.extractor import Citation, CitationExtractor, DocMention
from src.verification.normalize import NON_ORIGINAL_LOAI, canon_loai, normalize_text

# ── Hiệu lực ─────────────────────────────────────────────────
EFFECT_OF_STATUS = {
    "còn hiệu lực": "in_force",
    "hết hiệu lực một phần": "partial",
    "ngưng hiệu lực một phần": "partial",
    "hết hiệu lực toàn bộ": "expired",
    "ngưng hiệu lực": "expired",
    "không còn phù hợp": "expired",
    "chưa có hiệu lực": "not_yet",
    "chưa xác định": "unknown",
}
_EFFECT_RANK = {"in_force": 0, "partial": 1, "not_yet": 2, "unknown": 3, "expired": 4}
_LOAI_FAMILY = {"Luật": "luat", "Bộ luật": "luat"}


def effect_of(tinh_trang: str) -> str:
    return EFFECT_OF_STATUS.get(normalize_text(tinh_trang), "unknown")


# ── Ngưỡng (hiệu chỉnh trên tập val ở Phần D; đọc env để không phải sửa code) ──
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


# τ chọn trên DEV của bộ test làm sai có kiểm soát, tiêu chí báo nhầm ≤5%
# (data/citation_eval/verifier_eval.json → threshold_from_dev). Một mức: không có vùng xám.
CE_TAU_DEFAULT = 0.7174


@dataclass
class Thresholds:
    ce_high: float = field(default_factory=lambda: _env_float("CITATION_CE_HIGH", CE_TAU_DEFAULT))
    ce_low: float = field(default_factory=lambda: _env_float("CITATION_CE_LOW", CE_TAU_DEFAULT))
    quote_high: float = field(default_factory=lambda: _env_float("CITATION_QUOTE_HIGH", 0.6))
    quote_low: float = field(default_factory=lambda: _env_float("CITATION_QUOTE_LOW", 0.3))
    min_claim_chars: int = 15


# ── Chấm nội dung ────────────────────────────────────────────
ScoreFn = Callable[[list[tuple[str, str]]], list[float]]


class CrossEncoderScorer:
    """Bọc reranker sẵn có (FlagReranker hoặc sentence-transformers CrossEncoder), trả điểm 0..1."""

    def __init__(self, model: Any, use_flag: bool):
        self.model = model
        self.use_flag = use_flag

    @classmethod
    def from_reranker(cls, reranker: Any) -> Optional["CrossEncoderScorer"]:
        """Dùng lại model của Stage 4 — không nạp thêm model nào."""
        inner = getattr(reranker, "reranker", None)
        if inner is None:
            return None
        return cls(inner, hasattr(inner, "compute_score"))

    @classmethod
    def load(cls, model_name: str = "BAAI/bge-reranker-large") -> "CrossEncoderScorer":
        from FlagEmbedding import FlagReranker
        return cls(FlagReranker(model_name, use_fp16=True), True)

    def __call__(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        data = [[a, b] for a, b in pairs]
        if self.use_flag:
            s = self.model.compute_score(data, normalize=True)
            return [float(s)] if isinstance(s, (int, float)) else [float(x) for x in s]
        import math
        raw = self.model.predict(data)
        return [1 / (1 + math.exp(-float(x))) for x in raw]


_WORD_RE = re.compile(r"\w+")
_KHOAN_SPLIT_RE = re.compile(r"\n\s*(?=\d{1,2}\.\s)")
_HEADING_RE = re.compile(r"^\s*Điều\s+\d+[a-zđ]?\s*[.:]?\s*", re.IGNORECASE)


def quote_containment(quote: str, article: str, n: int = 3) -> float:
    """Tỉ lệ 3-gram từ của đoạn trích có mặt trong Điều (chịu được sai khác nhỏ)."""
    q = _WORD_RE.findall(normalize_text(quote))
    a = _WORD_RE.findall(normalize_text(article))
    if len(q) < n:
        return 0.0
    qs = {tuple(q[i:i + n]) for i in range(len(q) - n + 1)}
    as_ = {tuple(a[i:i + n]) for i in range(len(a) - n + 1)}
    return len(qs & as_) / len(qs)


def article_segments(content: str, khoan: Optional[str] = None,
                     max_chars: int = 1200, max_segments: int = 4) -> list[str]:
    """
    Cắt Điều thành đoạn cho cross-encoder (giới hạn 512 token, Điều dài bị cắt cụt →
    nhận định về khoản cuối sẽ bị báo sai). Bỏ "Điều N." ở đầu: nếu giữ, trích dẫn
    bị đổi số Điều vẫn khớp chữ "Điều 17" với "Điều 17." — rò rỉ từ vựng.
    """
    body = _HEADING_RE.sub("", content or "", count=1).strip()
    parts = _KHOAN_SPLIT_RE.split(body)
    heading, khoans = parts[0].split("\n", 1)[0].strip(), parts[1:] if len(parts) > 1 else []
    if not khoans:
        return [body[:max_chars * 2]]
    if khoan:
        hit = [k for k in khoans if re.match(rf"\s*{re.escape(khoan)}\.\s", k)]
        if hit:
            return [f"{heading}\n{hit[0]}"[:max_chars * 2]]
    segs, cur = [], heading
    for k in khoans:
        if len(cur) + len(k) > max_chars and cur != heading:
            segs.append(cur)
            cur = heading
        cur = f"{cur}\n{k}"
    segs.append(cur)
    return segs[:max_segments]


def khoan_numbers(content: str) -> set[str]:
    return set(re.findall(r"(?m)^\s*(\d{1,2})\.\s", content or ""))


# ── Kết quả ──────────────────────────────────────────────────
@dataclass
class CitationResult:
    text: str
    dieu: str
    khoan: Optional[str]
    diem: Optional[str]
    status: str                              # valid | warning | invalid | unverifiable
    reasons: list[str]
    resolution: str                          # so_hieu | alias | self_ref | inherited | context | unresolved
    doc_id: Optional[str] = None
    so_hieu: Optional[str] = None
    loai: Optional[str] = None
    title: Optional[str] = None
    tinh_trang: Optional[str] = None
    exists: Optional[bool] = None
    effect: Optional[str] = None
    content: Optional[str] = None            # supported | uncertain | mismatch | None
    ce_score: Optional[float] = None
    quote_score: Optional[float] = None
    in_context: bool = False
    chunk_id: Optional[str] = None
    claim: str = ""
    substantive: bool = True                 # False: dòng liệt kê nguồn, không kiểm nội dung
    start: int = 0
    end: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerificationReport:
    citations: list[CitationResult]

    @property
    def counts(self) -> dict:
        out = {"valid": 0, "warning": 0, "invalid": 0, "unverifiable": 0}
        for c in self.citations:
            out[c.status] += 1
        return out

    @property
    def n_invalid(self) -> int:
        return self.counts["invalid"]

    def to_dict(self) -> dict:
        return {"counts": self.counts, "n_citations": len(self.citations),
                "citations": [c.to_dict() for c in self.citations]}


REASON_TEXT = {
    "unresolved": "Không xác định được văn bản của trích dẫn",
    "doc_not_found": "Không tìm thấy văn bản trong cơ sở dữ liệu",
    "doc_not_in_kb": "Văn bản không có trong kho tra cứu, chưa kiểm được Điều",
    "doc_not_split": "Văn bản không chia theo Điều trong kho tra cứu",
    "dieu_out_of_range": "Văn bản không có Điều này (vượt số Điều của văn bản)",
    "dieu_missing": "Không tìm thấy Điều này trong kho tra cứu",
    "khoan_not_found": "Điều được trích không có khoản này",
    "expired": "Văn bản đã hết hiệu lực",
    "partial": "Văn bản đã hết hiệu lực một phần",
    "not_yet": "Văn bản chưa có hiệu lực",
    "effect_unknown": "Chưa xác định tình trạng hiệu lực",
    "content_mismatch": "Nội dung Điều không hỗ trợ nhận định",
    "content_uncertain": "Nội dung Điều chỉ hỗ trợ một phần nhận định",
    "quote_mismatch": "Đoạn trích nguyên văn không có trong Điều",
}


def _parse_date(s: str) -> datetime:
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y")
    except (ValueError, AttributeError):
        return datetime.min


def _dieu_int(dieu: str) -> Optional[int]:
    m = re.match(r"\d+", dieu or "")
    return int(m.group()) if m else None


class CitationVerifier:
    def __init__(self, index: CitationIndex, scorer: Optional[ScoreFn] = None,
                 thresholds: Optional[Thresholds] = None):
        self.index = index
        self.scorer = scorer
        self.th = thresholds or Thresholds()
        self.extractor = CitationExtractor(index.alias_names())
        self._max_dieu_cache: dict[str, Optional[int]] = {}

    # ── tra cứu ──────────────────────────────────────────────
    def _max_dieu(self, doc_id: str) -> Optional[int]:
        if doc_id not in self._max_dieu_cache:
            rows = self.index._conn().execute(
                "SELECT dieu FROM articles WHERE doc_id = ?", (doc_id,)).fetchall()
            nums = [n for n in (_dieu_int(r[0]) for r in rows) if n is not None]
            self._max_dieu_cache[doc_id] = max(nums) if nums else None
        return self._max_dieu_cache[doc_id]

    def _docs_for_mention(self, m: DocMention) -> list[DocRecord]:
        if m.kind == "so_hieu":
            docs = self.index.docs_by_so_hieu(m.so_hieu)
            if m.loai:
                fam = _LOAI_FAMILY.get(m.loai, m.loai)
                same = [d for d in docs if _LOAI_FAMILY.get(d.loai, d.loai) == fam]
                docs = same or docs
            if not docs and m.name:
                docs = self.index.docs_by_alias(m.name)
            return docs
        return self.index.docs_by_alias(m.name)

    def _pick(self, docs: list[DocRecord], dieu: str, ctx_docs: set[str]) -> Optional[DocRecord]:
        if not docs:
            return None
        originals = [d for d in docs if d.loai not in NON_ORIGINAL_LOAI] or docs

        def key(d: DocRecord):
            has_art = d.in_kb and self.index.get_article(d.doc_id, dieu) is not None
            return (d.doc_id not in ctx_docs, not has_art, not d.in_kb,
                    _EFFECT_RANK.get(effect_of(d.tinh_trang), 5),
                    -_parse_date(d.ngay_hieu_luc).toordinal())
        return min(originals, key=key)

    @staticmethod
    def _same_family(loai_a: str, loai_b: str) -> bool:
        return _LOAI_FAMILY.get(loai_a, loai_a) == _LOAI_FAMILY.get(loai_b, loai_b)

    def _resolve(self, c: Citation, ctx: list[dict], ctx_docs: set[str],
                 history: list[DocRecord]) -> tuple[Optional[DocRecord], str]:
        if c.ref is not None:
            docs = self._docs_for_mention(c.ref)
            method = "so_hieu" if c.ref.kind == "so_hieu" else "alias"
            doc = self._pick(docs, c.dieu, ctx_docs)
            return (doc, method) if doc else (None, "doc_not_found")

        ctx_hits = [ch for ch in ctx if str(ch.get("dieu") or "").lower() == c.dieu]
        if c.self_ref:
            # "Nghị định này" → văn bản CÙNG LOẠI được nhắc gần nhất, không phải văn bản gần nhất
            any_loai = c.self_ref.lower().startswith("văn bản")
            for doc in reversed(history):
                if any_loai or self._same_family(doc.loai, c.self_ref):
                    return doc, "self_ref"
            for m in c.preceding:
                doc = self._pick(self._docs_for_mention(m), c.dieu, ctx_docs)
                if doc and (any_loai or self._same_family(doc.loai, c.self_ref)):
                    return doc, "self_ref"
            for ch in ctx_hits:
                doc = self.index.get_doc(str(ch.get("doc_id")))
                if doc and (any_loai or self._same_family(doc.loai, c.self_ref)):
                    return doc, "context"
            return None, "unresolved"
        for m in c.preceding:
            doc = self._pick(self._docs_for_mention(m), c.dieu, ctx_docs)
            if doc is None:
                continue
            if self.index.get_article(doc.doc_id, c.dieu) is None and ctx_hits:
                break                       # văn bản kế thừa không có Điều này → thử context
            return doc, "inherited"
        if ctx_hits:
            doc = self.index.get_doc(str(ctx_hits[0].get("doc_id")))
            if doc:
                return doc, "context"
        return None, "unresolved"

    # ── kiểm ─────────────────────────────────────────────────
    def verify(self, answer: str, context_chunks: Sequence[dict] = ()) -> VerificationReport:
        ctx = list(context_chunks or [])
        ctx_docs = {str(ch.get("doc_id")) for ch in ctx if ch.get("doc_id")}
        ctx_pairs = {(str(ch.get("doc_id")), str(ch.get("dieu") or "").lower()) for ch in ctx}
        cites = self.extractor.extract(answer)

        results: list[CitationResult] = []
        pending: list[tuple[int, list[str]]] = []   # (result idx, segments) để chấm CE theo lô
        history: list[DocRecord] = []        # văn bản đã quy được, theo thứ tự xuất hiện
        group_sizes: dict[int, int] = {}
        for c in cites:
            group_sizes[c.group] = group_sizes.get(c.group, 0) + 1

        for c in cites:
            doc, method = self._resolve(c, ctx, ctx_docs, history)
            r = CitationResult(text=c.text, dieu=c.dieu, khoan=c.khoan, diem=c.diem,
                               status="unverifiable", reasons=[], resolution=method,
                               claim=c.claim, substantive=c.substantive, start=c.start, end=c.end)
            if doc is None:
                r.reasons.append("doc_not_found" if method == "doc_not_found" else "unresolved")
                r.resolution = "unresolved" if method != "doc_not_found" else (
                    "so_hieu" if c.ref and c.ref.kind == "so_hieu" else "alias")
                results.append(r)
                continue
            if method in ("so_hieu", "alias", "inherited", "context"):
                history.append(doc)

            r.doc_id, r.so_hieu, r.loai, r.title = doc.doc_id, doc.so_hieu, doc.loai, doc.title
            r.tinh_trang, r.effect = doc.tinh_trang, effect_of(doc.tinh_trang)
            r.in_context = (doc.doc_id, c.dieu) in ctx_pairs
            r.chunk_id = f"{doc.doc_id}_dieu_{c.dieu}"

            # (1) tồn tại
            article = self.index.get_article(doc.doc_id, c.dieu) if doc.in_kb else None
            if article is not None:
                r.exists = True
                if c.khoan:
                    ks = khoan_numbers(article)
                    if ks and c.khoan not in ks:
                        r.exists = False
                        r.reasons.append("khoan_not_found")
            elif not doc.in_kb:
                r.reasons.append("doc_not_in_kb")
            elif doc.n_articles == 0:
                r.reasons.append("doc_not_split")
            else:
                mx, n = self._max_dieu(doc.doc_id), _dieu_int(c.dieu)
                if mx is not None and n is not None and n > mx:
                    r.exists = False
                    r.reasons.append("dieu_out_of_range")
                else:
                    r.reasons.append("dieu_missing")

            # (2) hiệu lực
            if r.effect == "expired":
                r.reasons.append("expired")
            elif r.effect in ("partial", "not_yet"):
                r.reasons.append(r.effect)
            elif r.effect == "unknown":
                r.reasons.append("effect_unknown")

            # (3) nội dung — chỉ khi có Điều và có nhận định để so
            if article is not None and c.substantive and len(c.claim) >= self.th.min_claim_chars:
                if c.quote and group_sizes[c.group] == 1:
                    r.quote_score = round(quote_containment(c.quote, article), 4)
                    if r.quote_score >= self.th.quote_high:
                        r.content = "supported"
                    elif r.quote_score < self.th.quote_low:
                        r.content = "mismatch"
                        r.reasons.append("quote_mismatch")
                if r.content is None and self.scorer is not None:
                    pending.append((len(results), article_segments(article, c.khoan)))
            results.append(r)

        self._score_content(results, pending, cites)
        for r in results:
            r.status = self._status(r)
        return VerificationReport(results)

    def _score_content(self, results: list[CitationResult],
                       pending: list[tuple[int, list[str]]], cites: list[Citation]) -> None:
        if not pending or self.scorer is None:
            return
        pairs, owners = [], []
        for ri, segs in pending:
            for s in segs:
                pairs.append((results[ri].claim, s))
                owners.append(ri)
        # Cùng Điều được trích nhiều lần trong cùng câu → cặp trùng; chấm mỗi cặp một lần
        uniq = list(dict.fromkeys(pairs))
        try:
            uniq_scores = dict(zip(uniq, self.scorer(uniq)))
        except Exception as e:                       # chấm lỗi thì bỏ qua, không làm hỏng câu trả lời
            logger.warning(f"Citation content scoring lỗi: {e}")
            return
        best: dict[int, float] = {}
        for ri, p in zip(owners, pairs):
            best[ri] = max(best.get(ri, 0.0), uniq_scores[p])
        # "Điều 12 và Điều 13 ..." — nhận định dựa trên cả cụm: một Điều trong cụm hỗ trợ là đủ
        group_best: dict[int, float] = {}
        for ri, s in best.items():
            g = cites[ri].group
            group_best[g] = max(group_best.get(g, 0.0), s)
        for ri in best:
            apply_ce_score(results[ri], group_best[cites[ri].group], self.th)

    @staticmethod
    def _status(r: "CitationResult") -> str:
        return final_status(r)


def apply_ce_score(r: CitationResult, score: float, th: Thresholds) -> None:
    """Quyết định 'nội dung khớp' từ điểm cross-encoder (dùng chung cho production và đánh giá)."""
    r.ce_score = round(score, 4)
    r.reasons = [x for x in r.reasons if x not in ("content_mismatch", "content_uncertain")]
    if score >= th.ce_high:
        r.content = "supported"
    elif score < th.ce_low:
        r.content = "mismatch"
        r.reasons.append("content_mismatch")
    else:
        r.content = "uncertain"
        r.reasons.append("content_uncertain")


def final_status(r: CitationResult) -> str:
    """Gộp ba bước kiểm thành một trạng thái — lỗi chắc chắn được ưu tiên trước."""
    if r.doc_id is None:
        return "unverifiable"
    if r.exists is False or r.effect == "expired" or r.content == "mismatch":
        return "invalid"
    if r.exists is None:
        return "unverifiable"
    if r.effect in ("partial", "not_yet", "unknown") or r.content == "uncertain":
        return "warning"
    return "valid"
