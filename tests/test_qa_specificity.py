"""
Unit tests cho QA Specificity Pipeline (Phần 3).

Không unit-test được output của LLM — nó không tất định. Test được là:
  - parser có chịu nổi output méo mó không
  - heuristic có đúng tiêu chí guideline không
  - derive_doc_id có ổn định không
  - group_split có rò rỉ giữa các tập không  ← quan trọng nhất
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from unittest.mock import MagicMock

from src.qa_specificity import corpus_filter
from src.qa_specificity.corpus_filter import (
    apply_scope_filter,
    derive_doc_id,
    is_in_scope,
    is_normative_doc,
    scope_of,
)
from src.qa_specificity.corpus_loader import (
    _slug,
    expand_documents_by_article,
    load_local_corpus,
    normalize_record,
    split_into_articles,
)
from src.qa_specificity.dataset_builder import (
    assert_no_leakage,
    compute_kappa,
    filter_consensus,
    group_split,
    resolve_item,
)
from src.qa_specificity.llm_judge import estimate_judge_cost, parse_judge_response
from config.qa_prompts import (
    NARROW_MODE_CITATION,
    NARROW_MODE_SITUATION,
    build_pair_generator_messages,
)
from src.qa_specificity.pair_generator import (
    build_pair_items,
    generate_pair,
    has_legal_citation,
    parse_pair_response,
    pick_narrow_mode,
)
from src.qa_specificity.schema import QAItem, Specificity
from src.qa_specificity.weak_labeler import heuristic_label


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def make_item(
    item_id="q1",
    pair_id="p1",
    doc_id="doc1",
    question="Câu hỏi thử nghiệm về hợp đồng lao động?",
    provenance=Specificity.BROAD,
    heuristic=Specificity.BROAD,
    judge=Specificity.BROAD,
):
    return QAItem(
        item_id=item_id,
        pair_id=pair_id,
        source_doc_id=doc_id,
        question=question,
        specificity=provenance,
        heuristic_label=heuristic,
        judge_label=judge,
    )


def make_pair(index: int, doc_id: str | None = None):
    """Một cặp broad+narrow hợp lệ, đã đồng thuận, dùng cho test split."""
    doc_id = doc_id or f"doc{index}"
    pair_id = f"pair{index}"
    items = []
    for label in (Specificity.BROAD, Specificity.NARROW):
        item = make_item(
            item_id=f"q{index}_{label.value}",
            pair_id=pair_id,
            doc_id=doc_id,
            provenance=label,
            heuristic=label,
            judge=label,
        )
        item.final_label = label
        item.consensus = True
        items.append(item)
    return items


# ══════════════════════════════════════════════════════════════════
# schema
# ══════════════════════════════════════════════════════════════════

class TestSchema:
    def test_roundtrip_giu_nguyen_du_lieu(self):
        item = make_item()
        item.final_label = Specificity.BROAD
        restored = QAItem.from_dict(item.to_dict())
        assert restored == item

    def test_to_dict_serialize_enum_thanh_chuoi(self):
        data = make_item().to_dict()
        assert data["specificity"] == "broad"
        assert isinstance(data["specificity"], str)

    def test_from_dict_bo_qua_field_la(self):
        data = make_item().to_dict()
        data["field_moi_cua_tuong_lai"] = 123
        assert QAItem.from_dict(data).item_id == "q1"

    def test_parse_nhan_bien_the(self):
        assert Specificity.parse("NARROW") is Specificity.NARROW
        assert Specificity.parse(" broad ") is Specificity.BROAD
        assert Specificity.parse("hẹp") is Specificity.NARROW
        assert Specificity.parse("unknown") is Specificity.AMBIGUOUS
        assert Specificity.parse("xyz") is None
        assert Specificity.parse(None) is None

    def test_is_decided(self):
        assert Specificity.BROAD.is_decided
        assert Specificity.NARROW.is_decided
        assert not Specificity.AMBIGUOUS.is_decided

    def test_blinded_dict_khong_lo_nhan_may(self):
        item = make_item(judge=Specificity.NARROW)
        item.final_label = Specificity.NARROW
        blinded = item.blinded_dict()

        # Anchoring bias: lộ bất kỳ nhãn máy nào là hỏng phép đo kappa
        for leaked in ("specificity", "heuristic_label", "judge_label", "final_label"):
            assert leaked not in blinded
        assert blinded["manual_label"] == ""


# ══════════════════════════════════════════════════════════════════
# corpus_filter
# ══════════════════════════════════════════════════════════════════

class TestCorpusFilter:
    def test_uu_tien_id_goc_cua_dataset(self):
        # `id` của dataset là định danh thật, ổn định tuyệt đối — không phụ
        # thuộc nội dung nên không đổi kể cả khi clean_html được chỉnh.
        doc_a = {"id": "132934", "metadata": {"so_ky_hieu": "45/2019/QH14"},
                 "content": "nội dung bản A"}
        doc_b = {"id": "132934", "metadata": {"so_ky_hieu": "khác hẳn"},
                 "content": "nội dung bản B khác hẳn"}
        assert derive_doc_id(doc_a) == derive_doc_id(doc_b) == "doc_132934"

    def test_id_khac_nhau_cho_doc_id_khac_nhau(self):
        assert derive_doc_id({"id": "1"}) != derive_doc_id({"id": "2"})

    def test_fallback_so_ky_hieu_khi_thieu_id(self):
        doc_a = {"metadata": {"so_ky_hieu": "45/2019/QH14"}, "content": "A"}
        doc_b = {"metadata": {"so_ky_hieu": "45/2019/QH14"}, "content": "B khác hẳn"}
        assert derive_doc_id(doc_a) == derive_doc_id(doc_b)
        assert derive_doc_id(doc_a) != derive_doc_id(
            {"metadata": {"so_ky_hieu": "91/2015/QH13"}, "content": "A"})

    def test_fallback_content_khi_thieu_ca_id_lan_so_ky_hieu(self):
        doc_id = derive_doc_id({"metadata": {}, "content": "x" * 600})
        assert doc_id.startswith("doc_")
        assert doc_id != derive_doc_id({"metadata": {}, "content": "y" * 600})

    def test_on_dinh_giua_cac_lan_goi(self):
        doc = {"metadata": {"so_ky_hieu": "45/2019/QH14"}, "content": "abc"}
        assert derive_doc_id(doc) == derive_doc_id(doc)

    @pytest.mark.parametrize("metadata,expected", [
        # Giá trị lấy từ dataset thật, không phải bịa
        # ── Lọt: nhận qua TIÊU ĐỀ (đường chính, vì 66% bản ghi thiếu linh_vuc) ──
        ({"title": "Bộ luật Dân sự số 91/2015/QH13", "loai_van_ban": "Bộ luật"}, True),
        ({"title": "Luật Đất đai số 45/2013/QH13", "loai_van_ban": "Luật"}, True),
        ({"title": "Luật Hôn nhân và gia đình số 52/2014/QH13", "nganh": "None",
          "linh_vuc": "Chưa phân loại", "loai_van_ban": "Luật"}, True),
        # ── Lọt: nhận qua metadata (đường bổ sung) ──
        ({"nganh": "Tư pháp", "linh_vuc": "Thi hành án dân sự",
          "loai_van_ban": "Nghị định"}, True),
        # ── Rớt: lao động KHÔNG còn trong phạm vi kể từ v1.2 ──
        ({"nganh": "Lao động - Thương binh và Xã hội", "linh_vuc": "Chưa phân loại",
          "loai_van_ban": "Thông tư"}, False),
        ({"nganh": "None", "linh_vuc": "Lao động, tiền lương, tiền công",
          "loai_van_ban": "Luật"}, False),
        # ── Rớt: ngoài phạm vi ──
        ({"nganh": "Tài chính", "linh_vuc": "Quản lý thuế, phí và lệ phí",
          "loai_van_ban": "Thông tư"}, False),
        ({"nganh": "", "linh_vuc": "", "loai_van_ban": "Luật"}, False),
    ])
    def test_loc_pham_vi(self, metadata, expected):
        assert is_in_scope({"metadata": metadata}) is expected

    def test_chi_giu_van_ban_quy_pham(self):
        # "Quyết định" chiếm 91k/171k nhưng phần lớn là quyết định hành chính
        # cá biệt, không có quy phạm để hỏi đáp pháp lý.
        base = {"nganh": "Tư pháp", "linh_vuc": "Thi hành án dân sự"}
        assert is_in_scope({"metadata": {**base, "loai_van_ban": "Thông tư"}}) is True
        for loai in ("Quyết định", "Nghị quyết", "Công văn", "Chỉ thị", "Bản dịch văn bản"):
            assert is_in_scope({"metadata": {**base, "loai_van_ban": loai}}) is False, loai

    def test_thieu_loai_van_ban_thi_khong_loc(self):
        # Nguồn tải tay thường không có cột `loai_van_ban`. Loại sạch corpus vì
        # thiếu một cột metadata là kiểu hỏng không có thông báo lỗi.
        assert is_normative_doc({"metadata": {}}) is True
        assert is_in_scope({"metadata": {"title": "Bộ luật Dân sự 2015"}}) is True

    @pytest.mark.parametrize("metadata", [
        # Mỗi dòng là một cú khớp nhầm ĐÃ ĐO ĐƯỢC trên dữ liệu thật
        {"nganh": "Quốc phòng", "linh_vuc": "Phòng thủ dân sự", "loai_van_ban": "Nghị định"},
        {"title": "Nghị định số 129/2017/NĐ-CP về quản lý, sử dụng tài sản công",
         "loai_van_ban": "Nghị định"},
        {"title": "Thông tư ban hành chế độ kế toán tài sản cố định",
         "loai_van_ban": "Thông tư"},
        {"title": "Thông tư quy định về phòng, chống bạo lực gia đình",
         "loai_van_ban": "Thông tư"},
        {"title": "Bộ luật Tố tụng hình sự số 101/2015/QH13", "loai_van_ban": "Bộ luật"},
    ])
    def test_anti_keyword_chan_khop_nham(self, metadata):
        assert is_in_scope({"metadata": metadata}) is False

    def test_chap_nhan_ca_dict_phang_lan_dict_long(self):
        flat = {"nganh": "Tư pháp", "linh_vuc": "Thi hành án dân sự",
                "loai_van_ban": "Thông tư"}
        assert is_in_scope(flat) is True
        assert is_in_scope({"metadata": flat}) is True

    def test_scope_of_phan_loai_dung_nhanh(self):
        assert scope_of({"title": "Bộ luật Dân sự số 91/2015/QH13"}) == "dan_su_chung"
        assert scope_of({"title": "Luật Nhà ở số 27/2023/QH15"}) == "dat_dai_nha_o"
        assert scope_of({"title": "Luật Sở hữu trí tuệ số 50/2005/QH11"}) == "so_huu_tri_tue"
        assert scope_of({"nganh": "Tư pháp", "linh_vuc": "Thi hành án dân sự"}) == "to_tung_thi_hanh_an"
        assert scope_of({"nganh": "Tài chính", "linh_vuc": "Chưa phân loại"}) == ""


class TestApplyScopeFilter:
    """Ba chế độ lọc — xem `SCOPE_FILTER_MODE` trong config/qa_settings.py."""

    CIVIL = {"metadata": {"title": "Bộ luật Dân sự 2015", "loai_van_ban": "Bộ luật"}}
    OTHER = {"metadata": {"title": "Luật An toàn thực phẩm", "loai_van_ban": "Luật"}}

    def _docs(self, n_civil, n_other):
        import copy
        return ([copy.deepcopy(self.CIVIL) for _ in range(n_civil)]
                + [copy.deepcopy(self.OTHER) for _ in range(n_other)])

    def test_strict_loc_thang_tay(self, monkeypatch):
        monkeypatch.setattr(corpus_filter, "SCOPE_FILTER_MODE", "strict")
        assert len(apply_scope_filter(self._docs(1, 9))) == 1

    def test_off_giu_nguyen(self, monkeypatch):
        monkeypatch.setattr(corpus_filter, "SCOPE_FILTER_MODE", "off")
        assert len(apply_scope_filter(self._docs(1, 9))) == 10

    def test_auto_loc_binh_thuong_khi_ti_le_du_cao(self, monkeypatch):
        monkeypatch.setattr(corpus_filter, "SCOPE_FILTER_MODE", "auto")
        monkeypatch.setattr(corpus_filter, "SCOPE_AUTO_MIN_RATIO", 0.20)
        assert len(apply_scope_filter(self._docs(8, 2))) == 8

    def test_auto_giu_nguyen_khi_ti_le_qua_thap(self, monkeypatch):
        # Nguồn đã thuần dân sự sẵn, hoặc từ khoá không khớp cách đặt tên của
        # nguồn — cả hai đều KHÔNG phải lý do để vứt dữ liệu.
        monkeypatch.setattr(corpus_filter, "SCOPE_FILTER_MODE", "auto")
        monkeypatch.setattr(corpus_filter, "SCOPE_AUTO_MIN_RATIO", 0.20)
        assert len(apply_scope_filter(self._docs(1, 19))) == 20

    def test_gan_truong_scope_cho_moi_doc(self, monkeypatch):
        monkeypatch.setattr(corpus_filter, "SCOPE_FILTER_MODE", "off")
        docs = apply_scope_filter(self._docs(1, 1))
        assert docs[0]["scope"] == "dan_su_chung"
        assert docs[1]["scope"] == ""


# ══════════════════════════════════════════════════════════════════
# pair_generator — parser
# ══════════════════════════════════════════════════════════════════

class TestParsePairResponse:
    def test_dinh_dang_chuan(self):
        text = (
            "[BROAD]\n"
            "Người lao động có những quyền gì theo pháp luật lao động?\n"
            "[NARROW]\n"
            "Theo khoản 1 Điều 35 Bộ luật Lao động 2019, phải báo trước bao nhiêu ngày?"
        )
        result = parse_pair_response(text)
        assert result["broad"].startswith("Người lao động")
        assert "Điều 35" in result["narrow"]

    @pytest.mark.parametrize("text", [
        # in đậm markdown
        "**[BROAD]**\nCâu hỏi rộng về quyền của người lao động?\n"
        "**[NARROW]**\nCâu hỏi hẹp theo Điều 35 quy định thế nào?",
        # heading
        "### BROAD\nCâu hỏi rộng về quyền của người lao động?\n"
        "### NARROW\nCâu hỏi hẹp theo Điều 35 quy định thế nào?",
        # đánh số + dấu hai chấm
        "1. [BROAD]: Câu hỏi rộng về quyền của người lao động?\n"
        "2. [NARROW]: Câu hỏi hẹp theo Điều 35 quy định thế nào?",
        # viết thường, không ngoặc
        "broad\nCâu hỏi rộng về quyền của người lao động?\n"
        "narrow\nCâu hỏi hẹp theo Điều 35 quy định thế nào?",
        # có lời dẫn thừa trước marker
        "Dưới đây là cặp câu hỏi tôi đã tạo:\n\n"
        "[BROAD]\nCâu hỏi rộng về quyền của người lao động?\n"
        "[NARROW]\nCâu hỏi hẹp theo Điều 35 quy định thế nào?",
        # tiếng Việt
        "[RỘNG]\nCâu hỏi rộng về quyền của người lao động?\n"
        "[HẸP]\nCâu hỏi hẹp theo Điều 35 quy định thế nào?",
    ])
    def test_chiu_duoc_bien_the_dinh_dang(self, text):
        result = parse_pair_response(text)
        assert "broad" in result and "narrow" in result
        assert "rộng" in result["broad"].lower()
        assert "Điều 35" in result["narrow"]

    def test_cau_hoi_trai_nhieu_dong(self):
        text = (
            "[BROAD]\n"
            "Khi phát sinh tranh chấp hợp đồng dân sự, các bên có những\n"
            "phương thức giải quyết nào?\n"
            "[NARROW]\n"
            "Theo Điều 468 BLDS, lãi suất tối đa là bao nhiêu?"
        )
        result = parse_pair_response(text)
        assert "phương thức giải quyết nào" in result["broad"]
        assert "\n" not in result["broad"]

    def test_thieu_mot_nhanh_thi_nhanh_do_vang_mat(self):
        result = parse_pair_response("[BROAD]\nChỉ có mỗi câu hỏi rộng ở đây thôi?")
        assert "broad" in result
        assert "narrow" not in result

    @pytest.mark.parametrize("text", ["", None, "Hoàn toàn không có marker nào cả.", "[BROAD]\n"])
    def test_output_rac_khong_raise(self, text):
        # Output méo mó là chuyện thường với model 8B — parser không được
        # phép ném exception làm chết cả pipeline.
        assert isinstance(parse_pair_response(text), dict)

    def test_bo_cau_qua_ngan(self):
        result = parse_pair_response("[BROAD]\nOK?\n[NARROW]\nCâu hỏi hẹp đủ dài về Điều 35?")
        assert "broad" not in result
        assert "narrow" in result


class TestBuildPairItems:
    @pytest.fixture
    def doc(self):
        return {
            "source_doc_id": "doc_abc123",
            "content": "nội dung",
            "scope": "dan_su_chung",
            "metadata": {"linh_vuc": "Lao động", "nganh": "Lao động - Tiền lương",
                         "so_hieu": "45/2019/QH14", "loai_van_ban": "Bộ luật"},
        }

    def test_hai_item_cung_pair_id_va_doc_id(self, doc):
        items = build_pair_items(doc, {
            "broad": "Người lao động có những quyền gì?",
            "narrow": "Theo Điều 35 phải báo trước bao nhiêu ngày?",
        })
        assert len(items) == 2
        assert items[0].pair_id == items[1].pair_id
        assert items[0].source_doc_id == items[1].source_doc_id == "doc_abc123"
        assert {i.specificity for i in items} == {Specificity.BROAD, Specificity.NARROW}
        assert items[0].item_id != items[1].item_id

    def test_thieu_mot_ve_thi_loai_ca_cap(self, doc):
        assert build_pair_items(doc, {"broad": "Chỉ có câu rộng thôi?"}) == []

    def test_hai_cau_trung_nhau_thi_loai(self, doc):
        same = "Người lao động có những quyền gì?"
        assert build_pair_items(doc, {"broad": same, "narrow": same}) == []


class TestChongShortcutTrichDan:
    """
    Chặn shortcut learning: câu narrow không được chỉ khác câu broad ở mỗi
    tiền tố trích dẫn. Xem khối chú thích đầu `config/qa_prompts.py`.
    """

    @pytest.fixture
    def doc(self):
        return {
            "source_doc_id": "doc_abc123",
            "content": "nội dung",
            "scope": "dan_su_chung",
            "metadata": {"linh_vuc": "Lao động", "nganh": "Lao động",
                         "so_hieu": "45/2019/QH14", "loai_van_ban": "Bộ luật"},
        }

    @pytest.mark.parametrize("question", [
        "Theo Điều 35 Bộ luật Lao động, báo trước mấy ngày?",
        "Theo khoản 2 Điều 468 thì lãi suất tối đa bao nhiêu?",
        "Theo Nghị định số 196-CP, doanh nghiệp nào phải áp dụng?",
        "Nghị định 100/2020/NĐ-CP quy định mức phạt bao nhiêu?",
        "Theo Điều 1 Nghị định 157-HĐBT, cấp uý nghỉ hưu năm bao nhiêu tuổi?",
        "Bộ luật Lao động 2019 quy định thời giờ làm việc thế nào?",
    ])
    def test_bat_duoc_trich_dan(self, question):
        assert has_legal_citation(question)

    @pytest.mark.parametrize("question", [
        "Chị B ký hợp đồng 24 tháng với công ty X, nghỉ việc sau 14 tháng thì sao?",
        "Anh A làm việc 3 năm, bị cho nghỉ không báo trước 45 ngày, có được bồi thường?",
        "Người lao động có những quyền gì theo pháp luật lao động Việt Nam?",
    ])
    def test_khong_bat_nham_con_so_trong_tinh_huong(self, question):
        # Tình huống narrow đầy số (24 tháng, 14 tháng, 45 ngày) nhưng KHÔNG
        # trích điều khoản — bắt nhầm mấy câu này thì cơ chế cưỡng chế sẽ
        # loại sạch đúng loại câu ta đang muốn có.
        assert not has_legal_citation(question)

    def test_che_do_tinh_huong_loai_cap_neu_narrow_van_trich_dan(self, doc):
        parsed = {
            "broad": "Người lao động có những quyền gì?",
            "narrow": "Theo Điều 35 Bộ luật Lao động, phải báo trước bao nhiêu ngày?",
        }
        assert build_pair_items(doc, parsed, narrow_mode=NARROW_MODE_SITUATION) == []
        # Cùng dữ liệu đó ở chế độ trích dẫn thì hợp lệ
        assert len(build_pair_items(doc, parsed, narrow_mode=NARROW_MODE_CITATION)) == 2

    def test_khong_truyen_mode_thi_bo_qua_kiem_tra_trich_dan(self, doc):
        parsed = {
            "broad": "Người lao động có những quyền gì?",
            "narrow": "Theo Điều 35 Bộ luật Lao động, phải báo trước bao nhiêu ngày?",
        }
        assert len(build_pair_items(doc, parsed)) == 2

    @pytest.mark.parametrize("parsed", [
        # narrow là câu khẳng định — lỗi chiếm 8/40 doc lúc đo thực tế
        {"broad": "Người lao động có quyền gì?",
         "narrow": "Theo Điều 2, Bộ Điện lực có nhiệm vụ trình Chính phủ duyệt quy hoạch."},
        # broad là câu khẳng định
        {"broad": "Bộ Điện lực quản lý ngành điện theo quy định của Chính phủ.",
         "narrow": "Anh A làm việc 3 năm thì được nghỉ phép bao nhiêu ngày?"},
    ])
    def test_loai_cap_neu_co_ve_khong_phai_cau_hoi(self, doc, parsed):
        assert build_pair_items(doc, parsed, narrow_mode=NARROW_MODE_SITUATION) == []

    def test_pick_narrow_mode_tat_dinh(self):
        # Tái lập được: resume từ checkpoint không được làm lệch phân bố
        assert pick_narrow_mode("doc_1") == pick_narrow_mode("doc_1")
        assert all(pick_narrow_mode(f"doc_{i}") in
                   (NARROW_MODE_SITUATION, NARROW_MODE_CITATION) for i in range(50))

    def test_pick_narrow_mode_can_bang_xap_xi(self):
        modes = [pick_narrow_mode(f"doc_{i}") for i in range(400)]
        ty_le = modes.count(NARROW_MODE_SITUATION) / len(modes)
        assert 0.4 <= ty_le <= 0.6, f"lệch quá: {ty_le:.2%} situation"

    def test_prompt_doi_vi_du_fewshot_theo_mode(self):
        # Đưa ví dụ trích dẫn rồi dặn "đừng trích dẫn" thì model nghe ví dụ,
        # không nghe lời dặn — nên ví dụ BẮT BUỘC phải khớp mode.
        sit = build_pair_generator_messages("nội dung", narrow_mode=NARROW_MODE_SITUATION)
        cit = build_pair_generator_messages("nội dung", narrow_mode=NARROW_MODE_CITATION)
        assert "CẤM TUYỆT ĐỐI" in sit[0]["content"]
        assert "CẤM TUYỆT ĐỐI" not in cit[0]["content"]
        assert not has_legal_citation(sit[1]["content"].split("[NARROW]")[1])
        assert has_legal_citation(cit[1]["content"].split("[NARROW]")[1])

    def test_mode_la_khong_hop_le_thi_raise(self):
        with pytest.raises(ValueError, match="narrow_mode"):
            build_pair_generator_messages("nội dung", narrow_mode="linh tinh")


class TestGeneratePair:
    def test_goi_llm_dung_mot_lan(self):
        # Thiết kế cặp đối chứng phụ thuộc vào việc sinh cả 2 câu trong CÙNG
        # một lượt gọi; gọi 2 lần riêng sẽ tái tạo confound về chủ đề.
        llm = MagicMock()
        llm.chat.return_value = (
            "[BROAD]\nNgười lao động có những quyền gì theo luật lao động?\n"
            "[NARROW]\nTheo khoản 1 Điều 35 Bộ luật Lao động 2019, báo trước mấy ngày?"
        )
        doc = {"source_doc_id": "doc_x", "content": "nội dung luật", "scope": "dan_su_chung",
               "metadata": {"linh_vuc": "Lao động", "nganh": "Lao động", "so_hieu": "45/2019/QH14"}}

        items = generate_pair(doc, llm)

        llm.chat.assert_called_once()
        assert len(items) == 2

    def test_llm_loi_thi_tra_list_rong(self):
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("connection refused")
        doc = {"source_doc_id": "doc_x", "content": "nội dung", "metadata": {}}
        assert generate_pair(doc, llm) == []


# ══════════════════════════════════════════════════════════════════
# weak_labeler — guideline §3, §4, §6
# ══════════════════════════════════════════════════════════════════

class TestHeuristicLabel:
    def test_vi_du_narrow_trong_guideline_5_1(self):
        question = (
            "Theo khoản 1 Điều 35 Bộ luật Lao động 2019, người lao động làm việc theo "
            "hợp đồng không xác định thời hạn phải báo trước bao nhiêu ngày khi đơn "
            "phương chấm dứt hợp đồng?"
        )
        label, detail = heuristic_label(question)
        assert label is Specificity.NARROW
        # Ngoại lệ phủ quyết: nêu đích danh cả điều lẫn khoản
        assert detail["override"] == "explicit_article_and_clause"

    def test_vi_du_narrow_tinh_huong_khong_trich_dieu_luat(self):
        # narrow KHÔNG đồng nghĩa với "có trích dẫn điều luật" (guideline §5.1)
        question = (
            "Chị B ký hợp đồng lao động xác định thời hạn 24 tháng với công ty X. "
            "Sau 14 tháng, chị B nghỉ việc và chỉ báo trước 10 ngày. Công ty yêu cầu "
            "chị bồi thường. Yêu cầu này có căn cứ pháp lý không?"
        )
        label, detail = heuristic_label(question)
        assert label is Specificity.NARROW
        assert "named_actor" in detail["narrow_signals"]
        assert "quantity_with_unit" in detail["narrow_signals"]

    def test_vi_du_broad_trong_guideline_5_2(self):
        label, detail = heuristic_label(
            "Người lao động có những quyền gì theo pháp luật lao động Việt Nam?"
        )
        assert label is Specificity.BROAD
        assert "enumeration" in detail["broad_signals"]

    def test_broad_so_sanh_nhieu_che_dinh(self):
        label, _ = heuristic_label(
            "Khi phát sinh tranh chấp hợp đồng dân sự, các bên có những phương thức "
            "giải quyết nào và ưu nhược điểm của từng phương thức ra sao?"
        )
        assert label is Specificity.BROAD

    def test_vung_xam_dung_mot_tin_hieu_thi_ambiguous(self):
        # guideline §6: đúng 1 tín hiệu narrow ⇒ nhường quyết định cho tầng khác
        label, detail = heuristic_label("Theo Điều 35 thì xử lý ra sao?")
        assert label is Specificity.AMBIGUOUS
        assert detail["narrow_count"] == 1

    def test_ngoai_le_hai_van_de_doc_lap_luon_broad(self):
        question = (
            "Theo khoản 2 Điều 468 BLDS lãi suất tối đa là bao nhiêu, và trong trường "
            "hợp đó thì thủ tục khởi kiện thế nào?"
        )
        label, detail = heuristic_label(question)
        # Ngoại lệ điều+khoản xét trước, đúng theo thứ tự ưu tiên ở guideline §4
        assert detail["n_legal_issues"] == 2
        assert label is Specificity.NARROW
        assert detail["override"] == "explicit_article_and_clause"

    def test_hai_van_de_khong_trich_dieu_khoan_thi_broad(self):
        label, detail = heuristic_label(
            "Hợp đồng có bị vô hiệu không, và trong trường hợp đó thì thủ tục khởi kiện "
            "được tiến hành như thế nào?"
        )
        assert label is Specificity.BROAD
        assert detail["override"] == "multiple_legal_issues"

    def test_cau_dinh_nghia_la_broad(self):
        label, detail = heuristic_label("Hợp đồng lao động là gì?")
        assert label is Specificity.BROAD
        assert "definition" in detail["broad_signals"]

    def test_khong_bat_nham_dai_tu_thanh_ten_rieng(self):
        # "anh ấy" không phải chủ thể có tên → không được tính là tín hiệu narrow
        _, detail = heuristic_label("Nếu anh ấy nghỉ việc thì công ty xử lý ra sao?")
        assert "named_actor" not in detail["narrow_signals"]

    def test_so_tran_khong_tinh_la_tin_hieu_dinh_luong(self):
        # "2019" trong tên văn bản không phải con số tình huống
        _, detail = heuristic_label("Bộ luật Lao động 2019 quy định về nội dung gì?")
        assert "quantity_with_unit" not in detail["narrow_signals"]

    def test_do_dai_chi_la_tin_hieu_phu(self):
        # Câu ngắn NHƯNG có tín hiệu narrow → không được gắn cờ short
        _, detail = heuristic_label("Điều 35 quy định gì?")
        assert "short_and_unspecific" not in detail["broad_signals"]

    def test_luon_tra_ve_signals_de_audit_duoc(self):
        _, detail = heuristic_label("Câu hỏi bất kỳ?")
        for key in ("narrow_signals", "broad_signals", "narrow_count", "n_words", "override"):
            assert key in detail

    @pytest.mark.parametrize("question", ["", "   ", "?"])
    def test_input_rong_khong_raise(self, question):
        label, _ = heuristic_label(question)
        assert isinstance(label, Specificity)


# ══════════════════════════════════════════════════════════════════
# llm_judge — parser
# ══════════════════════════════════════════════════════════════════

class TestParseJudgeResponse:
    def test_json_chuan(self):
        result = parse_judge_response(
            '{"axis1": "narrow", "axis2": "narrow", "axis3": "broad", '
            '"label": "narrow", "reason": "Nêu đích danh điều khoản"}'
        )
        assert result["label"] is Specificity.NARROW
        assert result["axes"]["axis1"] == "narrow"
        assert "đích danh" in result["reason"]

    def test_json_boc_trong_code_fence(self):
        result = parse_judge_response('```json\n{"label": "broad", "reason": "tổng quan"}\n```')
        assert result["label"] is Specificity.BROAD

    def test_json_kem_loi_dan_thua(self):
        result = parse_judge_response(
            'Sau khi phân tích, tôi kết luận:\n{"label": "narrow", "reason": "x"}\nHy vọng giúp ích.'
        )
        assert result["label"] is Specificity.NARROW

    def test_plain_text_tran(self):
        assert parse_judge_response("narrow")["label"] is Specificity.NARROW
        assert parse_judge_response('"broad"')["label"] is Specificity.BROAD

    def test_judge_tra_ambiguous(self):
        result = parse_judge_response('{"label": "ambiguous", "reason": "trục 2 không chấm được"}')
        assert result["label"] is Specificity.AMBIGUOUS

    @pytest.mark.parametrize("text", ["", None, "hoàn toàn vô nghĩa", "{lỗi json"])
    def test_khong_parse_duoc_tra_none_chu_khong_doan_bua(self, text):
        # Mặc định về broad/narrow khi không parse được sẽ tạo ra nhãn giả
        # trông y hệt nhãn thật — không bao giờ phát hiện được về sau.
        assert parse_judge_response(text)["label"] is None


# ══════════════════════════════════════════════════════════════════
# dataset_builder — hợp nhất nhãn
# ══════════════════════════════════════════════════════════════════

class TestResolveItem:
    def test_ba_tang_dong_thuan_thi_giu(self):
        item = resolve_item(make_item(judge=Specificity.BROAD))
        assert item.consensus is True
        assert item.final_label is Specificity.BROAD

    def test_provenance_lech_judge_thi_loai(self):
        item = resolve_item(make_item(provenance=Specificity.BROAD, judge=Specificity.NARROW))
        assert item.consensus is False
        assert item.reject_reason == "provenance_vs_judge_mismatch"

    def test_judge_ambiguous_thi_loai(self):
        # Judge chấm đủ 3 trục nên 'ambiguous' của judge là kết luận
        # "câu vùng xám" (guideline §5.3), không phải abstain.
        item = resolve_item(make_item(judge=Specificity.AMBIGUOUS))
        assert item.consensus is False
        assert item.reject_reason == "judge_ambiguous"

    def test_judge_vang_mat_thi_loai(self):
        item = resolve_item(make_item(judge=None))
        assert item.consensus is False
        assert item.reject_reason == "judge_missing"

    def test_heuristic_ambiguous_la_abstain_khong_phai_phieu_chong(self):
        # guideline §6: 'ambiguous' = "nhường quyết định cho LLM judge và
        # tầng provenance". Hai tầng còn lại đã đồng thuận ⇒ giữ.
        item = resolve_item(make_item(heuristic=Specificity.AMBIGUOUS))
        assert item.consensus is True
        assert item.final_label is Specificity.BROAD

    def test_strict_thi_heuristic_ambiguous_bi_loai(self):
        item = resolve_item(make_item(heuristic=Specificity.AMBIGUOUS), strict=True)
        assert item.consensus is False
        assert item.reject_reason == "heuristic_ambiguous_strict"

    def test_heuristic_lech_han_thi_loai_ke_ca_khong_strict(self):
        item = resolve_item(make_item(heuristic=Specificity.NARROW, judge=Specificity.BROAD,
                                      provenance=Specificity.BROAD))
        assert item.consensus is False
        assert item.reject_reason == "heuristic_vs_judge_mismatch"


class TestFilterConsensus:
    def test_loai_cau_lam_cap_khuyet_ve(self):
        # Giữ cặp khuyết vế làm lệch phân bố chủ đề giữa hai lớp — đúng cái
        # confound mà thiết kế cặp đối chứng sinh ra để triệt tiêu.
        broad, narrow = make_pair(1)
        narrow.judge_label = Specificity.BROAD  # vế narrow sẽ bị loại
        verified, rejected = filter_consensus([broad, narrow])
        assert verified == []
        assert len(rejected) == 2
        assert any(i.reject_reason == "incomplete_pair" for i in rejected)

    def test_cho_phep_cap_khuyet_khi_bat_co(self):
        broad, narrow = make_pair(1)
        narrow.judge_label = Specificity.BROAD
        verified, _ = filter_consensus([broad, narrow], require_complete_pairs=False)
        assert len(verified) == 1

    def test_cap_hoan_chinh_thi_giu_ca_hai(self):
        verified, rejected = filter_consensus(make_pair(1))
        assert len(verified) == 2
        assert rejected == []


# ══════════════════════════════════════════════════════════════════
# dataset_builder — group split (TEST QUAN TRỌNG NHẤT)
# ══════════════════════════════════════════════════════════════════

class TestGroupSplit:
    @pytest.fixture
    def items(self):
        return [item for i in range(40) for item in make_pair(i)]

    def test_khong_ro_ri_giua_train_va_test(self, items):
        """
        Bất biến sống còn của Phần 3.

        Nếu bất biến này vỡ, mọi metric của ablation study đều cao giả tạo, và
        lỗi này KHÔNG tự báo — nó chỉ âm thầm cho ra con số đẹp không có thật.
        """
        splits = group_split(items)
        train_docs = {i.source_doc_id for i in splits["train"]}
        test_docs = {i.source_doc_id for i in splits["test"]}
        val_docs = {i.source_doc_id for i in splits["val"]}

        assert train_docs & test_docs == set()
        assert train_docs & val_docs == set()
        assert val_docs & test_docs == set()

    def test_ca_hai_ve_cua_cap_nam_cung_mot_split(self, items):
        splits = group_split(items)
        pair_to_split = {}
        for name, subset in splits.items():
            for item in subset:
                assert pair_to_split.setdefault(item.pair_id, name) == name

    def test_nhieu_cap_tu_cung_van_ban_khong_bi_tach(self):
        # Một văn bản sinh nhiều cặp: các cặp đó cũng chồng lấn nội dung nên
        # phải nằm cùng split. Đây là lý do group theo source_doc_id chứ
        # không phải theo pair_id.
        items = []
        for doc_index in range(20):
            for pair_index in range(3):
                items.extend(make_pair(doc_index * 10 + pair_index, doc_id=f"doc{doc_index}"))

        splits = group_split(items)
        doc_to_split = {}
        for name, subset in splits.items():
            for item in subset:
                assert doc_to_split.setdefault(item.source_doc_id, name) == name

    def test_khong_mat_item_nao(self, items):
        splits = group_split(items)
        assert sum(len(s) for s in splits.values()) == len(items)
        all_ids = {i.item_id for s in splits.values() for i in s}
        assert all_ids == {i.item_id for i in items}

    def test_ty_le_xap_xi_70_15_15(self, items):
        splits = group_split(items)
        total = len(items)
        assert 0.55 <= len(splits["train"]) / total <= 0.85
        assert len(splits["val"]) > 0
        assert len(splits["test"]) > 0

    def test_cung_seed_cho_cung_ket_qua(self, items):
        a = group_split(items, seed=7)
        b = group_split(items, seed=7)
        assert [i.item_id for i in a["test"]] == [i.item_id for i in b["test"]]

    def test_ty_le_khong_cong_bang_1_thi_raise(self, items):
        with pytest.raises(ValueError, match="1.0"):
            group_split(items, train_ratio=0.7, val_ratio=0.2, test_ratio=0.2)

    def test_qua_it_van_ban_nguon_thi_raise(self):
        # 2 văn bản không thể chia 3 tập mà không rò rỉ — thà nổ còn hơn
        # âm thầm trả về split hỏng.
        items = make_pair(1, doc_id="doc1") + make_pair(2, doc_id="doc2")
        with pytest.raises(ValueError, match="source_doc_id"):
            group_split(items)

    def test_items_rong(self):
        assert group_split([]) == {"train": [], "val": [], "test": []}


class TestAssertNoLeakage:
    def test_phat_hien_ro_ri_doc_id(self):
        broad, narrow = make_pair(1)
        with pytest.raises(AssertionError, match="DATA LEAKAGE"):
            assert_no_leakage({"train": [broad], "val": [], "test": [narrow]})

    def test_split_sach_thi_khong_raise(self):
        assert_no_leakage({
            "train": make_pair(1, doc_id="docA"),
            "val": make_pair(2, doc_id="docB"),
            "test": make_pair(3, doc_id="docC"),
        })


# ══════════════════════════════════════════════════════════════════
# Cohen's kappa
# ══════════════════════════════════════════════════════════════════

class TestComputeKappa:
    def test_dong_thuan_tuyet_doi(self):
        labels = ["broad", "narrow"] * 10
        result = compute_kappa(labels, list(labels))
        assert result["cohen_kappa"] == 1.0
        assert result["raw_agreement"] == 1.0

    def test_kappa_thap_thi_bao_sua_guideline(self):
        manual = ["broad", "narrow"] * 10
        machine = ["narrow", "broad"] * 10
        result = compute_kappa(manual, machine)
        assert result["cohen_kappa"] < 0.6
        assert "GUIDELINE" in result["interpretation"]

    def test_do_dai_lech_thi_raise(self):
        with pytest.raises(ValueError, match="không khớp"):
            compute_kappa(["broad"], ["broad", "narrow"])

    def test_rong_thi_raise(self):
        with pytest.raises(ValueError):
            compute_kappa([], [])


# ══════════════════════════════════════════════════════════════════
# estimate_judge_cost
# ══════════════════════════════════════════════════════════════════

class TestEstimateJudgeCost:
    """
    Hàm này tồn tại để trả lời "chạy judge tốn bao nhiêu" TRƯỚC khi gọi API.
    Nó mà đếm nhầm thì quyết định bật/tắt judge trả phí dựa trên số sai.
    """

    def test_khong_co_cache_thi_moi_cau_deu_phai_tra(self):
        items = [make_item(item_id=f"q{i}") for i in range(5)]
        est = estimate_judge_cost(items, cache_path=None)
        assert est["n_items"] == 5
        assert est["n_calls"] == 5
        assert est["n_cached"] == 0
        assert est["input_tokens_est"] > 0

    def test_cau_da_co_trong_cache_khong_tinh_tien(self, tmp_path):
        # Cache chỉ nhận bản ghi có nhãn thật (xem `_load_cache`), nên bản ghi
        # judge_label=None phải bị coi như CHƯA chấm và vẫn phải trả tiền.
        import json

        cache = tmp_path / "judge_cache.jsonl"
        cache.write_text(
            json.dumps({"item_id": "q0", "judge_label": "broad"}, ensure_ascii=False) + "\n"
            + json.dumps({"item_id": "q1", "judge_label": None}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        items = [make_item(item_id=f"q{i}") for i in range(3)]
        est = estimate_judge_cost(items, cache_path=cache)
        assert est["n_cached"] == 1        # chỉ q0
        assert est["n_calls"] == 2         # q1 (hỏng) + q2

    def test_bo_fewshot_thi_prompt_ngan_lai(self):
        items = [make_item()]
        co = estimate_judge_cost(items, use_fewshot=True)
        khong = estimate_judge_cost(items, use_fewshot=False)
        assert khong["input_chars"] < co["input_chars"]

    def test_khong_con_cau_nao_thi_chi_phi_bang_khong(self):
        est = estimate_judge_cost([], cache_path=None)
        assert est["n_calls"] == 0
        assert est["usd_total"] == 0


# ══════════════════════════════════════════════════════════════════
# corpus_loader — nạp nguồn đa định dạng
# ══════════════════════════════════════════════════════════════════

class TestSlugTenCot:
    """Nguồn dữ liệu người Việt hay có header tiếng Việt CÓ DẤU."""

    @pytest.mark.parametrize("raw,expected", [
        ("Nội dung", "noi_dung"),
        ("Số ký hiệu", "so_ky_hieu"),
        ("Loại văn bản", "loai_van_ban"),
        ("Tiêu đề", "tieu_de"),
        ("  CONTENT_HTML  ", "content_html"),
        ("Ngày ban hành", "ngay_ban_hanh"),
    ])
    def test_bo_dau_va_thuong_hoa(self, raw, expected):
        assert _slug(raw) == expected


class TestNormalizeRecord:
    def test_header_tieng_viet_van_khop_bi_danh(self):
        doc = normalize_record({
            "Số ký hiệu": "91/2015/QH13",
            "Tiêu đề": "Bộ luật Dân sự",
            "Nội dung": "x" * 600,
            "Loại văn bản": "Bộ luật",
        }, source_file="a.csv")
        assert doc is not None
        assert doc["metadata"]["so_hieu"] == "91/2015/QH13"
        assert doc["metadata"]["title"] == "Bộ luật Dân sự"
        assert doc["metadata"]["loai_van_ban"] == "Bộ luật"
        assert doc["content_length"] == 600

    def test_khong_co_noi_dung_thi_bo_qua(self):
        # Dòng trống trong CSV là chuyện bình thường, không phải lỗi
        assert normalize_record({"title": "abc"}, source_file="a.csv") is None

    def test_o_trong_ghi_bang_chuoi_None(self):
        doc = normalize_record({"content": "x" * 600, "nganh": "None",
                                "linh_vuc": "nan"}, source_file="a.csv")
        assert doc["metadata"]["nganh"] == ""
        assert doc["metadata"]["linh_vuc"] == ""

    def test_lam_sach_html(self):
        doc = normalize_record(
            {"content_html": "<p>Điều 1. Phạm vi</p><p>" + "x" * 600 + "</p>"},
            source_file="a.jsonl",
        )
        assert "<p>" not in doc["content"]

    def test_thieu_id_thi_sinh_id_on_dinh(self):
        raw = {"content": "x" * 600, "so_hieu": "91/2015/QH13"}
        a = normalize_record(raw, source_file="a.csv", index=0)
        b = normalize_record(raw, source_file="a.csv", index=0)
        assert a["source_doc_id"] == b["source_doc_id"]
        assert a["source_doc_id"].startswith("doc_")


class TestLoadLocalCorpus:
    def test_doc_duoc_jsonl_va_csv_trong_cung_thu_muc(self, tmp_path):
        import json as _json
        body = "x" * 600
        (tmp_path / "a.jsonl").write_text(
            _json.dumps({"id": "1", "content": body, "title": "Bộ luật Dân sự"},
                        ensure_ascii=False) + "\n",
            encoding="utf-8")
        (tmp_path / "b.csv").write_text(
            "id,Tiêu đề,Nội dung\n2,Luật Đất đai,{}\n".format(body),
            encoding="utf-8-sig")

        docs = load_local_corpus(tmp_path)
        assert len(docs) == 2
        assert {d["metadata"]["title"] for d in docs} == {"Bộ luật Dân sự", "Luật Đất đai"}
        assert {d["source_file"] for d in docs} == {"a.jsonl", "b.csv"}

    def test_loai_trung_source_doc_id(self, tmp_path):
        import json as _json
        line = _json.dumps({"id": "1", "content": "x" * 600}) + "\n"
        (tmp_path / "a.jsonl").write_text(line + line, encoding="utf-8")
        assert len(load_local_corpus(tmp_path)) == 1

    def test_bo_qua_file_qua_ngan(self, tmp_path):
        import json as _json
        (tmp_path / "a.jsonl").write_text(
            _json.dumps({"id": "1", "content": "ngắn"}) + "\n", encoding="utf-8")
        assert load_local_corpus(tmp_path) == []

    def test_mot_file_hong_khong_lam_hong_ca_me(self, tmp_path):
        import json as _json
        (tmp_path / "good.jsonl").write_text(
            _json.dumps({"id": "1", "content": "x" * 600}) + "\n", encoding="utf-8")
        # .parquet không phải parquet — reader sẽ ném, phải bị bỏ qua chứ không lan
        (tmp_path / "bad.parquet").write_bytes(b"khong phai parquet")
        assert len(load_local_corpus(tmp_path)) == 1

    def test_thu_muc_rong_tra_ve_rong(self, tmp_path):
        assert load_local_corpus(tmp_path) == []


class TestSplitByArticle:
    CONTENT = (
        "CHÍNH PHỦ\nCăn cứ Hiến pháp năm 2013;\n"
        "Điều 1. Phạm vi điều chỉnh\n" + "a" * 400 + "\n"
        "Điều 2. Giải thích từ ngữ\n" + "b" * 400 + "\n"
        "Điều 3. Nguyên tắc\n" + "c" * 400 + "\n"
    )

    def test_cat_dung_so_dieu(self):
        articles = split_into_articles(self.CONTENT)
        assert [num for num, _ in articles] == ["1", "2", "3"]
        assert articles[0][1].startswith("Điều 1.")

    def test_dieu_qua_ngan_bi_loai(self):
        content = "Điều 1. Ngắn\nx\nĐiều 2. Dài\n" + "y" * 400
        assert [n for n, _ in split_into_articles(content)] == ["2"]

    def test_van_ban_khong_danh_so_theo_dieu_tra_ve_rong(self):
        # Thông tư đánh `I.`/`1.` — caller giữ nguyên cả văn bản
        assert split_into_articles("I. Quy định chung\n" + "x" * 900) == []

    def test_khong_bat_dieu_viet_thuong_giua_cau(self):
        assert split_into_articles("Theo điều 5 nói trên thì " + "x" * 900) == []

    def test_expand_doi_source_doc_id_thanh_khoa_group_moi(self):
        docs = expand_documents_by_article([{
            "id": "1", "source_doc_id": "doc_1", "content": self.CONTENT,
            "content_length": len(self.CONTENT), "metadata": {"title": "BLDS"},
        }])
        assert len(docs) == 3
        assert [d["source_doc_id"] for d in docs] == [
            "doc_1#dieu-1", "doc_1#dieu-2", "doc_1#dieu-3"]
        assert all(d["parent_doc_id"] == "doc_1" for d in docs)
        # metadata phải là bản sao, không dùng chung một dict
        docs[0]["metadata"]["dieu"] = "sửa"
        assert docs[1]["metadata"]["dieu"] == "2"

    def test_van_ban_khong_cat_duoc_thi_giu_nguyen(self):
        doc = {"id": "1", "source_doc_id": "doc_1", "content": "x" * 900,
               "content_length": 900, "metadata": {}}
        out = expand_documents_by_article([doc])
        assert out == [doc]
