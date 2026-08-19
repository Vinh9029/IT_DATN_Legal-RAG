"""Unit tests cho Seed Generator."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.seed_generator import (
    extract_legal_entities,
    extract_multiple_contents,
    generate_seeds_from_templates,
)


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


class TestExtractMultipleContents:
    def test_multiple_dieu(self):
        text = (
            "Điều 584. Căn cứ phát sinh trách nhiệm bồi thường thiệt hại\n"
            "Điều 585. Nguyên tắc bồi thường thiệt hại\n"
            "Điều 586. Năng lực chịu trách nhiệm bồi thường\n"
        )
        contents = extract_multiple_contents(text)
        assert len(contents) >= 3
        assert any("584" in c for c in contents)
        assert any("585" in c for c in contents)

    def test_empty_text(self):
        contents = extract_multiple_contents("")
        assert contents == []

    def test_fallback_sentences(self):
        text = "Cơ quan nhà nước phải bảo đảm quyền lợi hợp pháp của công dân."
        contents = extract_multiple_contents(text)
        assert len(contents) >= 1


class TestGenerateSeeds:
    def test_generates_multiple_seeds_per_doc(self):
        """Mỗi doc có nhiều Điều → phải tạo được nhiều seeds."""
        documents = [
            {
                "content": (
                    "Điều 584. Căn cứ phát sinh trách nhiệm bồi thường thiệt hại\n"
                    "Điều 585. Nguyên tắc bồi thường thiệt hại\n"
                    "Điều 586. Năng lực chịu trách nhiệm bồi thường\n"
                ),
                "metadata": {
                    "so_hieu": "91/2015/QH13",
                    "loai_van_ban": "Luật",
                    "co_quan_ban_hanh": "Quốc hội",
                    "linh_vuc": "Dân sự",
                    "nganh": "Tư pháp",
                },
            }
        ]
        seeds = generate_seeds_from_templates(documents, target_seeds=10)
        assert len(seeds) > 1  # Phải tạo được nhiều seeds từ 1 doc
        assert "instruction" in seeds[0]
        assert "id" in seeds[0]

    def test_target_seeds_limit(self):
        """Không vượt quá target_seeds."""
        documents = [
            {
                "content": "Điều 100. Quy định chung\nĐiều 101. Quy định cụ thể\nĐiều 102. Xử phạt",
                "metadata": {
                    "so_hieu": "01/2020/NĐ-CP", "loai_van_ban": "Nghị định",
                    "co_quan_ban_hanh": "Chính phủ", "linh_vuc": "Hành chính", "nganh": "Hành chính",
                },
            }
        ] * 10  # 10 docs giống nhau
        seeds = generate_seeds_from_templates(documents, target_seeds=5)
        assert len(seeds) <= 5

    def test_empty_documents(self):
        seeds = generate_seeds_from_templates([], target_seeds=10)
        assert seeds == []

    def test_missing_metadata_skipped(self):
        documents = [{"content": "abc", "metadata": {}}]
        seeds = generate_seeds_from_templates(documents, target_seeds=10)
        assert len(seeds) == 0

    def test_dedup_no_duplicates(self):
        """Không có 2 seeds trùng instruction."""
        documents = [
            {
                "content": "Điều 584. Căn cứ phát sinh trách nhiệm bồi thường thiệt hại",
                "metadata": {
                    "so_hieu": "91/2015/QH13", "loai_van_ban": "Luật",
                    "co_quan_ban_hanh": "Quốc hội", "linh_vuc": "Dân sự", "nganh": "Tư pháp",
                },
            }
        ] * 5  # 5 docs GIỐNG NHAU
        seeds = generate_seeds_from_templates(documents, target_seeds=100)
        instructions = [s["instruction"] for s in seeds]
        assert len(instructions) == len(set(instructions))  # Không trùng
