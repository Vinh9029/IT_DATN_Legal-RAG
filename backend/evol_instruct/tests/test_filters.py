"""Unit tests cho bộ lọc Instruction Eliminator."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from evol_instruct.src.filters import (
    filter_prompt_leakage,
    filter_refusal,
    filter_semantic_similarity,
    filter_irac_structure,
    filter_min_length,
    filter_legal_hallucination,
    instruction_eliminator,
)


class TestPromptLeakage:
    def test_clean_prompt_passes(self):
        assert filter_prompt_leakage("Hãy phân tích quy định pháp luật") is True

    def test_rewritten_tag_fails(self):
        assert filter_prompt_leakage("Đây là #Rewritten Prompt# mới") is False

    def test_given_tag_fails(self):
        assert filter_prompt_leakage("#Given Prompt# câu hỏi gốc") is False

    def test_inst_tag_fails(self):
        assert filter_prompt_leakage("Nội dung [INST] chứa thẻ") is False


class TestRefusal:
    def test_normal_response_passes(self):
        assert filter_refusal("Theo Luật Dân sự 2015, quy định...") is True

    def test_short_refusal_fails(self):
        assert filter_refusal("Xin lỗi, tôi không thể.") is False

    def test_long_response_with_disclaimer_passes(self):
        resp = "Xin lỗi nếu có thiếu sót, " + "phân tích chi tiết " * 50
        assert filter_refusal(resp) is True

    def test_ai_identity_short_fails(self):
        assert filter_refusal("Tôi là một AI, không thể.") is False


class TestSemanticSimilarity:
    def test_different_prompts_pass(self):
        orig = "Luật Dân sự quy định gì?"
        evolved = "Phân tích trường hợp ngoại lệ trong tranh chấp hợp đồng mua bán bất động sản theo Bộ luật Dân sự"
        assert filter_semantic_similarity(orig, evolved) is True

    def test_identical_prompts_fail(self):
        text = "Luật Dân sự quy định gì về hợp đồng?"
        assert filter_semantic_similarity(text, text, threshold=0.95) is False

    def test_empty_prompts_pass(self):
        assert filter_semantic_similarity("", "") is True


class TestIRACStructure:
    def test_full_irac_passes(self):
        resp = """
        **Vấn đề (Issue):** Ai chịu trách nhiệm?
        **Quy tắc (Rule):** Theo Điều 584 BLDS 2015
        **Áp dụng (Application):** Trong trường hợp này
        **Kết luận (Conclusion):** Người gây thiệt hại phải bồi thường
        """
        assert filter_irac_structure(resp) is True

    def test_partial_irac_3_passes(self):
        resp = "Vấn đề: abc. Quy tắc: xyz. Kết luận: ok"
        assert filter_irac_structure(resp) is True

    def test_only_2_parts_fails(self):
        resp = "Vấn đề: abc. Kết luận: ok"
        assert filter_irac_structure(resp) is False

    def test_english_labels_work(self):
        resp = "Issue: problem. Rule: law. Application: analysis. Conclusion: done"
        assert filter_irac_structure(resp) is True


class TestMinLength:
    def test_long_response_passes(self):
        assert filter_min_length("a" * 300) is True

    def test_short_response_fails(self):
        assert filter_min_length("ngắn quá") is False

    def test_exactly_min_passes(self):
        assert filter_min_length("a" * 200) is True


class TestLegalHallucination:
    def test_no_refs_provided_passes(self):
        assert filter_legal_hallucination("Nghị định 100/2019/NĐ-CP") is True

    def test_valid_ref_passes(self):
        refs = {"100/2019/NĐ-CP", "Luật Dân sự 2015"}
        assert filter_legal_hallucination("Theo 100/2019/NĐ-CP", refs) is True

    def test_hallucinated_ref_fails(self):
        refs = {"100/2019/NĐ-CP"}
        assert filter_legal_hallucination("Theo 999/2099/NĐ-CP", refs) is False


class TestInstructionEliminator:
    def test_good_sample_passes(self):
        passed, fails = instruction_eliminator(
            original_prompt="Luật Dân sự quy định gì?",
            evolved_prompt="Phân tích trường hợp ngoại lệ trong tranh chấp hợp đồng bất động sản",
            response=(
                "**Vấn đề:** Tranh chấp hợp đồng. "
                "**Quy tắc:** Theo BLDS 2015. "
                "**Áp dụng:** Trong trường hợp anh A ký hợp đồng mua bán nhà. "
                "**Kết luận:** Hợp đồng vô hiệu do vi phạm hình thức. "
            ) * 3,
        )
        assert passed is True
        assert fails == []

    def test_leaked_prompt_rejected(self):
        passed, fails = instruction_eliminator(
            original_prompt="test",
            evolved_prompt="#Rewritten Prompt# test mới",
            response="Vấn đề Quy tắc Áp dụng Kết luận " * 20,
        )
        assert passed is False
        assert "prompt_leakage" in fails
