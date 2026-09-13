"""
Instruction Eliminator - Bộ lọc loại bỏ dữ liệu lỗi.

6 bộ lọc:
1. Prompt Leakage     2. Refusal
3. Semantic Similarity 4. IRAC Structure
5. Min Length          6. Legal Hallucination

Bổ sung: PoolDeduplicator (chống trùng lặp trên TOÀN BỘ pool đã accept, theo
đúng tinh thần Instruction Eliminator của WizardLM) và `eliminate_evolved()`
để lọc sớm trước khi tốn một lượt gọi LLM sinh câu trả lời IRAC.
"""

import re
from loguru import logger
from sklearn.feature_extraction.text import TfidfVectorizer, HashingVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config.settings import SIMILARITY_THRESHOLD

# Evolved instruction ngắn hơn mức này chắc chắn là rác (model trả rỗng, chỉ trả
# nhãn dẫn, hoặc bị cắt ngay đầu). Trùng với ngưỡng script 06 vẫn dùng.
MIN_EVOLVED_LENGTH = 20


def filter_prompt_leakage(evolved_prompt: str) -> bool:
    """Lọc rò rỉ thẻ kỹ thuật."""
    tags = ["#Rewritten Prompt#", "#Given Prompt#", "#Original Prompt#",
            "#Evolved Prompt#", "<|im_start|>", "<|im_end|>", "[INST]", "[/INST]"]
    for tag in tags:
        if tag in evolved_prompt:
            logger.debug(f"❌ Prompt leakage: '{tag}'")
            return False
    return True


# Nhãn dẫn mà model hay lặp lại từ prompt kỹ thuật (mọi technique đều kết bằng
# "Câu hỏi viết lại:" / "Tình huống pháp lý:") — cắt bỏ thay vì loại cả record.
_LEAD_LABEL_RE = re.compile(
    r"^\s*\*{0,2}\s*"
    r"(?:câu hỏi (?:viết lại|mới)|tình huống pháp lý|câu hỏi đã viết lại|"
    r"rewritten prompt|evolved prompt|đáp án|trả lời)"
    # dấu ** có thể nằm trước HOẶC sau dấu hai chấm: "**Nhãn:**" lẫn "**Nhãn**:"
    r"\s*\*{0,2}\s*[:：]\s*\*{0,2}\s*",
    re.IGNORECASE,
)


def strip_lead_label(text: str) -> str:
    """Cắt nhãn dẫn thừa ở đầu output (không phải lỗi nội dung, chỉ là format)."""
    if not text:
        return text
    cleaned = _LEAD_LABEL_RE.sub("", text.strip(), count=1)
    return cleaned.strip()


# ── Refusal ───────────────────────────────────────────────────────
# Pattern PHẢI đủ cụ thể: "xin lỗi" trần trụi là chế tài dân sự hợp lệ
# ("buộc xin lỗi, cải chính công khai" - Điều 592 BLDS 2015), không phải từ chối.
_REFUSAL_PATTERNS = [
    r"xin lỗi[,.\s]*(?:nhưng\s+)?tôi\s+không\s+thể",
    r"rất tiếc[,.\s]*(?:nhưng\s+)?tôi\s+không\s+thể",
    r"tôi\s+không\s+thể\s+(?:giúp|hỗ trợ|trả lời|cung cấp|thực hiện|đưa ra|tư vấn)",
    r"tôi\s+là\s+một\s+(?:mô hình|trợ lý|ai\b)",
    r"với tư cách là một\s+(?:ai\b|mô hình)",
    r"không thể thực hiện yêu cầu",
    r"i\s+cannot\s+(?:help|assist|provide|answer)",
    r"i'm sorry[,.\s]*(?:but\s+)?i\s+can(?:not|'t)",
    r"as an ai(?:\s+language)?\s+model",
]

# Từ khoá mơ hồ — chỉ dùng cho response RẤT ngắn (giữ hành vi cũ của max_short).
_WEAK_REFUSAL_PATTERNS = [r"xin lỗi", r"không thể thực hiện", r"là một ai",
                          r"tôi không thể", r"i cannot", r"i'm sorry", r"as an ai"]


