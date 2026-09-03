"""
Shared helper functions cho seed generation.
Dùng chung bởi 02_generate_seeds.py và 06_gemini_pipeline.py.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from loguru import logger
from tqdm import tqdm

from config.prompts import SYSTEM_SEED_GENERATOR
from evol_instruct.src.utils import generate_item_id


def generate_seeds_with_gemini(
    documents: list[dict],
    gemini,
    target_seeds: int = 1000,
    seeds_per_doc: int = 3,
) -> list[dict]:
    """
    Dùng Gemini 2.5 Flash để tạo câu hỏi pháp lý chất lượng cao.

    Args:
        documents: Danh sách documents từ HuggingFace dataset.
        gemini: GeminiClient instance.
        target_seeds: Số seeds cần đạt (dừng sớm khi đủ).
        seeds_per_doc: Số câu hỏi yêu cầu per document.

    Returns:
        Danh sách seed dicts.
    """
    seeds = []
    seen = set()
    max_docs = min(len(documents), (target_seeds // seeds_per_doc) + 20)

    logger.info(
        f"Gemini seed generation | target={target_seeds} | "
        f"seeds_per_doc={seeds_per_doc} | max_docs={max_docs}"
    )

    for doc in tqdm(documents[:max_docs], desc="Gemini seed generation"):
        if len(seeds) >= target_seeds:
            logger.info(f"Đạt {target_seeds} seeds, dừng sớm.")
            break

        content = doc["content"][:3000]
        metadata = doc.get("metadata", {})
        linh_vuc = metadata.get("linh_vuc", "Chưa xác định")
        nganh = metadata.get("nganh", "Chưa xác định")
        loai_vb = metadata.get("loai_van_ban", "")
        so_hieu = metadata.get("so_hieu", "")
        so_hieu_luat = f"{loai_vb} {so_hieu}".strip() if so_hieu else ""

        system_prompt = SYSTEM_SEED_GENERATOR.format(
            linh_vuc=linh_vuc, nganh=nganh,
        )

        user_prompt = (
            f"Dựa trên nội dung văn bản pháp luật sau, hãy tạo ra CHÍNH XÁC "
            f"{seeds_per_doc} câu hỏi pháp lý KHÁC NHAU.\n\n"
            f"Văn bản: {so_hieu_luat or 'Văn bản pháp luật Việt Nam'}\n"
            f"Lĩnh vực: {linh_vuc}\n"
            f"Nội dung:\n{content}\n\n"
            f"YÊU CẦU QUAN TRỌNG:\n"
            f"- Mỗi câu hỏi phải ĐẶT RA TÌNH HUỐNG CỤ THỂ (tên người Việt, địa điểm, thời gian).\n"
            f"- Câu hỏi phải yêu cầu phân tích theo IRAC.\n"
            f"- KHÔNG hỏi kiểu \"X là gì?\" hay \"Định nghĩa X\".\n"
            f"- Mỗi câu hỏi trên 1 DÒNG RIÊNG, KHÔNG đánh số.\n"
            f"- Độ dài mỗi câu: 30-120 từ.\n\n"
            f"Viết {seeds_per_doc} câu hỏi (mỗi câu 1 dòng):"
        )

        try:
            response = gemini.evolve(system_prompt, user_prompt)

            lines = [
                line.strip().lstrip("0123456789.-) •–*")
                for line in response.split("\n")
                if line.strip() and len(line.strip()) > 25
            ]

            for line in lines[:seeds_per_doc]:
                line = line.strip()
                norm = line.lower()
                if norm in seen:
                    continue
                seen.add(norm)

                seed = {
                    "id": generate_item_id(line),
                    "instruction": line,
                    "metadata": {
                        "linh_vuc": linh_vuc,
                        "nganh": nganh,
                        "so_hieu_luat": so_hieu_luat,
                        "generator": "gemini",
                    },
                }
                seeds.append(seed)

        except Exception as e:
            logger.warning(f"Gemini error: {e}")
            continue

    if len(seeds) > target_seeds:
        seeds = seeds[:target_seeds]

    logger.info(
        f"Gemini tạo {len(seeds)} seeds | "
        f"dedup loại {len(seen) - len(seeds)} trùng"
    )
    return seeds


def generate_seeds_with_llm_client(
    documents: list[dict],
    llm,
    target_seeds: int = 1000,
    seeds_per_doc: int = 3,
) -> list[dict]:
    """
    Dùng OpenAI-compatible LLM (LM Studio hoặc Rented API) để tạo câu hỏi pháp lý chất lượng cao.

    Args:
        documents: Danh sách documents từ HuggingFace dataset.
        llm: LLMClient instance.
        target_seeds: Số seeds cần đạt (dừng sớm khi đủ).
        seeds_per_doc: Số câu hỏi yêu cầu per document.

    Returns:
        Danh sách seed dicts.
    """
    seeds = []
    seen = set()
    max_docs = min(len(documents), (target_seeds // seeds_per_doc) + 20)

    logger.info(
        f"LLM seed generation | target={target_seeds} | "
        f"seeds_per_doc={seeds_per_doc} | max_docs={max_docs}"
    )

    for doc in tqdm(documents[:max_docs], desc="LLM seed generation"):
        if len(seeds) >= target_seeds:
            logger.info(f"Đạt {target_seeds} seeds, dừng sớm.")
            break

        content = doc["content"][:3000]
        metadata = doc.get("metadata", {})
        linh_vuc = metadata.get("linh_vuc", "Chưa xác định")
        nganh = metadata.get("nganh", "Chưa xác định")
        loai_vb = metadata.get("loai_van_ban", "")
        so_hieu = metadata.get("so_hieu", "")
        so_hieu_luat = f"{loai_vb} {so_hieu}".strip() if so_hieu else ""

        system_prompt = SYSTEM_SEED_GENERATOR.format(
            linh_vuc=linh_vuc, nganh=nganh,
        )

        user_prompt = (
            f"Dựa trên nội dung văn bản pháp luật sau, hãy tạo ra CHÍNH XÁC "
            f"{seeds_per_doc} câu hỏi pháp lý KHÁC NHAU.\n\n"
            f"Văn bản: {so_hieu_luat or 'Văn bản pháp luật Việt Nam'}\n"
            f"Lĩnh vực: {linh_vuc}\n"
            f"Nội dung:\n{content}\n\n"
            f"YÊU CẦU QUAN TRỌNG:\n"
            f"- Mỗi câu hỏi phải ĐẶT RA TÌNH HUỐNG CỤ THỂ (tên người Việt, địa điểm, thời gian).\n"
            f"- Câu hỏi phải yêu cầu phân tích theo IRAC.\n"
            f"- KHÔNG hỏi kiểu \"X là gì?\" hay \"Định nghĩa X\".\n"
            f"- Mỗi câu hỏi trên 1 DÒNG RIÊNG, KHÔNG đánh số.\n"
            f"- Độ dài mỗi câu: 30-120 từ.\n\n"
            f"Viết {seeds_per_doc} câu hỏi (mỗi câu 1 dòng):"
        )

        try:
            response = llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
            )

            lines = [
                line.strip().lstrip("0123456789.-) •–*")
                for line in response.split("\n")
                if line.strip() and len(line.strip()) > 25
            ]

            for line in lines[:seeds_per_doc]:
                line = line.strip()
                norm = line.lower()
                if norm in seen:
                    continue
                seen.add(norm)

                seed = {
                    "id": generate_item_id(line),
                    "instruction": line,
                    "metadata": {
                        "linh_vuc": linh_vuc,
                        "nganh": nganh,
                        "so_hieu_luat": so_hieu_luat,
                        "generator": "llm",
                    },
                }
                seeds.append(seed)

        except Exception as e:
            logger.warning(f"LLM seed gen error: {e}")
            continue

    if len(seeds) > target_seeds:
        seeds = seeds[:target_seeds]

    logger.info(
        f"LLM tạo {len(seeds)} seeds | "
        f"dedup loại {len(seen) - len(seeds)} trùng"
    )
    return seeds

