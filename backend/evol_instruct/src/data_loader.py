"""
Data Loader cho Evol-Instruct Pipeline.
Load dataset pháp luật từ HuggingFace để tạo seed questions.
Dùng riêng cho Evol-Instruct, không liên quan đến RAG data pipeline.
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from datasets import load_dataset
from loguru import logger
from tqdm import tqdm

# Import settings từ project root (backend/)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import HF_DATASET_NAME, SEEDS_DIR


def clean_html(html_content: str) -> str:
    """Làm sạch content_html → plain text."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def load_and_preprocess(
    max_items: int = 0,
    min_content_length: int = 200,
    cache: bool = True,
) -> list[dict]:
    """
    Load dataset từ HuggingFace dùng cho Evol-Instruct seed generation.
    Cache tại data/evol_instruct/seeds/preprocessed_cache.jsonl
    """
    cache_path = SEEDS_DIR / "preprocessed_cache.jsonl"

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

    logger.info(f"Loading {HF_DATASET_NAME} - config: metadata")
    ds_meta = load_dataset(HF_DATASET_NAME, "metadata", split="data")
    logger.info(f"Loading {HF_DATASET_NAME} - config: content")
    ds_content = load_dataset(HF_DATASET_NAME, "content", split="data")

    # Build metadata dict
    meta_dict = {}
    for item in tqdm(ds_meta, desc="Indexing metadata"):
        meta_dict[item["id"]] = item

    documents = []
    skipped = 0
    items = ds_content
    if max_items > 0:
        items = ds_content.select(range(min(max_items, len(ds_content))))

    for item in tqdm(items, desc="Tiền xử lý"):
        doc_id = item.get("id")
        content_raw = item.get("content_html") or item.get("content") or ""
        content_clean = clean_html(content_raw)
        if len(content_clean) < min_content_length:
            skipped += 1
            continue

        meta_item = meta_dict.get(doc_id, {})
        metadata = {
            "nganh":            (meta_item.get("nganh") or "").strip(),
            "linh_vuc":         (meta_item.get("linh_vuc") or "").strip(),
            "so_hieu":          (meta_item.get("so_ky_hieu") or "").strip(),
            "loai_van_ban":     (meta_item.get("loai_van_ban") or "").strip(),
            "co_quan_ban_hanh": (meta_item.get("co_quan_ban_hanh") or "").strip(),
            "tinh_trang":       (meta_item.get("tinh_trang_hieu_luc") or "").strip(),
        }
        documents.append({
            "doc_id": doc_id,
            "content": content_clean,
            "metadata": metadata,
            "content_length": len(content_clean),
        })

    logger.info(f"Tiền xử lý: {len(documents)} giữ lại, {skipped} bỏ qua")

    if cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            for doc in documents:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        logger.info(f"Cached → {cache_path}")

    return documents


def get_unique_categories(documents: list[dict]) -> dict:
    """Thống kê các danh mục duy nhất."""
    categories = {"nganh": set(), "linh_vuc": set(), "loai_van_ban": set(), "co_quan_ban_hanh": set()}
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
