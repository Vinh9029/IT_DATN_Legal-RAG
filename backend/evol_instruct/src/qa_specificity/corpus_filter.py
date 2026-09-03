"""
Lọc corpus về đúng phạm vi LUẬT DÂN SỰ và gán định danh ổn định.

─── Phạm vi: vì sao là dân sự theo chiều sâu ───

Bản trước lọc "lao động + dân sự" theo chiều rộng. Đo trên dữ liệu thật thì ra
2.188 doc lao động / 145 doc dân sự — lệch 94/6, và phần Limitations của báo
cáo phải đi thanh minh cho con số đó. Nhóm đã chốt đổi sang đi theo CHIỀU SÂU
một lĩnh vực: chủ đề hẹp lại thì biến nhiễu giảm, nên thứ classifier học được
chắc chắn là ĐỘ CỤ THỂ chứ không phải chủ đề.

─── Vì sao module này không tự đọc file ───

Việc ĐỌC nguồn (mọi định dạng) đã tách sang `corpus_loader`. Ở đây chỉ còn
việc LỌC trên doc dict đã chuẩn hoá. Nhờ vậy đổi nguồn dữ liệu không phải sửa
logic phạm vi, và đổi phạm vi không phải sửa code đọc file.

─── Vì sao đường HuggingFace KHÔNG dùng `data_loader.load_and_preprocess()` ───

Spec ban đầu dự kiến module này chỉ là wrapper mỏng quanh hàm đó. Nhưng đối
chiếu với dataset thật thì giả định nền của thiết kế đó sai:

  - Dataset có 5 config. Config `content` mà `config/settings.py` đang trỏ tới
    CHỈ có 2 cột: `id` và `content_html`. Không có `nganh`, `linh_vuc`,
    `loai_van_ban` nào cả.
  - `extract_metadata()` đọc `item.get("nganh")` v.v. trên config đó nên trả về
    chuỗi rỗng cho TOÀN BỘ 154.380 document. Đã kiểm chứng: lọc theo metadata
    qua đường đó cho ra đúng 0 document.
  - Metadata thật nằm ở config `metadata`, join với content qua trường `id`.
"""

import json

from loguru import logger
from tqdm import tqdm

from config.qa_settings import (
    CIVIL_ANCHOR_TITLES,
    CIVIL_METADATA_KEYWORDS,
    CORPUS_SOURCE,
    HF_CONFIG_CONTENT,
    HF_CONFIG_METADATA,
    HF_DATASET_NAME,
    INCLUDED_DOC_TYPES,
    MIN_CONTENT_LENGTH,
    SCOPE_ANTI_KEYWORDS,
    SCOPE_AUTO_MIN_RATIO,
    SCOPE_FILTER_MODE,
    SCOPED_CORPUS_CACHE,
    SPLIT_BY_ARTICLE,
)
from evol_instruct.src.qa_specificity.corpus_loader import (
    expand_documents_by_article,
    has_local_corpus,
    load_local_corpus,
)
from evol_instruct.src.utils import generate_item_id


def _normalize(text) -> str:
    """Chuẩn hoá về lowercase, gộp khoảng trắng. Nhiều nguồn dùng chuỗi 'None' cho ô trống."""
    text = ("" if text is None else str(text)).strip()
    if text.lower() in ("none", "nan", "null"):
        return ""
    return " ".join(text.lower().split())


def _metadata_of(doc: dict) -> dict:
    """
    Lấy phần metadata, chấp nhận cả doc dict lẫn dict metadata phẳng.

    Cần cả hai vì đường HuggingFace lọc TRƯỚC khi join content (lúc đó chỉ có
    metadata phẳng trong tay), còn đường cục bộ lọc trên doc dict đầy đủ.
    """
    metadata = doc.get("metadata")
    return metadata if isinstance(metadata, dict) else doc


def derive_doc_id(doc: dict) -> str:
    """
    Sinh `source_doc_id` ổn định cho một document.

    `source_doc_id` là bắt buộc để chống data leakage lúc group split, nên phải
    đảm bảo cùng một văn bản luôn cho cùng một id.

    Thứ tự ưu tiên:
      1. `id` gốc của nguồn — định danh thật, không phụ thuộc nội dung.
      2. `so_ky_hieu` / `so_hieu` — số hiệu văn bản.
      3. Băm `content[:500]` — chốt chặn cuối.

    Cách 1 giải quyết trọn vẹn vấn đề mà spec §2.1 phải chấp nhận đánh đổi: id
    không đổi kể cả khi `clean_html` được chỉnh sửa.
    """
    raw_id = str(doc.get("id") or "").strip()
    if raw_id:
        return f"doc_{raw_id}"

    metadata = _metadata_of(doc)
    so_ky_hieu = _normalize(metadata.get("so_ky_hieu") or metadata.get("so_hieu"))
    if so_ky_hieu:
        return "doc_" + generate_item_id(so_ky_hieu)

    return "doc_" + generate_item_id((doc.get("content") or "")[:500])


