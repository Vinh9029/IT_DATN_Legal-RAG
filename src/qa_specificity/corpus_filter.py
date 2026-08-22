"""
Lọc corpus về đúng phạm vi Phần 3 (lao động + dân sự) và gán định danh ổn định.

─── Vì sao KHÔNG dùng `data_loader.load_and_preprocess()` của Vinh ───

Spec ban đầu dự kiến module này chỉ là wrapper mỏng quanh hàm đó. Nhưng đối
chiếu với dataset thật thì giả định nền của thiết kế đó sai:

  - Dataset có 5 config. Config `content` mà `config/settings.py` đang trỏ tới
    CHỈ có 2 cột: `id` và `content_html`. Không có `nganh`, `linh_vuc`,
    `loai_van_ban` nào cả.
  - `extract_metadata()` đọc `item.get("nganh")` v.v. trên config đó nên trả về
    chuỗi rỗng cho TOÀN BỘ 154.380 document. Đã kiểm chứng: lọc theo metadata
    qua đường đó cho ra đúng 0 document.
  - Metadata thật nằm ở config `metadata`, join với content qua trường `id`.

Nên module này tự load và join hai config. Vẫn giữ đúng nguyên tắc "chỉ import,
không edit" — `clean_html` dùng lại nguyên hàm của Vinh.

Đổi lại còn được hai thứ:
  1. `source_doc_id` lấy thẳng `id` của dataset — định danh thật, ổn định tuyệt
     đối, thay cho việc băm `so_hieu`/`content` như spec §2.1 phải chấp nhận.
  2. Lọc metadata TRƯỚC rồi mới `clean_html` cho ~2.400 doc trong phạm vi, thay
     vì clean cả 170.824 doc rồi mới lọc (~20 phút xuống còn dưới 1 phút).
"""

import json

from loguru import logger
from tqdm import tqdm

from config.qa_settings import (
    HF_CONFIG_CONTENT,
    HF_CONFIG_METADATA,
    HF_DATASET_NAME,
    INCLUDED_DOC_TYPES,
    MIN_CONTENT_LENGTH,
    SCOPE_ANTI_KEYWORDS,
    SCOPE_KEYWORDS,
    SCOPED_CORPUS_CACHE,
)
from src.data_loader import clean_html
from src.utils import generate_item_id


def _normalize(text) -> str:
    """Chuẩn hoá về lowercase, gộp khoảng trắng. Dataset dùng chuỗi 'None' cho ô trống."""
    text = ("" if text is None else str(text)).strip()
    if text.lower() == "none":
        return ""
    return " ".join(text.lower().split())


def derive_doc_id(doc: dict) -> str:
    """
    Sinh `source_doc_id` ổn định cho một document.

    `source_doc_id` là bắt buộc để chống data leakage lúc group split, nên phải
    đảm bảo cùng một văn bản luôn cho cùng một id.

    Thứ tự ưu tiên:
      1. `id` gốc của dataset — định danh thật, không phụ thuộc nội dung.
      2. `so_ky_hieu` (tên trường THẬT trong config metadata; lưu ý
         `extract_metadata()` của Vinh đọc `so_hieu`, trường đó không tồn tại).
      3. Băm `content[:500]` — chốt chặn cuối.

    Cách 1 giải quyết trọn vẹn vấn đề mà spec §2.1 phải chấp nhận đánh đổi: id
    không đổi kể cả khi `clean_html` được chỉnh sửa.
    """
    raw_id = str(doc.get("id") or "").strip()
    if raw_id:
        return f"doc_{raw_id}"

    metadata = doc.get("metadata") or {}
    so_ky_hieu = _normalize(metadata.get("so_ky_hieu") or metadata.get("so_hieu"))
    if so_ky_hieu:
        return "doc_" + generate_item_id(so_ky_hieu)

    return "doc_" + generate_item_id((doc.get("content") or "")[:500])


def scope_of(metadata: dict) -> str:
    """Trả về nhánh phạm vi ('lao_dong' / 'dan_su' / '') để thống kê cân bằng."""
    haystack = f"{_normalize(metadata.get('nganh'))} {_normalize(metadata.get('linh_vuc'))}"
    if not haystack.strip():
        return ""
    for anti in SCOPE_ANTI_KEYWORDS:
        haystack = haystack.replace(anti, " ")
    for scope, keywords in SCOPE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return scope
    return ""


def is_in_scope(doc: dict) -> bool:
    """
    Document có thuộc phạm vi lao động/dân sự VÀ là văn bản quy phạm không?

    Chấp nhận cả dict dạng `{"metadata": {...}}` lẫn dict metadata phẳng, để
    dùng được ở cả hai phía của bước join.
    """
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else doc

    loai = _normalize(metadata.get("loai_van_ban"))
    if loai not in INCLUDED_DOC_TYPES:
        return False

    return bool(scope_of(metadata))


