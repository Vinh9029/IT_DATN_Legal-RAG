"""
Chuẩn hoá số hiệu, loại văn bản và tên gọi văn bản để so khớp trích dẫn.

Dùng chung cho script dựng chỉ mục (offline) và verifier (online) — hai phía
phải chuẩn hoá giống hệt nhau thì tra cứu mới khớp.
"""

import re
import unicodedata

# Metadata HF có 14 số hiệu chứa chữ Cyrillic trông giống chữ Latin
# (vd "151/2025/TT-BTС" với С là U+0421) — model sẽ viết bằng chữ Latin.
_CONFUSABLES = str.maketrans({
    "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K", "М": "M",
    "О": "O", "Р": "P", "Т": "T", "Х": "X", "У": "Y", "І": "I",
    "а": "a", "в": "b", "с": "c", "е": "e", "н": "h", "к": "k", "м": "m",
    "о": "o", "р": "p", "т": "t", "х": "x", "у": "y", "і": "i",
})

_EMPTY_SO_HIEU = {"", "KHÔNG SỐ", "KHONG SO", "NONE", "NULL"}
_DASHED_RE = re.compile(r"^(\d+)-(\d{4})-(.+)$")
_LEADING_NUM_RE = re.compile(r"^0+(\d)")


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def normalize_so_hieu(raw: str) -> str:
    """
    Khoá so khớp số hiệu: "91-2015-QH13", "91/2015/qh13", "01/2019/NĐ-CP",
    "1/2019/ND-CP" → cùng một khoá. Trả về "" nếu không có số hiệu.
    """
    s = nfc(raw).translate(_CONFUSABLES).strip().upper()
    if s in _EMPTY_SO_HIEU:
        return ""
    s = re.sub(r"\s+", "", s)
    s = s.replace("Đ", "D").replace("–", "-").replace("—", "-")
    m = _DASHED_RE.match(s)
    if m:
        s = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    s = _LEADING_NUM_RE.sub(r"\1", s)
    return s.rstrip(".,;:)")


# Đặt dấu kiểu cũ → kiểu mới ("toà" → "tòa", "thuỷ" → "thủy"): corpus và model
# dùng lẫn cả hai, không thống nhất thì "Luật Tổ chức Toà án" không khớp tên gọi.
_TONE_FIX = {
    "oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
    "oè": "òe", "oé": "óe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
    "uỳ": "ùy", "uý": "úy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
}
_TONE_RE = re.compile("(?:" + "|".join(_TONE_FIX) + r")(?!\w)")   # "toàn" giữ nguyên


def normalize_text(text: str) -> str:
    """Chữ thường, NFC, gộp khoảng trắng — dùng cho tên gọi văn bản."""
    s = nfc(text).translate(_CONFUSABLES).lower()
    s = _TONE_RE.sub(lambda m: _TONE_FIX[m.group(0)], s)
    s = s.replace("&", " và ")
    s = re.sub(r"[\"“”‘’'`]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .,;:")


# Loại văn bản → dạng chuẩn. Model viết "Nghị định", "NĐ", "Thông tư liên tịch"...
LOAI_CANON = {
    "bộ luật": "Bộ luật",
    "luật": "Luật",
    "hiến pháp": "Hiến pháp",
    "pháp lệnh": "Pháp lệnh",
    "nghị định": "Nghị định",
    "nđ": "Nghị định",
    "nghị quyết": "Nghị quyết",
    "nq": "Nghị quyết",
    "nghị quyết liên tịch": "Nghị quyết liên tịch",
    "thông tư liên tịch": "Thông tư liên tịch",
    "ttlt": "Thông tư liên tịch",
    "thông tư": "Thông tư",
    "tt": "Thông tư",
    "quyết định": "Quyết định",
    "qđ": "Quyết định",
    "chỉ thị": "Chỉ thị",
    "lệnh": "Lệnh",
    "sắc lệnh": "Sắc lệnh",
    "văn bản hợp nhất": "Văn bản hợp nhất",
}

# Loại văn bản không phải bản gốc — không dùng làm đích của trích dẫn trừ khi
# không còn ứng viên nào khác (bản dịch còn ghi sai trạng thái hiệu lực).
NON_ORIGINAL_LOAI = {"Bản dịch văn bản", "Văn bản hệ thống hóa"}


