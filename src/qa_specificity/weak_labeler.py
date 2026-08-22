"""
Tầng 2: gán nhãn heuristic rule-based, độc lập hoàn toàn với LLM.

Ánh xạ trực tiếp từ `docs/specificity-guideline.md` §6.

Heuristic CHỈ xấp xỉ được Trục 1 (chỉ định điều khoản) và Trục 3 (chi tiết
tình huống). Trục 2 (số điều luật cần để trả lời) đòi hỏi hiểu nội dung luật
nên không rule-based được — đó chính là lý do phải có thêm tầng LLM judge.

Ngưỡng quyết định (guideline §6):
    >= 2 tín hiệu narrow  ⇒ narrow
    0 tín hiệu narrow     ⇒ broad
    đúng 1 tín hiệu       ⇒ ambiguous, "nhường quyết định cho LLM judge và
                            tầng provenance" — tức là ABSTAIN, không phải
                            phiếu chống. Xem `dataset_builder.filter_consensus`.
"""

import re

from config.qa_settings import NARROW_SIGNAL_THRESHOLD, SHORT_QUESTION_WORDS
from src.qa_specificity.schema import Specificity


# ══════════════════════════════════════════════════════════════════
# Trục 1 — mức chỉ định văn bản / điều khoản
# ══════════════════════════════════════════════════════════════════

# "Điều 35", "khoản 2", "điểm a)" / "điểm a khoản 1"
RE_ARTICLE = re.compile(r"\b(điều|khoản|điểm)\s+(\d+|[a-zđ]\b)", re.IGNORECASE)
RE_ARTICLE_NUM = re.compile(r"\bđiều\s+\d+", re.IGNORECASE)
RE_CLAUSE_NUM = re.compile(r"\bkhoản\s+\d+", re.IGNORECASE)

# Tên văn bản kèm năm, hoặc số hiệu dạng 15/2020/NĐ-CP
RE_DOC_NAME = re.compile(
    r"(?:bộ\s+luật|luật|nghị\s+định|thông\s+tư|nghị\s+quyết|quyết\s+định|pháp\s+lệnh)"
    r"[^.,;?\n]{0,60}?\b(?:năm\s+)?(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
RE_DOC_CODE = re.compile(
    r"\b\d+\s*/\s*(?:19|20)\d{2}\s*/\s*(?:NĐ-CP|TT-\w+|QĐ-\w+|NQ-\w+|QH\d*|TTLT-\w+)",
    re.IGNORECASE,
)
# Viết tắt phổ biến: BLDS, BLLĐ, BLHS, BLTTDS
RE_DOC_ABBR = re.compile(r"\b(BLDS|BLL[ĐD]|BLHS|BLTTDS|BLTTHS)\b")

# ══════════════════════════════════════════════════════════════════
# Trục 3 — mức chi tiết tình huống
# ══════════════════════════════════════════════════════════════════

# "Anh A", "Chị B", "Ông Nguyễn Văn A" — danh xưng + tên riêng viết hoa.
# Cố ý khớp trên text GỐC (còn hoa/thường) để không bắt nhầm "anh ấy", "chị em".
RE_ACTOR_PERSON = re.compile(
    r"\b(?:Anh|Chị|Ông|Bà|Em|Cháu|Cô|Chú|Bác)\s+"
    r"(?:[A-ZĐÀ-Ỹ][a-zà-ỹ]*\s+){0,2}"
    r"(?:[A-ZĐÀ-Ỹ]\b|[A-ZĐÀ-Ỹ][a-zà-ỹ]+)"
)
RE_ACTOR_ORG = re.compile(
    r"\b(?:[Cc]ông\s+ty|[Dd]oanh\s+nghiệp|[Xx]í\s+nghiệp|[Hh]ợp\s+tác\s+xã)\s+"
    r"(?:(?:cổ\s+phần|TNHH|trách\s+nhiệm\s+hữu\s+hạn)\s+)?"
    r"(?:[A-ZĐÀ-Ỹ]\b|[A-ZĐÀ-Ỹ][A-Za-zÀ-ỹ]+)"
)

# Con số ĐỊNH LƯỢNG gắn đơn vị. Cố ý KHÔNG bắt số trần ("Điều 35", "2019")
# vì số trần không nói lên tình huống có dữ kiện cụ thể.
RE_QUANTITY = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:ngày|tuần|tháng|năm\s+(?:làm\s+việc|kinh\s+nghiệm|công\s+tác)|giờ|tuổi|"
    r"triệu|tỷ|nghìn|đồng|%|phần\s+trăm|lần|người|m2|mét)\b",
    re.IGNORECASE,
)

