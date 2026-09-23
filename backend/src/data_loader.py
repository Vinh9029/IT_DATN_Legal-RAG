"""
Data Loader - Load & tiền xử lý dataset pháp luật Việt Nam từ HuggingFace.

Pipeline:
1. Load dataset th1nhng0/vietnamese-legal-documents (cả content và metadata)
2. Join content và metadata theo ID
3. Làm sạch content_html → plain text (BeautifulSoup)
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
    Trích xuất metadata quan trọng từ item metadata join được.
    """
    return {
        "nganh": (item.get("nganh") or "").strip(),
        "linh_vuc": (item.get("linh_vuc") or "").strip(),
        "so_hieu": (item.get("so_ky_hieu") or "").strip(),
        "loai_van_ban": (item.get("loai_van_ban") or "").strip(),
        "co_quan_ban_hanh": (item.get("co_quan_ban_hanh") or "").strip(),
        "nguoi_ky": (item.get("nguoi_ky") or "").strip(),
        "ngay_ban_hanh": (item.get("ngay_ban_hanh") or "").strip(),
        "ngay_hieu_luc": (item.get("ngay_co_hieu_luc") or "").strip(),
        "tinh_trang": (item.get("tinh_trang_hieu_luc") or "").strip(),
    }


def _get_parquet_paths():
    """Tìm đường dẫn file metadata.parquet và content.parquet trong cache HF hoặc tải về."""
    import glob
    from config.settings import BASE_DIR
    
    # 1. Kiểm tra trong local cache folder data/hf_cache
    repo_slug = HF_DATASET_NAME.replace("/", "--")
    pattern = str(BASE_DIR / "data" / "hf_cache" / "hub" / f"datasets--{repo_slug}" / "snapshots" / "*" / "data")
    snapshot_dirs = glob.glob(pattern)
    if snapshot_dirs:
        d = Path(snapshot_dirs[0])
        m = d / "metadata.parquet"
        c = d / "content.parquet"
        if m.exists() and c.exists():
            return m, c

    # 2. Thử tải qua hf_hub_download nếu chưa có
    try:
        from huggingface_hub import hf_hub_download
        m = hf_hub_download(repo_id=HF_DATASET_NAME, filename="data/metadata.parquet", repo_type="dataset")
        c = hf_hub_download(repo_id=HF_DATASET_NAME, filename="data/content.parquet", repo_type="dataset")
        return Path(m), Path(c)
    except Exception as e:
        logger.warning(f"Không thể tải trực tiếp parquet qua hf_hub_download: {e}")
        return None, None


def load_and_preprocess(
    max_items: int = 0,
    min_content_length: int = 200,
    cache: bool = True,
) -> list[dict]:
    """
    Load dataset từ HuggingFace, tiền xử lý và trả về danh sách documents.
    Kết hợp cả config 'content' và 'metadata'.
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

    meta_path, content_path = _get_parquet_paths()

    # Phương án tối ưu và tránh file lock Windows: Đọc trực tiếp parquet bằng pyarrow
    if meta_path and content_path:
        logger.info(f"Đọc trực tiếp từ parquet: {meta_path.name}, {content_path.name}")
        import pyarrow.parquet as pq
        import pyarrow.dataset as ds

        logger.info("Đang đọc metadata vào bộ nhớ...")
        meta_table = pq.read_table(meta_path)
        meta_dict = {}
        for batch in meta_table.to_batches():
            d = batch.to_pydict()
            for i in range(len(d["id"])):
                meta_dict[d["id"][i]] = {k: d[k][i] for k in d}
        logger.info(f"Đã load {len(meta_dict)} records metadata.")

        logger.info("Đang xử lý content theo từng batch...")
        documents = []
        skipped = 0
        dataset = ds.dataset(content_path, format="parquet")
        scanner = dataset.scanner(columns=["id", "content_html"], batch_size=2000)

        # Tính tổng số records để hiển thị progress bar
        total_rows = pq.read_metadata(content_path).num_rows
        target_rows = min(max_items, total_rows) if max_items > 0 else total_rows
        pbar = tqdm(total=target_rows, desc="Tiền xử lý documents")

        stop_processing = False
        for batch in scanner.to_batches():
            d = batch.to_pydict()
            ids = d["id"]
            contents = d["content_html"]

            for doc_id, content_raw in zip(ids, contents):
                content_clean = clean_html(content_raw or "")

                if len(content_clean) < min_content_length:
                    skipped += 1
                else:
                    meta_item = meta_dict.get(doc_id, {})
                    metadata = extract_metadata(meta_item)

                    doc = {
                        "doc_id": doc_id,
                        "content": content_clean,
                        "metadata": metadata,
                        "content_length": len(content_clean),
                    }
                    documents.append(doc)

                pbar.update(1)
                if max_items > 0 and (len(documents) + skipped) >= max_items:
                    stop_processing = True
                    break

            if stop_processing:
                break

        pbar.close()

    else:
        # Fallback cách cũ qua thư viện datasets nếu không tìm thấy parquet
        logger.info(f"Loading dataset {HF_DATASET_NAME} - config: metadata")
        ds_meta = load_dataset(HF_DATASET_NAME, "metadata", split="data")
        
        logger.info(f"Loading dataset {HF_DATASET_NAME} - config: content")
        ds_content = load_dataset(HF_DATASET_NAME, "content", split="data")

        # Build metadata dict for O(1) lookup
        logger.info("Building metadata index by ID...")
        meta_dict = {}
        for item in tqdm(ds_meta, desc="Indexing metadata"):
            meta_dict[item["id"]] = item

        documents = []
        skipped = 0

        items = ds_content
        if max_items > 0:
            items = ds_content.select(range(min(max_items, len(ds_content))))

        for item in tqdm(items, desc="Tiền xử lý documents"):
            doc_id = item.get("id")
            content_raw = item.get("content_html") or item.get("content") or ""
            content_clean = clean_html(content_raw)

            if len(content_clean) < min_content_length:
                skipped += 1
                continue

            meta_item = meta_dict.get(doc_id, {})
            metadata = extract_metadata(meta_item)

            doc = {
                "doc_id": doc_id,
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
    Thống kê các danh mục (nganh, linh_vuc) duy nhất trong dataset.
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

