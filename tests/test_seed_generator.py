"""Unit tests cho Seed Generator."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.seed_generator import extract_legal_entities, generate_seeds_from_templates


class TestExtractLegalEntities:
    def test_from_metadata(self):
        metadata = {
            "so_hieu": "100/2019/NĐ-CP",
            "loai_van_ban": "Nghị định",
            "co_quan_ban_hanh": "Chính phủ",
            "linh_vuc": "Giao thông",
            "nganh": "Hành chính",
        }
        entities = extract_legal_entities("", metadata)
        assert entities["so_hieu_luat"] == "Nghị định 100/2019/NĐ-CP"
        assert entities["co_quan_ban_hanh"] == "Chính phủ"
        assert entities["linh_vuc"] == "Giao thông"

    def test_regex_extraction(self):
        text = "Theo Nghị định 100/2019/NĐ-CP quy định về xử phạt vi phạm hành chính"
        entities = extract_legal_entities(text, {})
        assert "100/2019/NĐ-CP" in entities["so_hieu_luat"]

    def test_empty_input(self):
        entities = extract_legal_entities("", {})
        assert entities["so_hieu_luat"] == ""

    def test_content_extraction(self):
        text = "Điều 584. Căn cứ phát sinh trách nhiệm bồi thường thiệt hại"
        entities = extract_legal_entities(text, {})
        assert "Điều 584" in entities["noi_dung"]


class TestGenerateSeeds:
    def test_generates_seeds(self):
        documents = [
            {
                "content": "Điều 584 quy định về trách nhiệm bồi thường",
                "metadata": {
                    "so_hieu": "91/2015/QH13",
                    "loai_van_ban": "Luật",
                    "co_quan_ban_hanh": "Quốc hội",
                    "linh_vuc": "Dân sự",
                    "nganh": "Tư pháp",
                },
            }
        ]
        seeds = generate_seeds_from_templates(documents, max_seeds=5)
        assert len(seeds) > 0
        assert "instruction" in seeds[0]
        assert "id" in seeds[0]

    def test_empty_documents(self):
        seeds = generate_seeds_from_templates([], max_seeds=10)
        assert seeds == []

    def test_missing_metadata_skipped(self):
        documents = [{"content": "abc", "metadata": {}}]
        seeds = generate_seeds_from_templates(documents)
        assert len(seeds) == 0  # Không đủ entities