def filter_refusal(response: str, max_short: int = 100, window: int = 400) -> bool:
    """
    Lọc câu trả lời từ chối.

    Args:
        response: Nội dung phản hồi.
        max_short: Ngưỡng "response ngắn" cho nhóm từ khoá mơ hồ (hành vi cũ).
        window: Số ký tự đầu được quét cho nhóm pattern cụ thể. Giới hạn cửa sổ
            để tránh dính lời trích dẫn của đương sự ở phần Application.
    """
    if not response:
        return True

    head = response[:window].lower()
    for p in _REFUSAL_PATTERNS:
        if re.search(p, head):
            logger.debug(f"❌ Refusal: '{p}'")
            return False

    # Hành vi cũ: response quá ngắn + từ khoá mơ hồ → nhiều khả năng là từ chối.
    if len(response) < max_short:
        resp_lower = response.lower()
        for p in _WEAK_REFUSAL_PATTERNS:
            if re.search(p, resp_lower):
                logger.debug(f"❌ Refusal (ngắn): '{p}'")
                return False
    return True


def filter_semantic_similarity(original: str, evolved: str, threshold: float = None) -> bool:
    """Lọc trùng lặp ngữ nghĩa (TF-IDF Cosine)."""
    threshold = threshold if threshold is not None else SIMILARITY_THRESHOLD
    if not original or not evolved:
        return True
    try:
        matrix = TfidfVectorizer().fit_transform([original, evolved])
        score = cosine_similarity(matrix[0:1], matrix[1:2])[0][0]
        if score > threshold:
            logger.debug(f"❌ Similarity too high: {score:.3f}")
            return False
        return True
    except Exception as e:
        logger.warning(f"Cosine similarity error: {e}")
        return True


# ── IRAC ──────────────────────────────────────────────────────────
# Heading phải kết bằng DẤU HAI CHẤM. Nếu chỉ dò từ khoá trần ("quy định",
# "áp dụng") thì mọi đoạn văn xuôi pháp lý đều lọt.
_IRAC_WORDS = {
    "Issue":       r"(?:vấn\s*đề|issue)",
    "Rule":        r"(?:quy\s*tắc|căn\s*cứ\s*pháp\s*lý|cơ\s*sở\s*pháp\s*lý|quy\s*định|rule)",
    "Application": r"(?:áp\s*dụng|phân\s*tích|nhận\s*định|application)",
    "Conclusion":  r"(?:kết\s*luận|conclusion|kết\s*quả)",
}
_IRAC_HEADINGS = {
    k: re.compile(v + r"\s*(?:\([^)\n]{0,25}\))?\s*\**\s*[:：]", re.IGNORECASE)
    for k, v in _IRAC_WORDS.items()
}
_IRAC_ORDER = ["Issue", "Rule", "Application", "Conclusion"]


def filter_irac_structure(
    response: str, min_sections: int = 3, require_order: bool = True
) -> bool:
    """
    Kiểm tra cấu trúc IRAC.

    Args:
        response: Nội dung phản hồi.
        min_sections: Số phần IRAC tối thiểu (mặc định 3/4).
        require_order: Các phần tìm được phải xuất hiện đúng thứ tự I→R→A→C.
    """
    if not response:
        return False

    positions = {}
    for key, rx in _IRAC_HEADINGS.items():
        m = rx.search(response)
        if m:
            positions[key] = m.start()

    if len(positions) < min_sections:
        logger.debug(f"❌ IRAC incomplete: {sorted(positions)}")
        return False

    if require_order:
        seq = [positions[k] for k in _IRAC_ORDER if k in positions]
        if seq != sorted(seq):
            logger.debug(f"❌ IRAC sai thứ tự: {sorted(positions, key=positions.get)}")
            return False

    return True


def filter_min_length(response: str, min_len: int = 200) -> bool:
    """Lọc response quá ngắn."""
    if len(response) < min_len:
        logger.debug(f"❌ Too short: {len(response)}")
        return False
    return True


_warned_empty_refs = False

# Số hiệu trần dạng "100/2019/NĐ-CP" nằm trong chuỗi "Nghị định 100/2019/NĐ-CP".
_REF_NUMBER_RE = re.compile(r"\d+/\d{4}/[\w\-]+", re.UNICODE)

# Memo 1 phần tử: pipeline truyền cùng một object set suốt cả lượt chạy, nên
# dựng index một lần là đủ. Key kèm len() để tránh id() bị tái sử dụng sau GC.
_ref_index_cache: tuple = (None, None)