def _load_scoped_metadata() -> dict[str, dict]:
    """Đọc config `metadata`, trả về {id: metadata} cho các document trong phạm vi."""
    from datasets import load_dataset

    logger.info(f"Đọc metadata: {HF_DATASET_NAME} (config={HF_CONFIG_METADATA})")
    dataset = load_dataset(HF_DATASET_NAME, HF_CONFIG_METADATA)
    split = dataset[list(dataset.keys())[0]]
    logger.info(f"  {len(split)} bản ghi metadata")

    columns = ("id", "title", "so_ky_hieu", "loai_van_ban", "nganh", "linh_vuc",
               "co_quan_ban_hanh", "nguoi_ky", "ngay_ban_hanh", "ngay_co_hieu_luc",
               "tinh_trang_hieu_luc")
    available = [c for c in columns if c in split.column_names]
    table = {c: split[c] for c in available}

    scoped: dict[str, dict] = {}
    for i in range(len(split)):
        row = {c: table[c][i] for c in available}
        if not is_in_scope(row):
            continue
        doc_id = str(row.get("id") or "").strip()
        if not doc_id:
            continue
        clean = {k: ("" if v is None or str(v).strip().lower() == "none" else str(v).strip())
                 for k, v in row.items()}
        # Giữ cả tên `so_hieu` để tương thích với code đọc theo tên cũ
        clean["so_hieu"] = clean.get("so_ky_hieu", "")
        clean["scope"] = scope_of(row)
        scoped[doc_id] = clean

    logger.info(f"  {len(scoped)} document lọt phạm vi (lao động + dân sự, văn bản quy phạm)")
    return scoped


def load_scoped_corpus(
    max_items: int = 0,
    min_content_length: int | None = None,
    cache: bool = True,
) -> list[dict]:
    """
    Load corpus đã lọc phạm vi, kèm `source_doc_id` và `scope`.

    Args:
        max_items: số document trong phạm vi tối đa trả về (0 = tất cả).
        min_content_length: ngưỡng độ dài content; None → MIN_CONTENT_LENGTH.
        cache: đọc/ghi `data/qa_pairs/raw/scoped_corpus.jsonl`.

    Returns:
        list dict: {id, content, metadata, content_length, source_doc_id, scope}

    Lưu ý về `max_items`: luôn lọc phạm vi TRƯỚC rồi mới cắt. Cắt trước khi lọc
    (như `load_and_preprocess(max_items=N)` làm) sẽ lấy N document đầu dataset,
    gần như không có văn bản lao động/dân sự nào trong đó.
    """
    threshold = MIN_CONTENT_LENGTH if min_content_length is None else min_content_length

    # ── Cache ─────────────────────────────────────────────────────
    if cache and SCOPED_CORPUS_CACHE.exists():
        logger.info(f"Đọc scoped corpus từ cache: {SCOPED_CORPUS_CACHE}")
        documents = []
        with open(SCOPED_CORPUS_CACHE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    documents.append(json.loads(line))
        logger.info(f"  {len(documents)} documents từ cache")
        if max_items > 0:
            documents = documents[:max_items]
        return documents

    # ── Bước 1: lọc trên metadata (rẻ) ────────────────────────────
    scoped_metadata = _load_scoped_metadata()
    if not scoped_metadata:
        logger.error(
            "Không có document nào lọt phạm vi. Kiểm tra SCOPE_KEYWORDS và "
            "INCLUDED_DOC_TYPES trong config/qa_settings.py so với giá trị thực tế "
            "của cột nganh/linh_vuc/loai_van_ban trong config 'metadata'."
        )
        return []

    # ── Bước 2: chỉ clean_html cho phần trong phạm vi (đắt) ───────
    from datasets import load_dataset

    logger.info(f"Đọc nội dung: {HF_DATASET_NAME} (config={HF_CONFIG_CONTENT})")
    content_ds = load_dataset(HF_DATASET_NAME, HF_CONFIG_CONTENT)
    content_split = content_ds[list(content_ds.keys())[0]]

    ids = content_split["id"]
    wanted_rows = [i for i, doc_id in enumerate(ids) if str(doc_id).strip() in scoped_metadata]
    logger.info(f"  {len(wanted_rows)} document khớp id giữa hai config")

    documents = []
    skipped_short = 0
    for row_index in tqdm(wanted_rows, desc="Làm sạch HTML (chỉ phần trong phạm vi)"):
        row = content_split[row_index]
        doc_id = str(row["id"]).strip()
        content = clean_html(row.get("content_html") or "")

        if len(content) < threshold:
            skipped_short += 1
            continue

        metadata = scoped_metadata[doc_id]
        documents.append({
            "id": doc_id,
            "content": content,
            "content_length": len(content),
            "metadata": metadata,
            "source_doc_id": f"doc_{doc_id}",
            "scope": metadata.get("scope", ""),
        })

    logger.info(
        f"Corpus trong phạm vi: {len(documents)} documents "
        f"({skipped_short} bị loại vì content < {threshold} ký tự)"
    )

    if cache and documents:
        SCOPED_CORPUS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(SCOPED_CORPUS_CACHE, "w", encoding="utf-8") as f:
            for doc in documents:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        logger.info(f"Đã cache → {SCOPED_CORPUS_CACHE}")

    if max_items > 0:
        documents = documents[:max_items]
        logger.info(f"Cắt còn {len(documents)} documents theo max_items={max_items}")

    return documents
