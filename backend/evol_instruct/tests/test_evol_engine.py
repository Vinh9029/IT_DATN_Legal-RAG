"""Unit tests cho Evol Engine."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from evol_instruct.src.evol_engine import EvolPipeline


class TestEvolPipeline:
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.chat.return_value = "Mocked response"
        return llm

    @pytest.fixture
    def pipeline(self, mock_llm, tmp_path):
        with patch("evol_instruct.src.evol_engine.OUTPUT_DIR", tmp_path):
            return EvolPipeline(
                llm_client=mock_llm,
                output_file="test_output.jsonl",
                checkpoint_file="test_checkpoint.json",
            )

    def test_evolve_instruction(self, pipeline):
        result = pipeline.evolve_instruction(
            "Luật Dân sự quy định gì?",
            technique_key="constraint_addition",
        )
        assert result == "Mocked response"
        pipeline.llm.chat.assert_called_once()

    def test_generate_irac_response(self, pipeline):
        result = pipeline.generate_irac_response("Câu hỏi tiến hóa")
        assert result == "Mocked response"

    def test_process_single_rejected(self, pipeline):
        # Mock LLM trả về response không đạt IRAC
        pipeline.llm.chat.return_value = "Quá ngắn"
        seed = {"id": "test1", "instruction": "Test instruction"}
        result = pipeline.process_single(seed)
        assert result is None
        assert pipeline.stats["total_rejected"] >= 0

    def test_stats_initialization(self, pipeline):
        assert pipeline.stats["total_processed"] == 0
        assert pipeline.stats["total_accepted"] == 0
        assert pipeline.stats["total_rejected"] == 0


IRAC_OK = (
    "**Vấn đề (Issue):** Ông A có được hưởng thừa kế không?\n\n"
    "**Quy tắc (Rule):** Theo Điều 651 Bộ luật Dân sự 2015, hàng thừa kế thứ nhất gồm vợ, chồng, cha, mẹ, con.\n\n"
    "**Áp dụng (Application):** Ông A là con của người chết nên thuộc hàng thừa kế thứ nhất theo quy định trên.\n\n"
    "**Kết luận (Conclusion):** Ông A được hưởng phần di sản bằng với những người cùng hàng thừa kế."
)


class TestGroundedMode:
    """Chế độ --ground-source: Điều nguồn đi vào [CONTEXT] và trường `input`."""

    def _pipeline(self, tmp_path, contexts=None):
        llm = MagicMock()
        with patch("evol_instruct.src.evol_engine.OUTPUT_DIR", tmp_path):
            p = EvolPipeline(
                llm_client=llm, output_file="out.jsonl",
                checkpoint_file="ck.json", source_contexts=contexts,
                dedup_pool=False,
            )
        return p, llm

    def test_context_goes_into_user_message(self, tmp_path):
        p, llm = self._pipeline(tmp_path)
        llm.chat.return_value = "ok"
        p.generate_irac_response("Câu hỏi?", context="Điều 651. Người thừa kế theo pháp luật")
        messages = llm.chat.call_args.kwargs["messages"]
        assert "[CONTEXT" in messages[1]["content"]
        assert "Điều 651" in messages[1]["content"]
        assert "QUY TẮC KHI CÓ [CONTEXT]" in messages[0]["content"]

    def test_no_context_keeps_old_messages(self, tmp_path):
        p, llm = self._pipeline(tmp_path)
        llm.chat.return_value = "ok"
        p.generate_irac_response("Câu hỏi?")
        messages = llm.chat.call_args.kwargs["messages"]
        assert messages[1]["content"] == "Câu hỏi?"
        assert "[CONTEXT" not in messages[0]["content"]

    def test_record_stores_context_as_input(self, tmp_path):
        ctx = "Bộ luật Dân sự 2015\nĐiều 651. Người thừa kế theo pháp luật"
        p, llm = self._pipeline(tmp_path, contexts={"doc#dieu-651": ctx})
        evolved = "Ông A mất năm 2020 để lại nhà ở Hà Nội cho con và vợ, ai được hưởng thừa kế theo IRAC?"
        llm.chat.side_effect = [evolved, IRAC_OK]
        seed = {"id": "s1", "instruction": "Ai được thừa kế?",
                "metadata": {"source_doc_id": "doc#dieu-651"}}
        record = p.process_single(seed, technique_key="concretizing")
        assert record is not None
        assert record["input"] == ctx
        assert record["metadata"]["grounded"] is True

    def test_seed_without_source_is_ungrounded(self, tmp_path):
        p, llm = self._pipeline(tmp_path, contexts={"doc#dieu-651": "x"})
        evolved = "Ông A mất năm 2020 để lại nhà ở Hà Nội cho con và vợ, ai được hưởng thừa kế theo IRAC?"
        llm.chat.side_effect = [evolved, IRAC_OK]
        record = p.process_single({"id": "s2", "instruction": "Ai được thừa kế?"},
                                  technique_key="concretizing")
        assert record["input"] == ""
        assert record["metadata"]["grounded"] is False

    def test_context_constrains_evolve_step(self, tmp_path):
        p, llm = self._pipeline(tmp_path)
        llm.chat.return_value = "Câu hỏi mới?"
        p.evolve_instruction("Ai được thừa kế?", "deepening", context="Điều 651. Người thừa kế")
        messages = llm.chat.call_args.kwargs["messages"]
        assert "ĐIỀU LUẬT NGUỒN" in messages[0]["content"]
        assert "Điều 651" in messages[0]["content"]
        assert messages[1]["content"].rstrip().endswith("Câu hỏi viết lại:")

    def test_evolve_without_context_unchanged(self, tmp_path):
        p, llm = self._pipeline(tmp_path)
        llm.chat.return_value = "Câu hỏi mới?"
        p.evolve_instruction("Ai được thừa kế?", "deepening")
        assert "ĐIỀU LUẬT NGUỒN" not in llm.chat.call_args.kwargs["messages"][0]["content"]
