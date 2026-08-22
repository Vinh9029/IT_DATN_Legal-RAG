"""
Sinh cặp câu hỏi đối chứng (contrastive pair) broad/narrow từ một văn bản luật.

THIẾT KẾ CỐT LÕI: MỘT lần gọi LLM sinh ĐỒNG THỜI cả hai câu.

Nếu sinh broad và narrow bằng hai lần gọi độc lập, phân bố chủ đề của hai lớp
sẽ lệch nhau (broad nghiêng dân sự, narrow nghiêng lao động chẳng hạn).
Classifier khi đó học CHỦ ĐỀ thay vì học ĐỘ CỤ THỂ — shortcut learning: accuracy
cao giả tạo trên test set rồi sập trên dữ liệu thật.
Sinh cùng lúc từ cùng văn bản ⇒ biến duy nhất khác nhau là độ cụ thể.
"""

import re

from loguru import logger

from config.qa_prompts import build_pair_generator_messages
from config.qa_settings import GEN_MAX_TOKENS, GEN_TEMPERATURE, MAX_DOC_CHARS
from src.qa_specificity.schema import QAItem, Specificity
from src.utils import generate_item_id, truncate_text


# Marker chuẩn là "[BROAD]" / "[NARROW]", nhưng model 8B hay biến tấu:
# "**[BROAD]**", "### BROAD", "1. [BROAD]:", "BROAD -", "[ BROAD ]"...
# Regex dưới đây nuốt hết các biến thể đó thay vì so khớp chuỗi cứng.
_MARKER_RE = re.compile(
    r"^\s*(?:[#>*\-\d.)\s]*)"          # bullet / heading / số thứ tự đứng trước
    r"[\[\(\*_\s]*"                     # dấu mở: [ ( * _
    r"(BROAD|NARROW|RỘNG|HẸP)"          # tên nhánh
    r"[\]\)\*_\s]*"                     # dấu đóng
    r"\s*[:：\-–]?\s*"                  # dấu hai chấm / gạch ngang tuỳ chọn
    r"(.*)$",                           # phần còn lại trên cùng dòng (nếu model viết liền)
    re.IGNORECASE,
)

_BRANCH_TO_LABEL = {
    "broad": Specificity.BROAD,
    "rộng": Specificity.BROAD,
    "narrow": Specificity.NARROW,
    "hẹp": Specificity.NARROW,
}

# Rác model hay chèn: đánh số, bullet, in đậm, ngoặc kép bao ngoài
_LEADING_NOISE_RE = re.compile(r'^[\s\-*•>#\d.)\]"“”\'`]+')
_TRAILING_NOISE_RE = re.compile(r'[\s"“”\'`*`]+$')

MIN_QUESTION_LENGTH = 15


def _clean_question(text: str) -> str:
    """Gột rác định dạng quanh câu hỏi, giữ nguyên nội dung."""
    text = " ".join(text.split())
    text = _LEADING_NOISE_RE.sub("", text)
    text = _TRAILING_NOISE_RE.sub("", text)
    return text.strip()


def parse_pair_response(text: str) -> dict:
    """
    Parse output của LLM thành {"broad": str, "narrow": str}.

    Nhánh nào không parse được thì vắng mặt trong dict trả về — caller tự
    quyết định loại cả cặp. Không bao giờ raise: output méo mó là chuyện
    thường ngày với model 8B, và một cặp hỏng không được phép giết cả pipeline.

    Chịu được:
      - marker in đậm / có heading / có đánh số
      - câu hỏi viết liền ngay sau marker trên cùng dòng
      - câu hỏi trải trên nhiều dòng
      - lời dẫn thừa trước marker đầu tiên
      - model chỉ trả về một nhánh
    """
    result: dict[str, str] = {}
    if not text:
        return result

    current: str | None = None
    buffers: dict[str, list[str]] = {}

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        match = _MARKER_RE.match(line)
        if match:
            branch = _BRANCH_TO_LABEL[match.group(1).lower()]
            current = branch.value
            buffers.setdefault(current, [])
            inline = match.group(2).strip()
            if inline:
                buffers[current].append(inline)
            continue

        # Dòng trước marker đầu tiên là lời dẫn thừa → bỏ
        if current is None:
            continue
        buffers[current].append(line.strip())

    for branch, parts in buffers.items():
        question = _clean_question(" ".join(parts))
        if len(question) >= MIN_QUESTION_LENGTH:
            result[branch] = question

    return result


def build_pair_items(
    doc: dict,
    parsed: dict,
) -> list[QAItem]:
    """
    Dựng 2 QAItem cùng `pair_id` từ kết quả đã parse.

    Trả về list rỗng nếu thiếu một trong hai nhánh: một cặp khuyết vế mất
    toàn bộ giá trị đối chứng, giữ lại chỉ làm nhiễu phân bố nhãn.
    """
    if Specificity.BROAD.value not in parsed or Specificity.NARROW.value not in parsed:
        return []

    broad_q = parsed[Specificity.BROAD.value]
    narrow_q = parsed[Specificity.NARROW.value]

    # Model đôi khi sinh hai câu gần như y hệt nhau — cặp đó không đối chứng gì cả.
    if broad_q.strip().lower() == narrow_q.strip().lower():
        logger.debug("Cặp bị loại: câu broad và narrow trùng nhau")
        return []

    source_doc_id = doc["source_doc_id"]
    pair_id = "pair_" + generate_item_id(f"{source_doc_id}|{broad_q}|{narrow_q}")
    metadata = doc.get("metadata") or {}
    shared_meta = {
        "linh_vuc": metadata.get("linh_vuc", ""),
        "nganh": metadata.get("nganh", ""),
        "so_hieu": metadata.get("so_hieu", ""),
        "loai_van_ban": metadata.get("loai_van_ban", ""),
        "scope": doc.get("scope", ""),
    }

    items = []
    for label, question in (
        (Specificity.BROAD, broad_q),
        (Specificity.NARROW, narrow_q),
    ):
        items.append(
            QAItem(
                item_id="q_" + generate_item_id(f"{pair_id}|{label.value}|{question}"),
                pair_id=pair_id,
                source_doc_id=source_doc_id,
                question=question,
                specificity=label,  # tầng 1: provenance, CHƯA qua kiểm chứng
                metadata=dict(shared_meta),
            )
        )
    return items


def generate_pair(doc: dict, llm_client) -> list[QAItem]:
    """
    Gọi LLM một lần, trả về 2 QAItem (broad + narrow) hoặc list rỗng nếu hỏng.

    Args:
        doc: document đã qua `load_scoped_corpus()` (đã có `source_doc_id`).
        llm_client: `src.llm_client.LLMClient` trỏ tới LM Studio local.
    """
    content = (doc.get("content") or "")[:MAX_DOC_CHARS]
    metadata = doc.get("metadata") or {}

    messages = build_pair_generator_messages(
        content=content,
        linh_vuc=metadata.get("linh_vuc", ""),
        nganh=metadata.get("nganh", ""),
        so_hieu=metadata.get("so_hieu", ""),
    )

    try:
        response = llm_client.chat(
            messages=messages,
            temperature=GEN_TEMPERATURE,
            max_tokens=GEN_MAX_TOKENS,
        )
    except Exception as e:
        logger.warning(f"Lỗi gọi LLM cho doc {doc.get('source_doc_id')}: {e}")
        return []

    parsed = parse_pair_response(response)
    items = build_pair_items(doc, parsed)

    if not items:
        logger.debug(
            f"Không parse được cặp từ doc {doc.get('source_doc_id')} | "
            f"raw={truncate_text(response, 300)}"
        )

    return items
