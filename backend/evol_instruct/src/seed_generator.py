"""
Seed Generator - Tạo câu hỏi hạt giống (seed prompts) từ dữ liệu pháp luật.

Pipeline:
1. Nhận documents đã tiền xử lý (từ data_loader)
2. Trích xuất thực thể pháp lý (NER) bằng regex + underthesea
3. Sinh seed instructions từ templates (multi-template per doc)
4. Dedup theo nội dung → loại trùng lặp
5. Lưu seeds vào JSONL
"""

import random
import re
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from config.prompts import SEED_TEMPLATES, SYSTEM_SEED_GENERATOR
from config.settings import SEEDS_DIR, MAX_SEEDS
from evol_instruct.src.llm_client import LLMClient
from evol_instruct.src.utils import save_jsonl, load_jsonl, generate_item_id


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

    # 3. Trích xuất nội dung chính - lấy NHIỀU nội dung nếu có
    noi_dungs = extract_multiple_contents(text)
    if noi_dungs:
        entities["noi_dung"] = noi_dungs[0]
        entities["_all_noi_dungs"] = noi_dungs  # Lưu tất cả để tạo nhiều seeds

    return entities


def extract_multiple_contents(text: str) -> list[str]:
    """
    Trích xuất NHIỀU nội dung/điều luật từ text để tạo nhiều seeds cho 1 document.

    Returns:
        Danh sách nội dung (tối đa 5).
    """
    contents = []

    # Tìm tất cả Điều luật
    dieu_matches = re.findall(r"(Điều\s+\d+[^\n]{0,150})", text)
    for match in dieu_matches[:5]:
        clean = match.strip()
        if len(clean) >= 20:
            contents.append(clean)

    # Nếu chưa đủ, tìm Chương/Mục
    if len(contents) < 3:
        chuong_matches = re.findall(r"(Chương\s+[IVXLCDM]+[^\n]{0,100})", text)
        for match in chuong_matches[:3]:
            clean = match.strip()
            if len(clean) >= 15 and clean not in contents:
                contents.append(clean)

    # Fallback: câu dài đủ ý nghĩa
    if not contents:
        sentences = re.split(r"[.!?]\s+", text[:2000])
        for sent in sentences:
            sent = sent.strip()
            if len(sent) >= 25 and not sent.startswith(("Số:", "Ngày", "Căn cứ")):
                contents.append(sent[:200])
                if len(contents) >= 3:
                    break

    return contents


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
    target_seeds: int = 1000,
    templates_per_doc: int = 0,
) -> list[dict]:
    """
    Tạo seed instructions từ templates + entities đã trích xuất.

    Chiến lược đạt 700-1000 seeds:
    - Mỗi document → trích NHIỀU nội dung (Điều luật khác nhau)
    - Mỗi nội dung × NHIỀU templates → nhiều seeds
    - Dedup cuối cùng để loại trùng lặp

    Args:
        documents: Danh sách documents đã tiền xử lý.
        target_seeds: Số seeds MỤC TIÊU cần đạt (mặc định 1000).
        templates_per_doc: Số templates áp dụng cho mỗi nội dung (0 = tự tính).

    Returns:
        Danh sách seed dicts: {id, instruction, metadata, source_entities}
    """
    seeds = []
    seen_instructions = set()  # Dedup
    dup_count = 0

    # Tự tính templates_per_doc nếu chưa chỉ định
    if templates_per_doc <= 0:
        # Ước lượng: mỗi doc trung bình cho 2-3 nội dung × N templates
        avg_contents_per_doc = 2.5
        if len(documents) > 0:
            templates_per_doc = max(2, int(target_seeds / (len(documents) * avg_contents_per_doc)) + 1)
        else:
            templates_per_doc = 3
        templates_per_doc = min(templates_per_doc, len(SEED_TEMPLATES))

    logger.info(
        f"Seed generation: {len(documents)} docs × ~{templates_per_doc} templates/content | "
        f"target={target_seeds}"
    )

    for doc in tqdm(documents, desc="Tạo seed prompts"):
        content = doc["content"]
        metadata = doc.get("metadata", {})

        # Trích xuất entities
        entities = extract_legal_entities(content, metadata)

        # Kiểm tra entities đủ để tạo seed
        if not entities["so_hieu_luat"] and not entities.get("noi_dung"):
            continue

        # Lấy tất cả nội dung trích xuất được
        all_noi_dungs = entities.get("_all_noi_dungs", [])
        if not all_noi_dungs and entities["noi_dung"]:
            all_noi_dungs = [entities["noi_dung"]]

        if not all_noi_dungs:
            continue

        # Chọn NHIỀU templates cho mỗi nội dung
        selected_templates = random.sample(
            SEED_TEMPLATES,
            min(templates_per_doc, len(SEED_TEMPLATES)),
        )

        for noi_dung in all_noi_dungs:
            for template in selected_templates:
                template_params = {
                    "so_hieu_luat": entities["so_hieu_luat"] or "văn bản pháp luật liên quan",
                    "co_quan_ban_hanh": entities["co_quan_ban_hanh"] or "cơ quan có thẩm quyền",
                    "noi_dung": noi_dung,
                }

                try:
                    instruction = template.format(**template_params)
                except KeyError as e:
                    logger.debug(f"Template format error: {e}")
                    continue

                # Dedup: bỏ qua nếu instruction đã tồn tại
                instruction_normalized = instruction.strip().lower()
                if instruction_normalized in seen_instructions:
                    dup_count += 1
                    continue
                seen_instructions.add(instruction_normalized)

                seed = {
                    "id": generate_item_id(instruction),
                    "instruction": instruction,
                    "metadata": {
                        "linh_vuc": entities["linh_vuc"],
                        "nganh": entities["nganh"],
                    },
                    "source_entities": {
                        k: v for k, v in entities.items()
                        if not k.startswith("_")
                    },
                }
                seeds.append(seed)

        # Dừng sớm nếu đã đạt target
        if target_seeds > 0 and len(seeds) >= target_seeds:
            logger.info(f"Đạt target {target_seeds} seeds, dừng sớm.")
            break

    # Cắt nếu vượt target
    if target_seeds > 0 and len(seeds) > target_seeds:
        seeds = seeds[:target_seeds]

    logger.info(
        f"Đã tạo {len(seeds)} seed prompts từ {len(documents)} documents "
        f"(dedup loại {dup_count} trùng)"
    )
    return seeds