def _ref_index(legal_refs: set[str]) -> set[str]:
    """
    Dựng index tra cứu O(1) cho số hiệu hợp lệ.

    Bản cũ dùng `r.lower() in k.lower()` quét tuyến tính toàn bộ tập. Với corpus
    thật (144.612 số hiệu) điều đó vừa chậm (~55ms mỗi response) vừa SAI: số hiệu
    bịa `2/2015/TT-BTC` được coi là hợp lệ chỉ vì nó là chuỗi con của
    `182/2015/TT-BTC`. Tập nhỏ không lộ ra lỗi này, tập lớn thì lộ.
    """
    global _ref_index_cache
    key = (id(legal_refs), len(legal_refs))
    if _ref_index_cache[0] == key:
        return _ref_index_cache[1]

    index = set()
    for k in legal_refs:
        kl = (k or "").strip().lower()
        if not kl:
            continue
        index.add(kl)
        m = _REF_NUMBER_RE.search(kl)
        if m:
            index.add(m.group(0))       # để "Nghị định X" cũng khớp được "X"
    _ref_index_cache = (key, index)
    return index


def filter_legal_hallucination(response: str, legal_refs: set[str] = None) -> bool:
    """Đối chiếu số hiệu luật với dataset gốc."""
    global _warned_empty_refs
    if not legal_refs:
        if not _warned_empty_refs:
            _warned_empty_refs = True
            logger.warning(
                "⚠️  legal_refs RỖNG → bộ lọc hallucination đang TẮT hoàn toàn. "
                "Nguyên nhân thường gặp: preprocessed_cache.jsonl cũ có metadata rỗng. "
                "Xoá cache và chạy lại 01_download_data.py để bật lại bộ lọc này."
            )
        return True
    patterns = [r"(\d+/\d{4}/(?:NĐ-CP|TT-\w+|QĐ-\w+|QH\d*))",
                r"(Nghị\s+định\s+\d+/\d{4}/NĐ-CP)",
                r"(Thông\s+tư\s+\d+/\d{4}/TT-\w+)"]
    found = set()
    for p in patterns:
        found.update(re.findall(p, response))
    if not found:
        return True
    index = _ref_index(legal_refs)
    bad = [r for r in found if r.strip().lower() not in index]
    if bad:
        # INFO chứ không DEBUG: cần thấy được tỉ lệ này để hiệu chỉnh phạm vi corpus.
        logger.info(f"⚠️ Hallucinated refs: {bad}")
        return False
    return True


# ── Pool Deduplication ────────────────────────────────────────────

class PoolDeduplicator:
    """
    Chống trùng lặp trên toàn bộ pool instruction đã accept.

    `filter_semantic_similarity` chỉ so seed ↔ evolved của CÙNG một item, nên hai
    seed khác nhau tiến hoá ra hai câu gần y hệt thì cả hai đều lọt. Lớp này so
    ứng viên với mọi câu đã nhận.

    Dùng HashingVectorizer (stateless, không cần fit) để chi phí là O(n) mỗi item;
    fit TfidfVectorizer theo từng cặp sẽ tốn ~125k lần fit cho pool 500 câu.

    Ngưỡng mặc định 0.92 chọn từ số đo thực nghiệm trên văn bản pháp lý tiếng Việt:
    hai case HỢP LỆ chỉ khác tên đương sự/địa danh/ngày đo được 0.829, còn bản
    trùng thật chỉ khác hư từ đo được 0.948. 0.92 nằm giữa, lệch về phía giữ dữ liệu.
    """

    DEFAULT_THRESHOLD = 0.92

    def __init__(self, threshold: float = None, n_features: int = 2 ** 18):
        self.threshold = self.DEFAULT_THRESHOLD if threshold is None else threshold
        self._vec = HashingVectorizer(
            n_features=n_features, alternate_sign=False, norm="l2", ngram_range=(1, 2)
        )
        self._matrix = None      # scipy sparse, mỗi hàng là 1 instruction đã nhận
        self._texts: list[str] = []

    def __len__(self) -> int:
        return len(self._texts)

    def check(self, text: str) -> tuple[bool, float, str | None]:
        """
        Returns:
            (is_unique, max_similarity, câu gần nhất trong pool)
        """
        if not text or self._matrix is None:
            return True, 0.0, None
        try:
            v = self._vec.transform([text])
            sims = (self._matrix @ v.T).toarray().ravel()
            if sims.size == 0:
                return True, 0.0, None
            idx = int(sims.argmax())
            score = float(sims[idx])
            if score > self.threshold:
                return False, score, self._texts[idx]
            return True, score, self._texts[idx]
        except Exception as e:
            logger.warning(f"Pool dedup error: {e}")
            return True, 0.0, None

    def add(self, text: str):
        """Thêm một instruction đã accept vào pool."""
        if not text:
            return
        try:
            from scipy.sparse import vstack
            v = self._vec.transform([text])
            self._matrix = v if self._matrix is None else vstack([self._matrix, v])
            self._texts.append(text)
        except Exception as e:
            logger.warning(f"Pool dedup add error: {e}")

    def seed_from(self, texts: list[str]):
        """Nạp lại pool từ các record đã có (dùng khi resume từ checkpoint)."""
        for t in texts:
            self.add(t)