def canon_loai(raw: str) -> str:
    return LOAI_CANON.get(normalize_text(raw), (raw or "").strip())


# Viết tắt thường gặp trong câu trả lời → tên đầy đủ (đã normalize_text)
ABBREVIATIONS = {
    "blds": "bộ luật dân sự",
    "bộ luật ds": "bộ luật dân sự",
    "blhs": "bộ luật hình sự",
    "bltths": "bộ luật tố tụng hình sự",
    "blttds": "bộ luật tố tụng dân sự",
    "bltds": "bộ luật tố tụng dân sự",
    "blld": "bộ luật lao động",
    "bllđ": "bộ luật lao động",
    "bộ luật lđ": "bộ luật lao động",
    "luật hn và gđ": "luật hôn nhân và gia đình",
    "luật hnvgđ": "luật hôn nhân và gia đình",
    "luật hngđ": "luật hôn nhân và gia đình",
}


def expand_abbreviations(text_norm: str) -> str:
    """Thay viết tắt (đã normalize_text) bằng tên đầy đủ, chỉ ở ranh giới từ."""
    for short, full in ABBREVIATIONS.items():
        text_norm = re.sub(rf"(?<!\w){re.escape(short)}(?!\w)", full, text_norm)
    return text_norm


_TITLE_SO_RE = re.compile(r"\s+số\s+(?:không số|\S*\d\S*)", re.IGNORECASE)
_YEAR_IN_SO_HIEU = re.compile(r"/(\d{4})/")
_YEAR_IN_TITLE = re.compile(r"năm\s+(\d{4})")

# Title "Luật sư số 65/2006/QH11" thiếu chữ "Luật" đầu → tên gọi "luật sư" sẽ trùng
# danh từ chung (người luật sư) trong câu trả lời.
_NAME_FIX = {"luật sư": "luật luật sư"}

# Loại văn bản hay được gọi bằng tên thay vì số hiệu
NAMED_LOAI = {"Bộ luật", "Luật", "Pháp lệnh", "Hiến pháp"}


def aliases_for(title: str, loai: str, so_hieu: str, ngay_ban_hanh: str = "") -> set[str]:
    """
    Sinh các tên gọi của một văn bản: "bộ luật dân sự 2015", "bộ luật dân sự năm
    2015", "bộ luật dân sự". Chỉ cho Luật/Bộ luật/Pháp lệnh/Hiến pháp — Nghị định,
    Thông tư được trích bằng số hiệu.
    """
    loai = (loai or "").strip()
    if loai not in NAMED_LOAI:
        return set()
    t = normalize_text(title)
    if not t:
        return set()

    year = ""
    m = _YEAR_IN_SO_HIEU.search(so_hieu or "")
    if m:
        year = m.group(1)
    else:
        m = _YEAR_IN_TITLE.search(t)
        if m:
            year = m.group(1)
        elif ngay_ban_hanh and re.search(r"(\d{4})\s*$", ngay_ban_hanh):
            year = re.search(r"(\d{4})\s*$", ngay_ban_hanh).group(1)

    loai_norm = normalize_text(loai)
    if loai == "Hiến pháp":
        name = "hiến pháp"
    else:
        # "pháp lệnh số 18/2004/pl-ubtvqh11 thú y" → "pháp lệnh thú y"
        # "bộ luật dân sự số 91/2015/qh13" → "bộ luật dân sự"
        name = _TITLE_SO_RE.sub(" ", t)
        name = re.sub(r"\s+", " ", name).strip(" ,.")
        name = re.sub(r"\s*\(.*$", "", name)            # bỏ "(sửa đổi, bổ sung ...)"
        if not name.startswith(loai_norm):
            name = f"{loai_norm} {name}"                 # title "Hàng hải" → "bộ luật hàng hải"
        name = re.sub(rf"\s+năm\s+{year}$", "", name) if year else name
        name = _NAME_FIX.get(name, name)
    if not name or (name == loai_norm and loai != "Hiến pháp"):
        return set()

    out = {name}
    if year:
        out |= {f"{name} {year}", f"{name} năm {year}"}
    return out
