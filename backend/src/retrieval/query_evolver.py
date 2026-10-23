"""
Stage 1: Query Evolution (Query Rewriting + Specificity Classification).

Mở rộng câu hỏi thô của user thành câu hỏi chuẩn pháp lý
theo framework IRAC, bổ sung thuật ngữ pháp luật, đồng thời
phân loại độ đặc thù (broad / narrow) để điều phối chiến lược retrieval.

Không dùng LangChain vì:
- Pipeline này là linear flow, không cần stateful graph
- Kiểm soát trực tiếp prompt và logging tốt hơn cho nghiên cứu
"""

from pathlib import Path
from typing import Dict, Any, Optional
from openai import OpenAI
from loguru import logger

from evol_instruct.src.qa_specificity.routing_classifier import RoutingClassifier

QUERY_REWRITE_PROMPT = """Bạn là chuyên gia pháp lý Việt Nam. Nhiệm vụ của bạn là làm rõ câu hỏi pháp lý mà KHÔNG thay đổi ý định ban đầu.

Câu hỏi gốc: {query}

Hãy viết lại câu hỏi theo đúng 3 quy tắc sau:
1. Chuẩn hoá thuật ngữ pháp lý: thay từ thông thường bằng thuật ngữ pháp luật chính xác
   Ví dụ: "bị bắt" → "bị tạm giữ/tạm giam", "xin ly hôn" → "yêu cầu ly hôn", "hoãn quân sự" → "tạm hoãn gọi nhập ngũ"
2. Làm rõ chủ thể và hành vi nếu câu hỏi mơ hồ (ai làm gì, theo luật nào)
3. Giữ nguyên phạm vi câu hỏi — KHÔNG mở rộng sang chủ đề khác, KHÔNG thêm câu hỏi phụ

Chỉ trả về câu hỏi đã viết lại (1 câu duy nhất), không giải thích."""


class QueryEvolver:
    """
    Stage 1: Query Rewriting kết hợp 2 lớp:
    1. Rule-based (không cần LLM): chuẩn hoá nhanh, bổ sung từ đồng nghĩa pháp lý
    2. LLM-based (LM Studio): chỉ gọi khi query ngắn/mơ hồ cần làm rõ thêm

    Sau đó phân loại specificity ('broad' | 'narrow') qua RoutingClassifier.
    """

    # Query ngắn hơn ngưỡng này → cần LLM làm rõ thêm
    _LLM_REWRITE_MIN_CHARS = 25
    # Từ ngữ thông thường thường gặp → cần chuẩn hoá (rule-based)
    _LEGAL_TERM_MAP = {
        "hoãn quân sự": "tạm hoãn gọi nhập ngũ",
        "hoãn nghĩa vụ": "tạm hoãn gọi nhập ngũ",
        "nhập ngũ trễ": "tạm hoãn gọi nhập ngũ",
        "bị bắt": "bị tạm giữ hình sự",
        "xin ly hôn": "yêu cầu giải quyết ly hôn",
        "kiện": "khởi kiện",
        "đất đai tranh chấp": "tranh chấp quyền sử dụng đất",
        "thuế trốn": "trốn thuế",
        "lương không trả": "nợ lương người lao động",
        "đuổi việc": "chấm dứt hợp đồng lao động",
        "sa thải": "xử lý kỷ luật sa thải",
        "phạt": "xử phạt vi phạm hành chính",
        "tai nạn lao động": "tai nạn lao động theo Luật An toàn vệ sinh lao động",
    }

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        model_dir: Optional[str | Path] = None,
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.temperature = temperature

        if model_dir is None:
            model_dir = Path(__file__).resolve().parents[2] / "models" / "routing_classifier"
        self.classifier = RoutingClassifier(model_dir=model_dir)

    # ── Layer 1: Rule-based normalization ─────────────────────────────────

    def _rule_normalize(self, query: str) -> str:
        """
        Thay thế nhanh từ thông thường → thuật ngữ pháp lý chuẩn.
        Không gọi LLM, không thay đổi cấu trúc câu.
        """
        result = query
        for informal, legal in self._LEGAL_TERM_MAP.items():
            if informal.lower() in result.lower():
                result = result.lower().replace(informal.lower(), legal)
                logger.debug(f"Rule normalize: '{informal}' → '{legal}'")
        return result

    def _needs_llm_rewrite(self, query: str) -> bool:
        """
        Heuristic: gọi LLM rewrite chỉ khi query còn mơ hồ sau rule-based.
        Tiêu chí:
        - Query quá ngắn (< _LLM_REWRITE_MIN_CHARS ký tự)
        - Hoặc không chứa từ khoá pháp lý nào nhận ra được
        """
        if len(query.strip()) < self._LLM_REWRITE_MIN_CHARS:
            return True
        legal_keywords = [
            "điều", "khoản", "luật", "nghị định", "thông tư", "vi phạm",
            "xử phạt", "quyền", "nghĩa vụ", "hợp đồng", "tố tụng",
            "tạm hoãn", "tạm giữ", "tạm giam", "khởi kiện", "tranh chấp",
        ]
        query_lower = query.lower()
        return not any(kw in query_lower for kw in legal_keywords)

    # ── Layer 2: LLM rewrite ───────────────────────────────────────────────

    def _llm_rewrite(self, query: str) -> str:
        """Rewrite câu hỏi bằng LLM; fallback về query gốc nếu lỗi hoặc rỗng."""
        try:
            prompt = QUERY_REWRITE_PROMPT.format(query=query)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=200,
            )
            choice = response.choices[0] if response.choices else None
            if choice is None:
                logger.warning("LLM rewrite: no choices returned, using normalized query.")
                return query

            content = choice.message.content
            if not content or not content.strip():
                logger.warning("LLM rewrite: empty content, using normalized query.")
                return query

            rewritten = content.strip()
            logger.debug(f"LLM rewrite: '{query}' → '{rewritten}'")
            return rewritten
        except Exception as e:
            logger.warning(f"LLM rewrite failed, using normalized query: {e}")
            return query

    # ── Public API ─────────────────────────────────────────────────────────

    def evolve(self, query: str) -> Dict[str, str]:
        """
        Stage 1: Rewrite query 2 lớp + phân loại specificity.

        Flow:
          raw query
            → Layer 1: rule-based normalization (luôn chạy, nhanh)
            → Layer 2: LLM rewrite (chỉ khi query vẫn ngắn/mơ hồ)
            → RoutingClassifier → specificity ('broad' | 'narrow')
        """
        # Layer 1: rule normalize (luôn chạy)
        normalized = self._rule_normalize(query)

        # Layer 2: LLM rewrite (chỉ khi cần)
        if self._needs_llm_rewrite(normalized):
            evolved_query = self._llm_rewrite(normalized)
            rewrite_mode = "llm"
        else:
            evolved_query = normalized
            rewrite_mode = "rule"

        specificity = self.classifier.predict(evolved_query)
        logger.info(
            f"Stage 1 | rewrite={rewrite_mode} | specificity={specificity} | "
            f"'{query}' → '{evolved_query}'"
        )
        return {
            "evolved_query": evolved_query,
            "original_query": query,
            "rewrite_mode": rewrite_mode,
            "specificity": specificity,
        }