# ══════════════════════════════════════════════════════════════════
# Nhận diện phạm vi dân sự
# ══════════════════════════════════════════════════════════════════

def _strip_anti(haystack: str) -> str:
    """Bỏ các cụm khớp nhầm trước khi so khớp phạm vi."""
    for anti in SCOPE_ANTI_KEYWORDS:
        haystack = haystack.replace(anti, " ")
    return haystack


def scope_of(doc: dict) -> str:
    """
    Trả nhánh con dân sự của một document, hoặc "" nếu ngoài phạm vi.

    Hai đường nhận diện, khớp đường nào cũng tính:
      - TIÊU ĐỀ khớp `CIVIL_ANCHOR_TITLES` — đường chính. Tiêu đề thì nguồn
        nào cũng có, còn `nganh`/`linh_vuc` thì nguồn mới có thể không có.
        Trên dataset HF cũ, lọc theo metadata chỉ ra 502 doc, thêm tiêu đề vào
        thì lên 522 và bắt được đúng bộ khung (BLDS, BLTTDS, Luật HNGĐ, Đất
        đai, Nhà ở, SHTT, Công chứng, THADS...) mà metadata bỏ sót vì 66% bản
        ghi có `linh_vuc = "Chưa phân loại"`.
      - `nganh` + `linh_vuc` khớp `CIVIL_METADATA_KEYWORDS` — đường bổ sung.

    Nhánh con CHỈ để thống kê cân bằng, không phải nhãn của bài toán.
    """
    metadata = _metadata_of(doc)
    title = _strip_anti(_normalize(metadata.get("title") or doc.get("title")))
    meta_hay = _strip_anti(
        f"{_normalize(metadata.get('nganh'))} {_normalize(metadata.get('linh_vuc'))}"
    )

    if title:
        for scope, anchors in CIVIL_ANCHOR_TITLES.items():
            if any(anchor in title for anchor in anchors):
                return scope

    if meta_hay.strip():
        for scope, keywords in CIVIL_METADATA_KEYWORDS.items():
            if any(keyword in meta_hay for keyword in keywords):
                return scope

    return ""


def is_normative_doc(doc: dict) -> bool:
    """
    Có phải văn bản QUY PHẠM không?

    Trả True khi nguồn không khai `loai_van_ban`: loại sạch corpus chỉ vì thiếu
    một cột metadata là kiểu hỏng tệ nhất — không có thông báo lỗi nào cả, chỉ
    có "0 document" ở cuối.
    """
    loai = _normalize(_metadata_of(doc).get("loai_van_ban"))
    if not loai:
        return True
    return loai in INCLUDED_DOC_TYPES


def is_in_scope(doc: dict) -> bool:
    """Document vừa thuộc phạm vi dân sự vừa là văn bản quy phạm?"""
    return is_normative_doc(doc) and bool(scope_of(doc))


def apply_scope_filter(documents: list[dict]) -> list[dict]:
    """
    Áp bộ lọc phạm vi theo `SCOPE_FILTER_MODE`, đồng thời gán trường `scope`.

    Chế độ "auto" (mặc định) có một lối thoát cố ý: nếu tỉ lệ lọt quá thấp thì
    giữ nguyên cả corpus thay vì trả về gần như rỗng. Lý do là hai tình huống
    khác hẳn nhau nhưng cho ra cùng một triệu chứng — (a) nguồn đã được chuẩn
    bị sẵn toàn văn bản dân sự nên chẳng cần lọc, (b) nguồn dùng cách đặt tên
    mà từ khoá của ta không khớp. Cả hai đều KHÔNG phải lý do để vứt dữ liệu;
    im lặng trả về 3 document mới là cái làm mất hàng giờ đi truy nhầm chỗ.
    """
    for doc in documents:
        doc["scope"] = scope_of(doc)

    if SCOPE_FILTER_MODE == "off":
        logger.info(f"QA_SCOPE_FILTER_MODE=off → giữ nguyên {len(documents)} document")
        return documents

    kept = [d for d in documents if is_normative_doc(d) and d["scope"]]
    ratio = len(kept) / len(documents) if documents else 0.0

    if SCOPE_FILTER_MODE == "auto" and ratio < SCOPE_AUTO_MIN_RATIO:
        logger.warning(
            f"Chỉ {len(kept)}/{len(documents)} document ({ratio:.1%}) khớp phạm vi dân sự, "
            f"dưới ngưỡng {SCOPE_AUTO_MIN_RATIO:.0%} → GIỮ NGUYÊN cả corpus.\n"
            f"   Hai khả năng: (a) nguồn đã thuần dân sự sẵn — không sao, chạy tiếp; "
            f"(b) từ khoá trong CIVIL_ANCHOR_TITLES không khớp cách đặt tên của nguồn "
            f"— soát lại vài tiêu đề rồi bổ sung từ khoá.\n"
            f"   Muốn lọc thẳng tay bất kể tỉ lệ: QA_SCOPE_FILTER_MODE=strict"
        )
        return documents

    logger.info(f"Lọc phạm vi dân sự: {len(kept)}/{len(documents)} document ({ratio:.1%})")
    return kept


