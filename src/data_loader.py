"""
Data Loader - Load & tiền xử lý dataset pháp luật Việt Nam từ HuggingFace.

Pipeline:
1. Load dataset th1nhng0/vietnamese-legal-documents
2. Làm sạch content_html → plain text (BeautifulSoup)
3. Trích xuất metadata (nganh, linh_vuc)
4. Cache local để tránh tải lại
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from datasets import load_dataset
from loguru import logger
from tqdm import tqdm

from config.settings import (
    HF_DATASET_NAME,
    HF_DATASET_CONFIG,
    RAW_DATA_DIR,
)


def clean_html(html_content: str) -> str:
    """
    Làm sạch content_html bằng BeautifulSoup → plain text.

    - Loại bỏ tất cả HTML tags.
    - Chuẩn hóa khoảng trắng (nhiều dòng trống → 1 dòng).
    - Loại bỏ ký tự đặc biệt thừa.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "lxml")

    # Loại bỏ script và style tags
    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # Chuẩn hóa khoảng trắng
    text = re.sub(r"\n{3,}", "\n\n", text)  # Nhiều dòng trống → 2 dòng
    text = re.sub(r"[ \t]+", " ", text)  # Nhiều spaces → 1 space
    text = text.strip()

    return text


def extract_metadata(item: dict) -> dict:
    """
    Trích xuất metadata quan trọng từ một item trong dataset.

    Returns:
        Dict chứa các trường metadata đã chuẩn hóa.
    """
    return {
        "nganh": (item.get("nganh") or "").strip(),
        "linh_vuc": (item.get("linh_vuc") or "").strip(),
        "so_hieu": (item.get("so_hieu") or "").strip(),
        "loai_van_ban": (item.get("loai_van_ban") or "").strip(),
        "co_quan_ban_hanh": (item.get("co_quan_ban_hanh") or "").strip(),
        "nguoi_ky": (item.get("nguoi_ky") or "").strip(),
        "ngay_ban_hanh": (item.get("ngay_ban_hanh") or "").strip(),
        "ngay_hieu_luc": (item.get("ngay_hieu_luc") or "").strip(),
        "tinh_trang": (item.get("tinh_trang") or "").strip(),
    }


def load_and_preprocess(
    max_items: int = 0,
    min_content_length: int = 200,
    cache: bool = True,
) -> list[dict]:
    """
    Load dataset từ HuggingFace, tiền xử lý và trả về danh sách documents.

    Args:
        max_items: Số lượng items tối đa (0 = tất cả).
        min_content_length: Độ dài tối thiểu của content (ký tự) để giữ lại.
        cache: Nếu True, cache kết quả vào local file.

    Returns:
        Danh sách dict, mỗi dict chứa:
        - content: Plain text đã làm sạch
        - metadata: Dict metadata (nganh, linh_vuc, so_hieu, ...)
        - content_length: Số ký tự content
    """
    cache_path = RAW_DATA_DIR / "preprocessed_cache.jsonl"

    # Kiểm tra cache
    if cache and cache_path.exists():
        logger.info(f"Đọc từ cache: {cache_path}")
        documents = []
        with open(cache_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    documents.append(json.loads(line))
        if max_items > 0:
            documents = documents[:max_items]
        logger.info(f"Loaded {len(documents)} documents từ cache")
        return documents

    # Load từ HuggingFace
    logger.info(f"Loading dataset: {HF_DATASET_NAME} (config={HF_DATASET_CONFIG})")
    ds = load_dataset(HF_DATASET_NAME, HF_DATASET_CONFIG)

    # Lấy split chính (thường là 'train')
    split_name = list(ds.keys())[0]
    dataset = ds[split_name]
    logger.info(f"Dataset loaded: {len(dataset)} items (split={split_name})")

    # Tiền xử lý
    documents = []
    skipped = 0

    items = dataset
    if max_items > 0:
        items = dataset.select(range(min(max_items, len(dataset))))

    for item in tqdm(items, desc="Tiền xử lý documents"):
        # Làm sạch HTML
        content_raw = item.get("content_html") or item.get("content") or ""
        content_clean = clean_html(content_raw)

        # Lọc content quá ngắn
        if len(content_clean) < min_content_length:
            skipped += 1
            continue

        # Trích xuất metadata
        metadata = extract_metadata(item)

        doc = {
            "content": content_clean,
            "metadata": metadata,
            "content_length": len(content_clean),
        }
        documents.append(doc)

    logger.info(
        f"Tiền xử lý hoàn tất: {len(documents)} documents giữ lại, "
        f"{skipped} bỏ qua (content < {min_content_length} chars)"
    )

    # Cache kết quả
    if cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            for doc in documents:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        logger.info(f"Cached {len(documents)} documents → {cache_path}")

    return documents


def get_unique_categories(documents: list[dict]) -> dict:
    """
    Thống kê các danh mục (ngành, lĩnh vực) duy nhất trong dataset.

    Returns:
        Dict chứa danh sách unique values cho mỗi trường metadata.
    """
    categories = {
        "nganh": set(),
        "linh_vuc": set(),
        "loai_van_ban": set(),
        "co_quan_ban_hanh": set(),
    }

    for doc in documents:
        meta = doc.get("metadata", {})
        for key in categories:
            val = meta.get(key, "")
            if val:
                categories[key].add(val)

    result = {k: sorted(list(v)) for k, v in categories.items()}

    for key, values in result.items():
        logger.info(f"  {key}: {len(values)} unique values")

    return result
