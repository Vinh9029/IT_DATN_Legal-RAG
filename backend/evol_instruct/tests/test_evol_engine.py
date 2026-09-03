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