# ── Bộ lọc tổng hợp ───────────────────────────────────────────────

def eliminate_evolved(
    original_prompt: str, evolved_prompt: str,
    sim_threshold: float = None, pool: PoolDeduplicator = None,
) -> tuple[bool, list[str]]:
    """
    Lọc SỚM chỉ dựa trên evolved prompt — chạy TRƯỚC khi gọi LLM sinh IRAC.

    Item rớt ở đây tiết kiệm được trọn một lượt gọi LLM (lượt đắt nhất, output dài
    nhất). Không thay thế `instruction_eliminator`, chỉ chạy trước nó.

    Returns: (passed, failed_filters)
    """
    fails = []
    # Model trả rỗng (bị chặn, hoặc chỉ sinh ra nhãn dẫn rồi bị strip) vẫn lọt mọi
    # bộ lọc phía dưới — similarity với chuỗi rỗng trả True — nên phải chặn ở đây,
    # nếu không sẽ tốn một lượt sinh IRAC cho một prompt trống.
    if len(evolved_prompt.strip()) < MIN_EVOLVED_LENGTH:
        logger.debug(f"❌ Evolved quá ngắn: {len(evolved_prompt.strip())} ký tự")
        fails.append("evolved_too_short")
        return False, fails
    if not filter_prompt_leakage(evolved_prompt):
        fails.append("prompt_leakage")
    if not filter_semantic_similarity(original_prompt, evolved_prompt, sim_threshold):
        fails.append("semantic_similarity")
    if pool is not None:
        unique, score, nearest = pool.check(evolved_prompt)
        if not unique:
            logger.info(
                f"❌ Trùng pool (sim={score:.3f}): {evolved_prompt[:70]!r} "
                f"≈ {(nearest or '')[:70]!r}"
            )
            fails.append("pool_duplicate")
    return len(fails) == 0, fails


def instruction_eliminator(
    original_prompt: str, evolved_prompt: str, response: str,
    legal_refs: set[str] = None, sim_threshold: float = None,
    pool: PoolDeduplicator = None, min_irac_sections: int = 3,
) -> tuple[bool, list[str]]:
    """Bộ lọc tổng hợp. Returns (passed, failed_filters)."""
    fails = []
    if not filter_prompt_leakage(evolved_prompt):
        fails.append("prompt_leakage")
    if not filter_refusal(response):
        fails.append("refusal")
    if not filter_min_length(response):
        fails.append("min_length")
    if not filter_semantic_similarity(original_prompt, evolved_prompt, sim_threshold):
        fails.append("semantic_similarity")
    if not filter_irac_structure(response, min_sections=min_irac_sections):
        fails.append("irac_structure")
    if not filter_legal_hallucination(response, legal_refs):
        fails.append("legal_hallucination")
    if pool is not None:
        unique, score, nearest = pool.check(evolved_prompt)
        if not unique:
            logger.info(
                f"❌ Trùng pool (sim={score:.3f}): {evolved_prompt[:70]!r} "
                f"≈ {(nearest or '')[:70]!r}"
            )
            fails.append("pool_duplicate")

    passed = len(fails) == 0
    if not passed:
        logger.debug(f"❌ REJECTED → {fails}")
    else:
        logger.debug("✅ ACCEPTED")
    return passed, fails
