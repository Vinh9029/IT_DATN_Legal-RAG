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


# Tăng số này mỗi khi đổi cấu trúc record do load_and_preprocess sinh ra, để
# cache cũ không bị dùng nhầm. Cache build trước khi join config 'metadata' có
# metadata rỗng toàn bộ → làm tắt âm thầm bộ lọc hallucination ở script 03/06.
CACHE_SCHEMA_VERSION = 2


def _cache_meta_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(".meta.json")


def _check_cache_version(cache_path: Path) -> bool:
    """
    Cảnh báo nếu cache được sinh bởi phiên bản code cũ. Returns True nếu hợp lệ.

    Gọi TRƯỚC khi duyệt: với 154k document, cảnh báo ở cuối vòng lặp thì người
    dùng phải chờ hết mới biết dữ liệu không dùng được.
    """
    meta_path = _cache_meta_path(cache_path)
    version = None
    if meta_path.exists():
        try:
            version = json.loads(meta_path.read_text(encoding="utf-8")).get("schema_version")
        except Exception:
            version = None

    if version != CACHE_SCHEMA_VERSION:
        logger.error(
            f"⚠️  CACHE CŨ: {cache_path.name} sinh bởi schema v{version} "
            f"(hiện tại v{CACHE_SCHEMA_VERSION}). Metadata có thể rỗng → bộ lọc "
            f"hallucination sẽ TẮT. Xoá file này (và {meta_path.name}) rồi chạy lại "
            f"01_download_data.py để rebuild."
        )
        return False
    return True


def _check_cache_freshness(cache_path: Path, sample: list[dict]):
    """Cảnh báo nếu cache cũ hoặc metadata rỗng."""
    if not _check_cache_version(cache_path):
        return

    if sample and all(not (d.get("metadata") or {}).get("so_hieu") for d in sample):
        logger.error(
            f"⚠️  {len(sample)} document đầu của cache đều KHÔNG có 'so_hieu'. "
            f"legal_refs sẽ rỗng và bộ lọc hallucination sẽ TẮT."
        )


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
                    # Dừng sớm thay vì đọc hết 2.6 GB rồi mới cắt.
                    if max_items > 0 and len(documents) >= max_items:
                        break
        _check_cache_freshness(cache_path, documents[:50])
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
        _cache_meta_path(cache_path).write_text(
            json.dumps({"schema_version": CACHE_SCHEMA_VERSION,
                        "n_documents": len(documents)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"Cached → {cache_path}")

    return documents


def iter_document_metadata(cache_only: bool = True):
    """
    Duyệt metadata của từng document mà KHÔNG giữ `content` trong RAM.

    `load_and_preprocess()` nạp cả 2.6 GB nội dung vào list chỉ để script 03/06
    lấy vài trường `so_hieu` build legal_refs. Hàm này đọc từng dòng và chỉ yield
    phần metadata.

    Args:
        cache_only: True thì chỉ đọc cache; nếu chưa có cache sẽ không tự tải
            dataset về (tránh bất ngờ tốn băng thông) mà trả về rỗng.

    Yields:
        dict metadata của từng document.
    """
    cache_path = SEEDS_DIR / "preprocessed_cache.jsonl"
    if not cache_path.exists():
        if cache_only:
            logger.warning(f"Chưa có cache {cache_path}, không duyệt được metadata.")
            return
        for doc in load_and_preprocess():
            yield doc.get("metadata", {})
        return

    # Cảnh báo NGAY, trước khi người dùng chờ hết 154k dòng.
    version_ok = _check_cache_version(cache_path)

    sample = []
    with open(cache_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                meta = json.loads(line).get("metadata", {})
            except json.JSONDecodeError as e:
                logger.warning(f"Bỏ qua dòng cache hỏng {line_num}: {e}")
                continue
            if len(sample) < 50:
                sample.append({"metadata": meta})
            yield meta

    if version_ok and sample and all(
        not (d.get("metadata") or {}).get("so_hieu") for d in sample
    ):
        logger.error(
            f"⚠️  {len(sample)} document đầu của cache đều KHÔNG có 'so_hieu'. "
            f"legal_refs sẽ rỗng và bộ lọc hallucination sẽ TẮT."
        )


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
