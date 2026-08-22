"""
Hợp đồng dữ liệu xuyên suốt QA Specificity Pipeline.

Mọi module trong `src/qa_specificity/` đọc/ghi đều đi qua `QAItem`.
`source_doc_id` và `pair_id` có mặt NGAY TỪ ĐẦU — thiếu chúng thì tới bước
split mới phát hiện là phải chạy lại toàn bộ pipeline (spec §7).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class Specificity(str, Enum):
    """
    Nhãn độ cụ thể của câu hỏi (guideline §2.2 — phương án A, nhãn nhị phân).

    AMBIGUOUS KHÔNG phải lớp thứ ba của bài toán phân loại. Nó là trạng thái
    "chưa quyết được", dùng ở hai chỗ:
      - heuristic chấm đúng 1 tín hiệu narrow → nhường quyết định cho tầng khác
      - judge thấy có trục không chấm được → câu vùng xám, loại khỏi dataset
    Dataset cuối cùng (`final_label`) chỉ chứa BROAD hoặc NARROW.

    Kế thừa `str` để `json.dumps` và so sánh với chuỗi hoạt động tự nhiên.
    """

    BROAD = "broad"
    NARROW = "narrow"
    AMBIGUOUS = "ambiguous"

    @classmethod
    def parse(cls, value) -> "Specificity | None":
        """Ép chuỗi bất kỳ về Specificity; trả None nếu không nhận diện được."""
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        text = str(value).strip().lower()
        for member in cls:
            if text == member.value:
                return member
        # Chấp nhận vài biến thể model hay trả về
        aliases = {
            "hẹp": cls.NARROW, "hep": cls.NARROW, "specific": cls.NARROW,
            "rộng": cls.BROAD, "rong": cls.BROAD, "general": cls.BROAD,
            "unknown": cls.AMBIGUOUS, "unclear": cls.AMBIGUOUS,
            "mơ hồ": cls.AMBIGUOUS, "mo ho": cls.AMBIGUOUS,
        }
        return aliases.get(text)

    @property
    def is_decided(self) -> bool:
        """True khi nhãn là một lớp thật (broad/narrow), không phải trạng thái chờ."""
        return self in (Specificity.BROAD, Specificity.NARROW)


@dataclass
class QAItem:
    """
    Một câu hỏi kèm toàn bộ vết gán nhãn của nó.

    Mỗi cặp đối chứng gồm 2 QAItem cùng `pair_id` và `source_doc_id`,
    khác nhau ở `specificity` (nhãn provenance).
    """

    # ── Định danh ────────────────────────────────────────────────
    item_id: str
    pair_id: str
    source_doc_id: str

    # ── Nội dung ─────────────────────────────────────────────────
    question: str

    # ── Tầng 1: provenance (câu sinh ở nhánh nào) ────────────────
    specificity: Specificity = Specificity.AMBIGUOUS

    # ── Tầng 2: heuristic rule-based ─────────────────────────────
    heuristic_label: Specificity | None = None
    heuristic_signals: dict = field(default_factory=dict)

    # ── Tầng 3: LLM judge ────────────────────────────────────────
    judge_label: Specificity | None = None
    judge_reason: str = ""
    judge_axes: dict = field(default_factory=dict)

    # ── Kết luận hợp nhất ────────────────────────────────────────
    final_label: Specificity | None = None
    consensus: bool | None = None
    reject_reason: str = ""

    # ── Ngữ cảnh ─────────────────────────────────────────────────
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize sang dict thuần JSON (Enum → str, None giữ nguyên)."""
        data = asdict(self)
        for key in ("specificity", "heuristic_label", "judge_label", "final_label"):
            value = data.get(key)
            if isinstance(value, Specificity):
                data[key] = value.value
            elif value is not None:
                data[key] = str(value)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "QAItem":
        """Dựng lại QAItem từ dict đã đọc từ JSONL. Bỏ qua field lạ."""
        return cls(
            item_id=data["item_id"],
            pair_id=data["pair_id"],
            source_doc_id=data["source_doc_id"],
            question=data["question"],
            specificity=Specificity.parse(data.get("specificity")) or Specificity.AMBIGUOUS,
            heuristic_label=Specificity.parse(data.get("heuristic_label")),
            heuristic_signals=data.get("heuristic_signals") or {},
            judge_label=Specificity.parse(data.get("judge_label")),
            judge_reason=data.get("judge_reason", "") or "",
            judge_axes=data.get("judge_axes") or {},
            final_label=Specificity.parse(data.get("final_label")),
            consensus=data.get("consensus"),
            reject_reason=data.get("reject_reason", "") or "",
            metadata=data.get("metadata") or {},
        )

    def blinded_dict(self) -> dict:
        """
        Bản rút gọn ĐÃ ẨN mọi nhãn máy, dùng cho vòng gán tay ở Bước 3.

        Nhìn thấy nhãn máy trước khi gán tay ⇒ anchoring bias ⇒ hệ số
        Cohen's kappa tính ra vô giá trị (guideline §7).
        """
        return {
            "item_id": self.item_id,
            "question": self.question,
            "manual_label": "",  # điền tay: broad | narrow | ambiguous
        }