def generate_seeds_with_llm(
    documents: list[dict],
    llm_client: LLMClient,
    max_docs: int = 0,
    seeds_per_doc: int = 3,
) -> list[dict]:
    """
    Tạo seed instructions bằng LLM (nâng cao, đa dạng hơn templates).

    Args:
        documents: Danh sách documents đã tiền xử lý.
        llm_client: LLMClient instance.
        max_docs: Số documents tối đa để xử lý (0 = tất cả).
        seeds_per_doc: Số seeds tạo ra cho mỗi document.

    Returns:
        Danh sách seed dicts.
    """
    seeds = []
    seen = set()
    max_docs = max_docs or len(documents)

    for doc in tqdm(documents[:max_docs], desc="Tạo seeds bằng LLM"):
        content = doc["content"][:2000]  # Giới hạn context
        metadata = doc.get("metadata", {})

        system_prompt = SYSTEM_SEED_GENERATOR.format(
            linh_vuc=metadata.get("linh_vuc", "Chưa xác định"),
            nganh=metadata.get("nganh", "Chưa xác định"),
        )

        user_prompt = (
            f"Dựa trên nội dung pháp luật sau, hãy tạo {seeds_per_doc} câu hỏi pháp lý "
            f"mang tính ÁP DỤNG thực tiễn. Mỗi câu hỏi phải có tình huống cụ thể, "
            f"KHÔNG hỏi kiểu định nghĩa đơn giản. Mỗi câu trên một dòng mới.\n\n"
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
                max_tokens=1024,
            )

            # Parse response thành từng câu hỏi
            lines = [
                line.strip().lstrip("0123456789.-) ")
                for line in response.strip().split("\n")
                if line.strip() and len(line.strip()) > 20
            ]

            for line in lines[:seeds_per_doc]:
                # Dedup
                norm = line.strip().lower()
                if norm in seen:
                    continue
                seen.add(norm)

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
                # Loại bỏ _all_noi_dungs (internal field)
                seed["source_entities"] = {
                    k: v for k, v in seed["source_entities"].items()
                    if not k.startswith("_")
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
