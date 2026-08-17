"""
Seed Generator - Tạo câu hỏi hạt giống (seed prompts) từ dữ liệu pháp luật.

Pipeline:
1. Nhận documents đã tiền xử lý (từ data_loader)
2. Trích xuất thực thể pháp lý (NER) bằng underthesea
3. Sinh seed instructions từ templates
4. Lưu seeds vào JSONL
"""

import random
import re
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from config.prompts import SEED_TEMPLATES, SYSTEM_SEED_GENERATOR
from config.settings import SEEDS_DIR, MAX_SEEDS
from src.llm_client import LLMClient
from src.utils import save_jsonl, load_jsonl, generate_item_id


# ── NER cho Pháp luật Việt Nam ────────────────────────────────────

def extract_legal_entities(text: str, metadata: dict) -> dict:
    """
    Trích xuất thực thể pháp lý từ text và metadata.

    Kết hợp:
    - Metadata trực tiếp (so_hieu, co_quan_ban_hanh)
    - Regex patterns cho số hiệu luật trong content
    - underthesea NER (nếu cần bổ sung)

    Returns:
        Dict chứa các entities: so_hieu_luat, co_quan_ban_hanh, noi_dung
    """
    entities = {
        "so_hieu_luat": "",
        "co_quan_ban_hanh": "",
        "noi_dung": "",
        "linh_vuc": "",
        "nganh": "",
    }

    # 1. Từ metadata (nguồn chính xác nhất)
    entities["co_quan_ban_hanh"] = metadata.get("co_quan_ban_hanh", "")
    entities["linh_vuc"] = metadata.get("linh_vuc", "")
    entities["nganh"] = metadata.get("nganh", "")

    # Xây dựng số hiệu luật từ metadata
    so_hieu = metadata.get("so_hieu", "")
    loai_van_ban = metadata.get("loai_van_ban", "")
    if so_hieu and loai_van_ban:
        entities["so_hieu_luat"] = f"{loai_van_ban} {so_hieu}"
    elif so_hieu:
        entities["so_hieu_luat"] = so_hieu

    # 2. Regex patterns cho số hiệu luật trong content
    if not entities["so_hieu_luat"]:
        patterns = [
            r"(Luật\s+[^\n,\.]{5,50}(?:năm\s+\d{4}|\d{4}))",
            r"(Nghị\s+định\s+\d+/\d{4}/NĐ-CP)",
            r"(Thông\s+tư\s+\d+/\d{4}/TT-\w+)",
            r"(Bộ\s+luật\s+[^\n,\.]{5,40}(?:năm\s+\d{4}|\d{4}))",
            r"(Quyết\s+định\s+\d+/\d{4}/QĐ-\w+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                entities["so_hieu_luat"] = match.group(1).strip()
                break

    # 3. Trích xuất nội dung chính (câu đầu tiên có ý nghĩa)
    if not entities["noi_dung"]:
        # Tìm tiêu đề hoặc nội dung chính
        title_patterns = [
            r"(?:Điều\s+\d+[^\n]*)",
            r"(?:Chương\s+[IVXLCDM]+[^\n]*)",
            r"(?:Mục\s+\d+[^\n]*)",
        ]
        for pattern in title_patterns:
            match = re.search(pattern, text)
            if match:
                entities["noi_dung"] = match.group(0).strip()
                break

        # Fallback: lấy phần nội dung tóm tắt
        if not entities["noi_dung"]:
            # Lấy câu đầu tiên có độ dài >= 20 ký tự
            sentences = re.split(r"[.!?]\s+", text[:1000])
            for sent in sentences:
                sent = sent.strip()
                if len(sent) >= 20 and not sent.startswith(("Số:", "Ngày")):
                    entities["noi_dung"] = sent[:200]
                    break

    return entities


def try_ner_underthesea(text: str) -> list[dict]:
    """
    Sử dụng underthesea NER để trích xuất thực thể bổ sung.

    Returns:
        Danh sách entities [{text, label}]
    """
    try:
        from underthesea import ner
        # Chỉ phân tích 500 ký tự đầu (tốc độ)
        results = ner(text[:500])
        entities = []
        for chunk in results:
            if len(chunk) >= 4 and chunk[3] != "O":
                entities.append({
                    "text": chunk[0],
                    "label": chunk[3],
                })
        return entities
    except ImportError:
        logger.warning("underthesea chưa cài đặt. Bỏ qua NER bổ sung.")
        return []
    except Exception as e:
        logger.debug(f"NER underthesea lỗi: {e}")
        return []


# ── Seed Generation ──────────────────────────────────────────────

def generate_seeds_from_templates(
    documents: list[dict],
    max_seeds: int = 0,
) -> list[dict]:
    """
    Tạo seed instructions từ templates + entities đã trích xuất.

    Args:
        documents: Danh sách documents đã tiền xử lý.
        max_seeds: Số seeds tối đa (0 = tất cả).

    Returns:
        Danh sách seed dicts: {id, instruction, metadata, source_entities}
    """
    seeds = []
    max_seeds = max_seeds or MAX_SEEDS or len(documents)

    for doc in tqdm(documents[:max_seeds], desc="Tạo seed prompts"):
        content = doc["content"]
        metadata = doc.get("metadata", {})

        # Trích xuất entities
        entities = extract_legal_entities(content, metadata)

        # Kiểm tra entities đủ để tạo seed
        if not entities["so_hieu_luat"] and not entities["noi_dung"]:
            continue

        # Chọn random template và format
        template = random.choice(SEED_TEMPLATES)

        # Chuẩn bị params cho template
        template_params = {
            "so_hieu_luat": entities["so_hieu_luat"] or "văn bản pháp luật liên quan",
            "co_quan_ban_hanh": entities["co_quan_ban_hanh"] or "cơ quan có thẩm quyền",
            "noi_dung": entities["noi_dung"] or "nội dung quy định",
        }

        try:
            instruction = template.format(**template_params)
        except KeyError as e:
            logger.debug(f"Template format error: {e}")
            continue

        seed = {
            "id": generate_item_id(instruction),
            "instruction": instruction,
            "metadata": {
                "linh_vuc": entities["linh_vuc"],
                "nganh": entities["nganh"],
            },
            "source_entities": entities,
        }
        seeds.append(seed)

    logger.info(f"Đã tạo {len(seeds)} seed prompts từ {len(documents)} documents")
    return seeds


def generate_seeds_with_llm(
    documents: list[dict],
    llm_client: LLMClient,
    max_seeds: int = 0,
    seeds_per_doc: int = 2,
) -> list[dict]:
    """
    Tạo seed instructions bằng LLM (nâng cao, đa dạng hơn templates).

    Args:
        documents: Danh sách documents đã tiền xử lý.
        llm_client: LLMClient instance.
        max_seeds: Số documents tối đa để xử lý.
        seeds_per_doc: Số seeds tạo ra cho mỗi document.

    Returns:
        Danh sách seed dicts.
    """
    seeds = []
    max_docs = max_seeds or MAX_SEEDS or len(documents)

    for doc in tqdm(documents[:max_docs], desc="Tạo seeds bằng LLM"):
        content = doc["content"][:2000]  # Giới hạn context
        metadata = doc.get("metadata", {})

        system_prompt = SYSTEM_SEED_GENERATOR.format(
            linh_vuc=metadata.get("linh_vuc", "Chưa xác định"),
            nganh=metadata.get("nganh", "Chưa xác định"),
        )

        user_prompt = (
            f"Dựa trên nội dung pháp luật sau, hãy tạo {seeds_per_doc} câu hỏi pháp lý "
            f"đơn giản, rõ ràng. Mỗi câu hỏi trên một dòng mới.\n\n"
            f"Nội dung:\n{content}\n\n"
            f"Các câu hỏi:"
        )

        try:
            response = llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=512,
            )

            # Parse response thành từng câu hỏi
            lines = [
                line.strip().lstrip("0123456789.-) ")
                for line in response.strip().split("\n")
                if line.strip() and len(line.strip()) > 15
            ]

            for line in lines[:seeds_per_doc]:
                seed = {
                    "id": generate_item_id(line),
                    "instruction": line,
                    "metadata": {
                        "linh_vuc": metadata.get("linh_vuc", ""),
                        "nganh": metadata.get("nganh", ""),
                    },
                    "source_entities": extract_legal_entities(
                        doc["content"], metadata
                    ),
                }
                seeds.append(seed)

        except Exception as e:
            logger.warning(f"Lỗi tạo seed bằng LLM: {e}")
            continue

    logger.info(f"Đã tạo {len(seeds)} seeds bằng LLM từ {min(max_docs, len(documents))} documents")
    return seeds


def save_seeds(seeds: list[dict], filename: str = "seeds.jsonl"):
    """Lưu seeds vào file JSONL."""
    filepath = SEEDS_DIR / filename
    save_jsonl(seeds, filepath, mode="w")
    logger.info(f"Đã lưu {len(seeds)} seeds → {filepath}")
    return filepath


def load_seeds(filename: str = "seeds.jsonl") -> list[dict]:
    """Đọc seeds từ file JSONL."""
    filepath = SEEDS_DIR / filename
    seeds = load_jsonl(filepath)
    logger.info(f"Đã đọc {len(seeds)} seeds ← {filepath}")
    return seeds