# ══════════════════════════════════════════════════════════════════
# Tín hiệu broad
# ══════════════════════════════════════════════════════════════════

RE_ENUMERATION = re.compile(
    # "có những quyền gì", "có những trường hợp nào", "gồm những gì"
    r"((?:có|gồm|bao\s+gồm)\s+những\s+[^?.]{0,40}?\s*(?:nào|gì)\b|"
    r"những\s+[^?.]{0,40}?\s*(?:nào|gì)\s*\?|"
    r"\bbao\s+gồm\b|\bliệt\s+kê\b|"
    r"các\s+(?:loại|hình\s+thức|phương\s+thức|trường\s+hợp)\s+[^?.]{0,30}?\s*(?:nào|gì)\b)",
    re.IGNORECASE,
)
RE_DEFINITION = re.compile(
    r"(\blà\s+gì\s*\?|\bthế\s+nào\s+là\b|\bđược\s+hiểu\s+(?:là|như\s+thế\s+nào)\b|"
    r"\bkhái\s+niệm\b|\bđịnh\s+nghĩa\b)",
    re.IGNORECASE,
)
# So sánh / phân tích ưu nhược — luôn cần tổng hợp nhiều chế định
RE_COMPARISON = re.compile(
    r"(so\s+sánh|khác\s+(?:nhau|biệt)\s+(?:như\s+thế\s+nào|ra\s+sao|gì)|"
    r"ưu\s+(?:và\s+)?nhược\s+điểm|phân\s+biệt)",
    re.IGNORECASE,
)

# ══════════════════════════════════════════════════════════════════
# Ngoại lệ phủ quyết — guideline §4
# ══════════════════════════════════════════════════════════════════

# Cụm nối báo hiệu vấn đề pháp lý thứ hai độc lập
RE_SECOND_ISSUE = re.compile(
    r"(và\s+(?:trong\s+)?trường\s+hợp\s+(?:đó|này)|"
    r"đồng\s+thời\s+.{0,40}?(?:thủ\s+tục|quy\s+trình|thế\s+nào|ra\s+sao)|"
    r"ngoài\s+ra\s+.{0,40}?(?:thế\s+nào|ra\s+sao|gì)|"
    r"và\s+.{0,30}?thủ\s+tục\s+.{0,30}?(?:thế\s+nào|ra\s+sao|như\s+thế\s+nào))",
    re.IGNORECASE,
)

# Từ để hỏi — dùng đếm số vấn đề độc lập
RE_INTERROGATIVE = re.compile(
    r"(thế\s+nào|như\s+thế\s+nào|ra\s+sao|bao\s+nhiêu|khi\s+nào|ở\s+đâu|"
    r"\bgì\b|\bnào\b|có\s+được\s+không|có\s+hợp\s+pháp\s+không|có\s+căn\s+cứ)",
    re.IGNORECASE,
)


def _count_legal_issues(question: str) -> int:
    """
    Đếm (xấp xỉ) số vấn đề pháp lý độc lập trong câu hỏi.

    Dùng cho ngoại lệ phủ quyết "từ 2 vấn đề độc lập trở lên ⇒ luôn broad".
    Cố ý bảo thủ: chỉ tính là 2 khi có DẤU HIỆU NỐI rõ ràng, hoặc có từ 2 dấu
    hỏi trở lên. Đếm từ để hỏi đơn thuần sẽ dương tính giả rất nhiều vì một câu
    tiếng Việt bình thường có thể chứa cả "nào" lẫn "thế nào".
    """
    if question.count("?") >= 2:
        return 2
    if RE_SECOND_ISSUE.search(question):
        return 2
    return 1


