"""
Instruction Eliminator - Bộ lọc loại bỏ dữ liệu lỗi.

6 bộ lọc:
1. Prompt Leakage     2. Refusal
3. Semantic Similarity 4. IRAC Structure
5. Min Length          6. Legal Hallucination
"""

import re
from loguru import logger
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config.settings import SIMILARITY_THRESHOLD


def filter_prompt_leakage(evolved_prompt: str) -> bool:
    """Lọc rò rỉ thẻ kỹ thuật."""
    tags = ["#Rewritten Prompt#", "#Given Prompt#", "#Original Prompt#",
            "#Evolved Prompt#", "<|im_start|>", "<|im_end|>", "[INST]", "[/INST]"]
    for tag in tags:
        if tag in evolved_prompt:
            logger.debug(f"❌ Prompt leakage: '{tag}'")
            return False
    return True


def filter_refusal(response: str, max_short: int = 100) -> bool:
    """Lọc từ chối trả lời (chỉ khi response ngắn)."""
    patterns = [r"xin lỗi", r"không thể thực hiện", r"là một ai",
                r"tôi không thể", r"i cannot", r"i'm sorry", r"as an ai"]
    resp_lower = response.lower()
    for p in patterns:
        if re.search(p, resp_lower) and len(response) < max_short:
            logger.debug(f"❌ Refusal: '{p}'")
            return False
    return True


def filter_semantic_similarity(original: str, evolved: str, threshold: float = None) -> bool:
    """Lọc trùng lặp ngữ nghĩa (TF-IDF Cosine)."""
    threshold = threshold or SIMILARITY_THRESHOLD
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


def filter_irac_structure(response: str) -> bool:
    """Kiểm tra cấu trúc IRAC (cần ≥ 3/4 phần)."""
    irac = {
        "Issue": [r"(?:vấn đề|issue)"],
        "Rule": [r"(?:quy tắc|rule|quy định|căn cứ pháp lý)"],
        "Application": [r"(?:áp dụng|application|phân tích|nhận định)"],
        "Conclusion": [r"(?:kết luận|conclusion|kết quả)"],
    }
    resp_lower = response.lower()
    found = [k for k, pats in irac.items() if any(re.search(p, resp_lower) for p in pats)]
    if len(found) < 3:
        logger.debug(f"❌ IRAC incomplete: {found}")
        return False
    return True


def filter_min_length(response: str, min_len: int = 200) -> bool:
    """Lọc response quá ngắn."""
    if len(response) < min_len:
        logger.debug(f"❌ Too short: {len(response)}")
        return False
    return True


def filter_legal_hallucination(response: str, legal_refs: set[str] = None) -> bool:
    """Đối chiếu số hiệu luật với dataset gốc."""
    if not legal_refs:
        return True
    patterns = [r"(\d+/\d{4}/(?:NĐ-CP|TT-\w+|QĐ-\w+|QH\d*))",
                r"(Nghị\s+định\s+\d+/\d{4}/NĐ-CP)",
                r"(Thông\s+tư\s+\d+/\d{4}/TT-\w+)"]
    found = set()
    for p in patterns:
        found.update(re.findall(p, response))
    if not found:
        return True
    bad = [r for r in found if not any(r.lower() in k.lower() for k in legal_refs)]
    if bad:
        logger.debug(f"⚠️ Hallucinated refs: {bad}")
        return False
    return True


def instruction_eliminator(
    original_prompt: str, evolved_prompt: str, response: str,
    legal_refs: set[str] = None, sim_threshold: float = None,
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
    if not filter_irac_structure(response):
        fails.append("irac_structure")
    if not filter_legal_hallucination(response, legal_refs):
        fails.append("legal_hallucination")

    passed = len(fails) == 0
    if not passed:
        logger.debug(f"❌ REJECTED → {fails}")
    else:
        logger.debug("✅ ACCEPTED")
    return passed, fails
