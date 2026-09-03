"""
Stage 1: Query Evolution (Query Rewriting).

Mở rộng câu hỏi thô của user thành câu hỏi chuẩn pháp lý
theo framework IRAC, bổ sung thuật ngữ pháp luật.

Không dùng LangChain vì:
- Pipeline này là linear flow, không cần stateful graph
- Kiểm soát trực tiếp prompt và logging tốt hơn cho nghiên cứu
"""

from openai import OpenAI
from loguru import logger

QUERY_REWRITE_PROMPT = """Bạn là chuyên gia pháp lý Việt Nam. Nhiệm vụ của bạn là cải thiện câu hỏi pháp lý.

Câu hỏi gốc: {query}

Hãy viết lại câu hỏi theo hướng:
1. Bổ sung thuật ngữ pháp lý chuẩn (tên Luật, Bộ luật, Nghị định nếu có thể)
2. Làm rõ tình huống cụ thể (chủ thể, hành vi, hậu quả)
3. Xác định vấn đề pháp lý cốt lõi (Issue theo IRAC)

Chỉ trả về câu hỏi đã được viết lại, không giải thích thêm."""


class QueryEvolver:
    """
    Stage 1: Dùng LLM nhỏ để rewrite query trước khi retrieval.
    Cải thiện semantic search accuracy cho câu hỏi pháp luật.
    """

    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.3):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.temperature = temperature

    def evolve(self, query: str) -> str:
        """Rewrite câu hỏi, fallback về query gốc nếu lỗi."""
        try:
            prompt = QUERY_REWRITE_PROMPT.format(query=query)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=256,
            )
            evolved = response.choices[0].message.content.strip()
            logger.debug(f"Query evolved: '{query}' → '{evolved}'")
            return evolved
        except Exception as e:
            logger.warning(f"Query evolution failed, using original: {e}")
            return query