def score_axis_1(question: str) -> dict:
    """Trục 1 — chỉ định văn bản/điều khoản. Trả về các tín hiệu narrow đã bắt được."""
    signals = {}
    if RE_ARTICLE.search(question):
        signals["article_reference"] = True
    if RE_DOC_NAME.search(question) or RE_DOC_CODE.search(question) or RE_DOC_ABBR.search(question):
        signals["document_name"] = True
    return signals


def score_axis_3(question: str) -> dict:
    """Trục 3 — chi tiết tình huống. Chấm trên text GỐC để giữ thông tin viết hoa."""
    signals = {}
    if RE_ACTOR_PERSON.search(question) or RE_ACTOR_ORG.search(question):
        signals["named_actor"] = True
    if RE_QUANTITY.search(question):
        signals["quantity_with_unit"] = True
    return signals


def score_broad_signals(question: str, has_narrow_signal: bool) -> dict:
    """Các tín hiệu nghiêng broad (trục 2 + trục 3)."""
    signals = {}
    if RE_ENUMERATION.search(question):
        signals["enumeration"] = True
    if RE_DEFINITION.search(question):
        signals["definition"] = True
    if RE_COMPARISON.search(question):
        signals["comparison"] = True

    # Tín hiệu PHỤ, chỉ dùng khi không còn tín hiệu nào khác.
    # Độ dài không tương quan ổn định với độ cụ thể: câu narrow có tình huống
    # thường rất dài, câu narrow trích điều luật lại rất ngắn (guideline §6).
    if not has_narrow_signal and len(question.split()) < SHORT_QUESTION_WORDS:
        signals["short_and_unspecific"] = True

    return signals


def heuristic_label(question: str) -> tuple[Specificity, dict]:
    """
    Gán nhãn heuristic cho một câu hỏi.

    Returns:
        (nhãn, chi tiết tín hiệu). Phần chi tiết được lưu vào
        `QAItem.heuristic_signals` để về sau còn audit được vì sao ra nhãn đó
        — không có nó thì mọi tranh cãi về nhãn đều không kiểm chứng được.
    """
    question = (question or "").strip()

    axis1 = score_axis_1(question)
    axis3 = score_axis_3(question)
    narrow_signals = {**axis1, **axis3}
    narrow_count = len(narrow_signals)

    broad_signals = score_broad_signals(question, has_narrow_signal=narrow_count > 0)

    detail = {
        "narrow_signals": sorted(narrow_signals.keys()),
        "broad_signals": sorted(broad_signals.keys()),
        "narrow_count": narrow_count,
        "broad_count": len(broad_signals),
        "n_legal_issues": _count_legal_issues(question),
        "n_words": len(question.split()),
        "override": None,
    }

    # ── Ngoại lệ phủ quyết (guideline §4) — xét TRƯỚC ngưỡng đếm ──

    # (1) Nêu đích danh CẢ điều VÀ khoản ⇒ luôn narrow.
    # Lý do: khi người dùng đã chỉ đích danh điều khoản, chiến lược truy xuất
    # đúng luôn là truy xuất chính xác, bất kể câu có tình huống hay không.
    if RE_ARTICLE_NUM.search(question) and RE_CLAUSE_NUM.search(question):
        detail["override"] = "explicit_article_and_clause"
        return Specificity.NARROW, detail

    # (2) Từ 2 vấn đề pháp lý độc lập trở lên ⇒ luôn broad.
    if detail["n_legal_issues"] >= 2:
        detail["override"] = "multiple_legal_issues"
        return Specificity.BROAD, detail

    # ── Ngưỡng đếm tín hiệu (guideline §6) ───────────────────────
    if narrow_count >= NARROW_SIGNAL_THRESHOLD:
        return Specificity.NARROW, detail
    if narrow_count == 0:
        return Specificity.BROAD, detail

    # Đúng 1 tín hiệu narrow: heuristic không đủ căn cứ để quyết
    # ⇒ ABSTAIN, nhường cho LLM judge và tầng provenance.
    return Specificity.AMBIGUOUS, detail


def label_items(items: list) -> list:
    """Gán `heuristic_label` + `heuristic_signals` tại chỗ cho danh sách QAItem."""
    for item in items:
        label, detail = heuristic_label(item.question)
        item.heuristic_label = label
        item.heuristic_signals = detail
    return items