# ══════════════════════════════════════════════════════════════════
# Đường dự phòng: HuggingFace dataset
# ══════════════════════════════════════════════════════════════════

def _load_scoped_metadata_hf() -> dict[str, dict]:
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
        # Lọc ở đây (trên metadata rẻ) thay vì sau khi join: đỡ phải clean_html
        # cho 170.824 document. Chế độ "auto"/"off" không áp được ở bước này
        # nên dùng luật chặt — đường HF là nguồn CŨ đã biết rõ, không phải
        # nguồn lạ cần nới tay.
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

    logger.info(f"  {len(scoped)} document lọt phạm vi dân sự (văn bản quy phạm)")
    return scoped


def _load_corpus_hf(threshold: int) -> list[dict]:
    """Nạp corpus từ HuggingFace: lọc trên metadata trước, rồi mới clean_html."""
    scoped_metadata = _load_scoped_metadata_hf()
    if not scoped_metadata:
        logger.error(
            "Không có document nào lọt phạm vi. Kiểm tra CIVIL_ANCHOR_TITLES và "
            "INCLUDED_DOC_TYPES trong config/qa_settings.py so với giá trị thực tế "
            "của cột title/nganh/linh_vuc/loai_van_ban trong config 'metadata'."
        )
        return []

    from datasets import load_dataset
    from evol_instruct.src.data_loader import clean_html

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
            "source_file": f"hf:{HF_DATASET_NAME}",
            "scope": metadata.get("scope", ""),
        })

    logger.info(
        f"Corpus HuggingFace trong phạm vi: {len(documents)} documents "
        f"({skipped_short} bị loại vì content < {threshold} ký tự)"
    )
    return documents


# ══════════════════════════════════════════════════════════════════
# Điểm vào
# ══════════════════════════════════════════════════════════════════

def load_scoped_corpus(
    max_items: int = 0,
    min_content_length: int | None = None,
    cache: bool = True,
    source=None,
    rebuild: bool = False,
) -> list[dict]:
    """
    Load corpus đã lọc phạm vi dân sự, kèm `source_doc_id` và `scope`.

    Nguồn được chọn theo thứ tự: `source` (nếu truyền) → thư mục cục bộ
    `CORPUS_SOURCE` → dataset HuggingFace (dự phòng).

    Args:
        max_items: số document tối đa trả về (0 = tất cả).
        min_content_length: ngưỡng độ dài content; None → MIN_CONTENT_LENGTH.
        cache: đọc/ghi `data/qa_pairs/raw/scoped_corpus.jsonl`.
        source: ghi đè thư mục/file nguồn cho lần gọi này.
        rebuild: bỏ qua cache và nạp lại từ nguồn.

    Lưu ý về `max_items`: luôn lọc phạm vi TRƯỚC rồi mới cắt. Cắt trước khi lọc
    (như `load_and_preprocess(max_items=N)` làm) sẽ lấy N document đầu nguồn,
    gần như không có văn bản dân sự nào trong đó.
    """
    threshold = MIN_CONTENT_LENGTH if min_content_length is None else min_content_length

    # ── Cache ─────────────────────────────────────────────────────
    # CÁI BẪY: cache được đọc trước mọi thứ, nên đổi phạm vi / đổi nguồn / bật
    # cắt theo Điều mà quên xoá cache thì corpus cũ vẫn về và mọi thay đổi đều
    # như không có tác dụng. Dùng `rebuild=True` (script: --rebuild-corpus).
    if cache and not rebuild and SCOPED_CORPUS_CACHE.exists():
        logger.info(f"Đọc scoped corpus từ CACHE: {SCOPED_CORPUS_CACHE}")
        logger.info("  (đổi nguồn hoặc đổi phạm vi thì phải chạy lại với --rebuild-corpus)")
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

    # ── Nạp thô ───────────────────────────────────────────────────
    chosen = source if source is not None else CORPUS_SOURCE
    if has_local_corpus(chosen):
        documents = load_local_corpus(chosen, min_content_length=threshold)
    else:
        logger.warning(
            f"Không có file corpus ở {chosen} → dùng dataset HuggingFace "
            f"({HF_DATASET_NAME}) làm nguồn dự phòng."
        )
        documents = _load_corpus_hf(threshold)

    if not documents:
        return []

    # ── Lọc phạm vi ───────────────────────────────────────────────
    documents = apply_scope_filter(documents)
    if not documents:
        return []

    # ── Cắt theo Điều (tuỳ chọn) ──────────────────────────────────
    if SPLIT_BY_ARTICLE:
        documents = expand_documents_by_article(documents)

    from collections import Counter
    logger.info(f"Phân bố nhánh: {dict(Counter(d.get('scope') or 'unknown' for d in documents))}")

    # ── Cache ─────────────────────────────────────────────────────
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
