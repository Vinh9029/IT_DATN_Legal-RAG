"""
Unit test cho Stage 6 (Citation Verification).

Dùng một chỉ mục SQLite tí hon dựng trong tmp_path từ đúng SCHEMA thật — không cần
file 1,2GB, không cần model. Các ca lấy từ dữ liệu thật đã gặp khi dựng chỉ mục:
số hiệu trùng giữa Bộ luật và Nghị quyết, bản dịch ghi sai trạng thái hiệu lực,
luật có trong metadata nhưng không có trong KB, "Nghị định này", tên "luật sư".

Chạy từ backend/:  pytest tests/test_citation_verification.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.verification.citation_index import SCHEMA, INDEXES, CitationIndex
from src.verification.extractor import CitationExtractor
from src.verification.normalize import aliases_for, normalize_so_hieu, normalize_text
from src.verification.verifier import (
    CitationVerifier, Thresholds, article_segments, quote_containment,
)

BLDS_34 = ("Điều 34. Quyền được bảo vệ danh dự, nhân phẩm, uy tín\n\n"
           "1. Danh dự, nhân phẩm, uy tín của cá nhân là bất khả xâm phạm và được pháp luật bảo vệ.\n\n"
           "2. Cá nhân có quyền yêu cầu Tòa án bác bỏ thông tin làm ảnh hưởng xấu đến danh dự.")
BLDS_35 = ("Điều 35. Quyền hiến, nhận mô, bộ phận cơ thể người\n\n"
           "1. Cá nhân có quyền hiến mô, bộ phận cơ thể của mình khi còn sống.")
ND70_15 = "Điều 15. Trách nhiệm của Hội Liên hiệp Phụ nữ\n\n1. Tham gia xây dựng chính sách."
ND70_16 = "Điều 16. Tham gia quản lý nhà nước\n\nCác Bộ có trách nhiệm phối hợp với Hội Liên hiệp Phụ nữ."

DOCS = [
    # doc_id, so_hieu, loai, title, tinh_trang, in_kb, n_articles
    ("95942", "91/2015/QH13", "Bộ luật", "Bộ luật Dân sự số 91/2015/QH13", "Còn hiệu lực", 1, 2),
    ("70827", "91/2015/QH13", "Nghị quyết",
     "Nghị quyết số 91/2015/QH13 Về chương trình giám sát", "Còn hiệu lực", 1, 0),
    ("18128", "33/2005/QH11", "Bộ luật", "Bộ luật Dân sự số 33/2005/QH11", "Hết hiệu lực toàn bộ", 0, 0),
    ("vbpqta_6607", "33/2005/QH11", "Bản dịch văn bản", "Code 33/2005/QH11", "Còn hiệu lực", 0, 0),
    ("24579", "70/2008/NĐ-CP", "Nghị định", "Nghị định số 70/2008/NĐ-CP Quy định chi tiết",
     "Còn hiệu lực", 1, 2),
    ("177815", "31/2024/QH15", "Luật", "Luật Đất đai số 31/2024/QH15", "Còn hiệu lực", 0, 0),
    ("139264", "45/2019/QH14", "Bộ luật", "Bộ Luật lao động số 45/2019/QH14", "Hết hiệu lực một phần", 1, 1),
    ("15076", "65/2006/QH11", "Luật", "Luật sư số 65/2006/QH11", "Hết hiệu lực một phần", 0, 0),
]
ARTICLES = [("95942", "34", BLDS_34), ("95942", "35", BLDS_35),
            ("24579", "15", ND70_15), ("24579", "16", ND70_16),
            ("139264", "35", "Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động của người lao động")]


@pytest.fixture(scope="module")
def index(tmp_path_factory) -> CitationIndex:
    path = tmp_path_factory.mktemp("cidx") / "citation_index.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    for doc_id, so, loai, title, tt, in_kb, n in DOCS:
        conn.execute(
            "INSERT INTO documents (doc_id, so_hieu, so_hieu_norm, loai, title, tinh_trang, in_kb, "
            "n_articles) VALUES (?,?,?,?,?,?,?,?)", (doc_id, so, normalize_so_hieu(so), loai, title, tt, in_kb, n))
        for a in aliases_for(title, loai, so):
            conn.execute("INSERT OR IGNORE INTO aliases VALUES (?, ?)", (a, doc_id))
    conn.executemany("INSERT INTO articles VALUES (?, ?, ?)", ARTICLES)
    conn.executescript(INDEXES)
    conn.commit()
    conn.close()
    return CitationIndex(path)


def keyword_scorer(pairs):
    """Scorer giả: tỉ lệ cặp từ (bigram) của nhận định có trong đoạn Điều.
    Không dùng từ đơn: âm tiết tiếng Việt như "cá", "nhân", "của" trùng khắp nơi."""
    def bigrams(s):
        w = normalize_text(s).replace(",", " ").split()
        return {tuple(w[i:i + 2]) for i in range(len(w) - 1)}
    out = []
    for claim, seg in pairs:
        cb = bigrams(claim)
        out.append(len(cb & bigrams(seg)) / max(1, len(cb)))
    return out


@pytest.fixture(scope="module")
def verifier(index) -> CitationVerifier:
    return CitationVerifier(index, scorer=keyword_scorer,
                            thresholds=Thresholds(ce_high=0.5, ce_low=0.2, quote_high=0.6, quote_low=0.3))


def one(verifier, text, ctx=()):
    cites = verifier.verify(text, ctx).citations
    assert len(cites) == 1, [c.text for c in cites]
    return cites[0]


# ── normalize ─────────────────────────────────────────────────
class TestNormalize:
    @pytest.mark.parametrize("raw,key", [
        ("91-2015-QH13", "91/2015/QH13"),
        ("01/2019/NĐ-CP", "1/2019/ND-CP"),
        ("151/2025/TT-BTС", "151/2025/TT-BTC"),       # С Cyrillic
        ("Không số", ""),
    ])
    def test_so_hieu(self, raw, key):
        assert normalize_so_hieu(raw) == key

    def test_tone_placement(self):
        assert normalize_text("Luật Tổ chức Toà án, thuỷ sản, toàn bộ") == \
            "luật tổ chức tòa án, thủy sản, toàn bộ"

    def test_aliases(self):
        assert aliases_for("Bộ luật Dân sự số 91/2015/QH13", "Bộ luật", "91/2015/QH13") == \
            {"bộ luật dân sự", "bộ luật dân sự 2015", "bộ luật dân sự năm 2015"}
        assert "bộ luật hàng hải 2015" in aliases_for("Hàng hải", "Bộ luật", "95/2015/QH13")
        assert "hiến pháp 2013" in aliases_for("Hiến pháp năm 2013", "Hiến pháp", "Không số")
        assert aliases_for("Nghị định số 70/2008/NĐ-CP", "Nghị định", "70/2008/NĐ-CP") == set()

    def test_luat_su_not_common_noun(self):
        assert "luật sư" not in aliases_for("Luật sư số 65/2006/QH11", "Luật", "65/2006/QH11")


# ── extractor ─────────────────────────────────────────────────
class TestExtractor:
    ex = CitationExtractor(["bộ luật dân sự", "bộ luật dân sự 2015", "luật luật sư"])

    def test_so_hieu_after(self):
        c = self.ex.extract("Theo Điều 16 Nghị định số 70/2008/NĐ-CP, các Bộ phải phối hợp.")[0]
        assert (c.dieu, c.ref.so_hieu, c.ref.loai) == ("16", "70/2008/NĐ-CP", "Nghị định")

    def test_lowercase_loai(self):
        c = self.ex.extract("Theo Điều 16 nghị định số 70/2008/NĐ-CP, các Bộ phải phối hợp.")[0]
        assert c.ref is not None and (c.ref.so_hieu, c.ref.loai) == ("70/2008/NĐ-CP", "Nghị định")

    def test_khoan_diem(self):
        c = self.ex.extract("Theo điểm a khoản 2 Điều 5 Nghị định 70/2008/NĐ-CP, ...")[0]
        assert (c.diem, c.khoan, c.dieu) == ("a", "2", "5")

    def test_self_ref(self):
        cs = self.ex.extract("Thực hiện các quy định tại khoản 1 Điều 15 Nghị định này.")
        assert cs[0].self_ref == "Nghị định" and cs[0].ref is None

    def test_list_and_range(self):
        assert [c.dieu for c in self.ex.extract("Điều 34, 35 và 36 Bộ luật Dân sự 2015")] == ["34", "35", "36"]
        assert [c.dieu for c in self.ex.extract("Các Điều 20 đến Điều 22 quy định")] == ["20", "21", "22"]

    def test_abbreviation(self):
        c = self.ex.extract("Căn cứ Điều 34 BLDS 2015, cá nhân có quyền yêu cầu.")[0]
        assert c.ref.kind == "alias" and c.ref.name == "bộ luật dân sự 2015"

    def test_doc_before_article_is_inherited(self):
        c = self.ex.extract("Bộ luật Dân sự 2015 quy định tại Điều 592 về bồi thường.")[0]
        assert c.ref is None and c.preceding[0].name == "bộ luật dân sự 2015"

    def test_common_noun_not_alias(self):
        assert self.ex.extract("Theo Điều 9, luật sư có quyền gặp thân chủ.")[0].ref is None

    def test_heading_period_not_sentence_end(self):
        c = self.ex.extract("Điều 34. Quyền được bảo vệ danh dự, nhân phẩm, uy tín của cá nhân.")[0]
        assert "danh dự" in c.claim

    def test_number_not_doc(self):
        assert self.ex.extract("Theo Điều 3, mức phạt là 5.000.000 đồng.")[0].ref is None

    def test_quote(self):
        c = self.ex.extract('Theo Điều 34 BLDS, "danh dự, nhân phẩm, uy tín của cá nhân là bất khả xâm phạm".')[0]
        assert c.quote.startswith("danh dự")


# ── verifier ──────────────────────────────────────────────────
class TestVerifier:
    def test_valid(self, verifier):
        r = one(verifier, "Theo Điều 34 Bộ luật Dân sự 2015, danh dự nhân phẩm uy tín của cá nhân là bất khả xâm phạm.")
        assert (r.status, r.doc_id, r.exists, r.effect) == ("valid", "95942", True, "in_force")

    def test_article_out_of_range(self, verifier):
        r = one(verifier, "Theo Điều 900 Bộ luật Dân sự 2015, cá nhân có quyền yêu cầu bồi thường.")
        assert r.status == "invalid" and "dieu_out_of_range" in r.reasons

    def test_khoan_not_found(self, verifier):
        r = one(verifier, "Theo khoản 9 Điều 34 Bộ luật Dân sự 2015, cá nhân có quyền yêu cầu.")
        assert r.status == "invalid" and "khoan_not_found" in r.reasons

    def test_expired_prefers_original_over_translation(self, verifier):
        # bản dịch vbpqta_6607 ghi "Còn hiệu lực" — sai; phải lấy bản gốc đã hết hiệu lực
        r = one(verifier, "Theo Điều 37 Bộ luật Dân sự số 33/2005/QH11, danh dự được bảo vệ.")
        assert (r.doc_id, r.status) == ("18128", "invalid") and "expired" in r.reasons

    def test_same_so_hieu_resolved_by_loai(self, verifier):
        r = one(verifier, "Theo Điều 34 Bộ luật số 91/2015/QH13, danh dự nhân phẩm là bất khả xâm phạm.")
        assert r.doc_id == "95942"

    def test_not_in_kb_is_unverifiable_not_invalid(self, verifier):
        r = one(verifier, "Theo Điều 4 Luật Đất đai số 31/2024/QH15, người sử dụng đất gồm tổ chức.")
        assert r.status == "unverifiable" and "doc_not_in_kb" in r.reasons

    def test_unknown_so_hieu(self, verifier):
        r = one(verifier, "Theo Điều 3 Nghị định số 999/2019/NĐ-CP, doanh nghiệp phải đăng ký.")
        assert r.status == "unverifiable" and "doc_not_found" in r.reasons

    def test_partial_effect_is_warning(self, verifier):
        r = one(verifier, "Theo Điều 35 Bộ luật Lao động 2019, quyền đơn phương chấm dứt hợp đồng lao động của người lao động.")
        assert r.status == "warning" and "partial" in r.reasons

    def test_self_ref_uses_previous_doc(self, verifier):
        cs = verifier.verify("Theo Điều 16 Nghị định số 70/2008/NĐ-CP, các Bộ phối hợp với Hội Liên hiệp Phụ nữ. "
                             "Hội tham gia xây dựng chính sách theo khoản 1 Điều 15 Nghị định này.").citations
        assert [(c.dieu, c.doc_id, c.resolution) for c in cs] == \
            [("16", "24579", "so_hieu"), ("15", "24579", "self_ref")]

    def test_self_ref_matches_loai_not_nearest_doc(self, verifier):
        # văn bản gần nhất là Bộ luật, nhưng "Nghị định này" phải về Nghị định 70/2008
        cs = verifier.verify(
            "Theo Điều 16 Nghị định số 70/2008/NĐ-CP, các Bộ phối hợp. Theo Điều 34 Bộ luật Dân sự 2015, "
            "danh dự được bảo vệ. Tham gia xây dựng chính sách theo khoản 1 Điều 15 hoặc Điều 16 của Nghị định này.").citations
        assert [(c.dieu, c.doc_id) for c in cs][-2:] == [("15", "24579"), ("16", "24579")]

    def test_hop_nhat_prefix(self):
        ex = CitationExtractor(["luật công chứng"])
        c = ex.extract("Theo Điều 34 Văn bản hợp nhất Luật Công chứng, văn phòng bị thu hồi.")[0]
        assert c.ref is not None and c.ref.name == "luật công chứng"

    def test_bare_article_resolved_by_context(self, verifier):
        r = one(verifier, "Điều 34 quy định danh dự nhân phẩm uy tín là bất khả xâm phạm.",
                ctx=[{"doc_id": "95942", "dieu": "34"}])
        assert (r.resolution, r.doc_id, r.in_context) == ("context", "95942", True)

    def test_bare_article_without_context(self, verifier):
        assert one(verifier, "Điều 592 quy định về bồi thường thiệt hại.").status == "unverifiable"

    def test_content_mismatch(self, verifier):
        # nhận định về danh dự nhưng trích Điều 35 (hiến mô)
        r = one(verifier, "Theo Điều 35 Bộ luật Dân sự 2015, danh dự nhân phẩm uy tín của cá nhân là bất khả xâm phạm.")
        assert r.status == "invalid" and r.content == "mismatch"

    def test_quote_mismatch(self, verifier):
        r = one(verifier, 'Theo Điều 35 Bộ luật Dân sự 2015, "người thừa kế được hưởng di sản theo di chúc hợp pháp".')
        assert r.status == "invalid" and "quote_mismatch" in r.reasons

    def test_no_scorer_still_checks_existence(self, index):
        v = CitationVerifier(index, scorer=None)
        r = one(v, "Theo Điều 35 Bộ luật Dân sự 2015, danh dự nhân phẩm uy tín của cá nhân là bất khả xâm phạm.")
        assert r.status == "valid" and r.content is None

    def test_reference_line_not_content_checked(self, verifier):
        # dòng liệt kê nguồn không có nhận định → không được báo "nội dung không khớp"
        r = one(verifier, "Trích dẫn: Điều 35 Bộ luật Dân sự 2015 ( )")
        assert r.substantive is False and r.content is None and r.status == "valid"

    def test_group_supported_by_any_member(self, verifier):
        # nhận định khớp Điều 34; Điều 35 trong cùng cụm không bị báo sai
        cs = verifier.verify("Theo Điều 34 và Điều 35 Bộ luật Dân sự 2015, danh dự nhân phẩm uy tín "
                             "của cá nhân là bất khả xâm phạm và được pháp luật bảo vệ.").citations
        assert [(c.dieu, c.status) for c in cs] == [("34", "valid"), ("35", "valid")]

    def test_duplicate_pairs_scored_once(self, index):
        seen = []

        def counting(pairs):
            seen.extend(pairs)
            return keyword_scorer(pairs)
        v = CitationVerifier(index, scorer=counting)
        # cùng một câu trích Điều 34 hai lần → cùng nhận định, cùng Điều
        v.verify("Theo Điều 34 Bộ luật Dân sự 2015 và Điều 34 Bộ luật Dân sự 2015, danh dự là bất khả xâm phạm.")
        assert len(seen) == len(set(seen)) and seen

    def test_scorer_failure_does_not_raise(self, index):
        def boom(_):
            raise RuntimeError("model down")
        r = one(CitationVerifier(index, scorer=boom),
                "Theo Điều 34 Bộ luật Dân sự 2015, danh dự nhân phẩm uy tín là bất khả xâm phạm.")
        assert r.status == "valid" and r.ce_score is None


class TestHelpers:
    def test_segments_strip_article_number(self):
        segs = article_segments(BLDS_34)
        assert segs and all("Điều 34" not in s for s in segs)

    def test_segments_pick_khoan(self):
        assert article_segments(BLDS_34, khoan="2")[0].endswith("ảnh hưởng xấu đến danh dự.")

    def test_quote_containment(self):
        assert quote_containment("danh dự, nhân phẩm, uy tín của cá nhân là bất khả xâm phạm", BLDS_34) == 1.0
        assert quote_containment("người thừa kế được hưởng di sản", BLDS_34) == 0.0


# ── Stage 6 + sửa (C4) với generator giả ──────────────────────
class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class FakeGenerator:
    """Bắt chước LegalGenerator backend LM Studio: chỉ dùng các thuộc tính repair cần."""
    _backend = "lmstudio"
    model, temperature, max_tokens = "fake", 0.1, 512

    def __init__(self, reply):
        self.reply, self.calls = reply, []
        self._history = []
        gen = self

        class _Completions:
            def create(self, **kw):
                gen.calls.append(kw)
                return type("R", (), {"choices": [_Msg(gen.reply)]})()
        self.client = type("C", (), {"chat": type("Ch", (), {"completions": _Completions()})()})()

    def _build_context(self, chunks):
        return "\n".join(f"[{i}] {c.get('doc_id')} — {c.get('dieu')}" for i, c in enumerate(chunks, 1))


BAD = "Theo Điều 900 Bộ luật Dân sự 2015, danh dự nhân phẩm uy tín của cá nhân là bất khả xâm phạm."
GOOD = "Theo Điều 34 Bộ luật Dân sự 2015, danh dự nhân phẩm uy tín của cá nhân là bất khả xâm phạm."
CTX = [{"doc_id": "95942", "dieu": "34", "metadata": {"so_hieu": "91/2015/QH13", "loai_van_ban": "Bộ luật"}}]


@pytest.fixture
def stage(index, verifier, monkeypatch):
    import src.verification.stage as st
    monkeypatch.setattr(st, "_verifier", verifier)
    monkeypatch.setattr(st, "_init_failed", False)
    monkeypatch.setenv("CITATION_VERIFY", "1")
    monkeypatch.setenv("CITATION_REPAIR", "1")
    return st


class TestStage:
    def test_repair_accepted_and_history_synced(self, stage):
        gen = FakeGenerator(GOOD)
        gen._history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": BAD}]
        out = stage.run_citation_stage("q", BAD, CTX, generator=gen)
        assert out["final_answer"] == GOOD and out["original_answer"] == BAD
        assert out["report"]["repair"]["accepted"] and out["report"]["counts"]["invalid"] == 0
        assert gen._history[-1]["content"] == GOOD
        # bước sửa không được kèm history dùng chung của generator
        assert [m["role"] for m in gen.calls[0]["messages"]] == ["system", "user", "assistant", "user"]
        assert "Điều 900" in gen.calls[0]["messages"][-1]["content"]

    def test_repair_rejected_when_citations_dropped(self, stage):
        out = stage.run_citation_stage("q", BAD, CTX, generator=FakeGenerator("Tôi không chắc chắn."))
        assert out["final_answer"] == BAD and out["original_answer"] is None
        assert out["report"]["repair"] == {"attempted": True, "accepted": False, "invalid_before": 1,
                                           "invalid_after": 0, "note": "not_better"}

    def test_no_repair_when_valid(self, stage):
        gen = FakeGenerator("không được gọi")
        out = stage.run_citation_stage("q", GOOD, CTX, generator=gen)
        assert out["final_answer"] == GOOD and gen.calls == []

    def test_repair_disabled(self, stage, monkeypatch):
        monkeypatch.setenv("CITATION_REPAIR", "0")
        gen = FakeGenerator(GOOD)
        out = stage.run_citation_stage("q", BAD, CTX, generator=gen)
        assert out["final_answer"] == BAD and out["report"]["repair"] is None and gen.calls == []

    def test_llm_error_keeps_answer(self, stage):
        gen = FakeGenerator(GOOD)
        gen.client = None                                   # gọi LLM sẽ AttributeError
        out = stage.run_citation_stage("q", BAD, CTX, generator=gen)
        assert out["final_answer"] == BAD and out["report"]["repair"]["note"].startswith("llm_error")

    def test_disabled_returns_none(self, stage, monkeypatch):
        monkeypatch.setenv("CITATION_VERIFY", "0")
        assert stage.run_citation_stage("q", BAD, CTX) is None

    def test_missing_index_does_not_raise(self, monkeypatch, tmp_path):
        import src.verification.stage as st
        monkeypatch.setattr(st, "_verifier", None)
        monkeypatch.setattr(st, "_init_failed", False)
        monkeypatch.setenv("CITATION_INDEX_PATH", str(tmp_path / "khong_co.sqlite"))
        assert st.run_citation_stage("q", BAD, CTX) is None

    def test_payload_matches_api_schema(self, stage):
        from src.api.schemas import QueryResponse
        out = stage.run_citation_stage("q", BAD, CTX, generator=FakeGenerator(GOOD))
        resp = QueryResponse(query="q", results=[], llm_answer=out["final_answer"], time_taken=1.0,
                             citation_report=out["report"], llm_answer_original=out["original_answer"])
        assert resp.citation_report.citations[0].status == "valid"
        assert resp.citation_report.citations[0].reason_texts == []
