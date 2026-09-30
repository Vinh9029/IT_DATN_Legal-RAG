"""
Stage 5: LLM Generator — Sinh câu trả lời pháp lý từ context đã Rerank.

Nhận top-K chunks sau Reranker, xây dựng system prompt chuyên pháp lý,
gửi đến LLM (LM Studio / OpenAI-compatible) và trả về câu trả lời.

Thiết kế:
- Không dùng LangChain (kiểm soát prompt trực tiếp, dễ debug cho nghiên cứu)
- Hỗ trợ streaming (generator) và non-streaming (một lần)
- Fallback an toàn: nếu LLM lỗi → trả về None thay vì raise
- Context window budget: mỗi chunk bị cắt theo MAX_CHUNK_CHARS
"""

from typing import List, Dict, Any, Optional, Iterator
from openai import OpenAI, APIError, APIConnectionError
from loguru import logger

# ── Prompt Templates ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Bạn là chuyên gia tư vấn pháp lý Việt Nam, chuyên về hệ thống pháp luật Việt Nam.

Nhiệm vụ của bạn:
1. Trả lời câu hỏi pháp lý DỰA TRÊN các điều khoản luật được cung cấp trong phần [CONTEXT].
2. Trích dẫn rõ ràng số điều, tên luật/nghị định khi đưa ra nhận định.
3. Nếu context không đủ thông tin → thành thật nói "Tôi không tìm thấy điều khoản phù hợp trong cơ sở dữ liệu pháp luật hiện tại."
4. KHÔNG bịa đặt điều khoản, KHÔNG suy diễn ngoài phạm vi văn bản pháp luật được cung cấp.
5. Trả lời bằng tiếng Việt, ngắn gọn, rõ ràng, có cấu trúc.

Định dạng câu trả lời:
- Nêu kết luận pháp lý chính trước.
- Trích dẫn điều khoản cụ thể hỗ trợ kết luận.
- Nếu có nhiều góc độ pháp lý → liệt kê từng điểm."""

CONTEXT_TEMPLATE = """[CONTEXT — Các điều khoản pháp luật liên quan]
{chunks}

[CÂU HỎI]
{query}

[YÊU CẦU]
Trả lời dựa trên các điều khoản trên. Trích dẫn số điều và tên văn bản pháp lý khi lập luận."""

# Giới hạn ký tự mỗi chunk để tránh vượt context window
MAX_CHUNK_CHARS = 800
# Số chunk tối đa đưa vào context (tránh quá dài)
MAX_CONTEXT_CHUNKS = 5


class LegalGenerator:
    """
    Stage 5: Dùng LLM (LM Studio / OpenAI-compatible) để sinh câu trả lời
    pháp lý từ top-K chunks đã được rerank.

    Sử dụng trong query router sau Stage 4 (Reranker).
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: float = 60.0,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )
        logger.info(
            f"LegalGenerator khởi tạo | model={model} | base_url={base_url} | "
            f"temperature={temperature} | max_tokens={max_tokens}"
        )

    # ── Context Builder ───────────────────────────────────────────────────────

    def _build_context(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Xây dựng chuỗi context từ danh sách chunks đã rerank.
        Mỗi chunk được format với số điều + tên văn bản + nội dung.
        """
        parts = []
        for i, chunk in enumerate(chunks[:MAX_CONTEXT_CHUNKS], start=1):
            dieu = chunk.get("dieu") or ""
            doc_id = chunk.get("doc_id", "")
            content = (chunk.get("content") or "").strip()
            meta = chunk.get("metadata") or {}
            so_hieu = meta.get("so_hieu", doc_id)
            loai_vb = meta.get("loai_van_ban", "")

            # Tiêu đề nguồn
            source_label = f"{loai_vb} {so_hieu}".strip() if loai_vb else so_hieu
            header = f"[{i}] {source_label}"
            if dieu:
                header += f" — {dieu}"

            # Cắt content nếu quá dài
            if len(content) > MAX_CHUNK_CHARS:
                content = content[:MAX_CHUNK_CHARS] + "..."

            score = chunk.get("rerank_score", chunk.get("rrf_score", 0.0))
            parts.append(f"{header}\n{content}\n(relevance: {score:.3f})")

        return "\n\n---\n\n".join(parts) if parts else "(Không có điều khoản liên quan)"

    def _build_messages(self, query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Xây dựng danh sách messages theo định dạng OpenAI Chat."""
        context_str = self._build_context(chunks)
        user_content = CONTEXT_TEMPLATE.format(chunks=context_str, query=query)
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    # ── Non-streaming Generate ────────────────────────────────────────────────

    def generate(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Sinh câu trả lời pháp lý (non-streaming).

        Args:
            query: Câu hỏi gốc (hoặc evolved query) của user.
            chunks: Danh sách chunks đã rerank từ Stage 4.

        Returns:
            Câu trả lời dạng chuỗi, hoặc None nếu LLM lỗi.
        """
        if not chunks:
            logger.warning("Generator: không có chunks → bỏ qua generation.")
            return None

        messages = self._build_messages(query, chunks)
        logger.info(
            f"Stage 5 Generate | query='{query[:60]}...' | "
            f"chunks={min(len(chunks), MAX_CONTEXT_CHUNKS)} | model={self.model}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            choice = response.choices[0] if response.choices else None
            if choice is None:
                logger.warning("Generator: LLM trả về không có choices.")
                return None

            content = choice.message.content
            if not content or not content.strip():
                logger.warning("Generator: LLM trả về content rỗng.")
                return None

            answer = content.strip()
            logger.info(f"Stage 5 done | answer_len={len(answer)} chars")
            return answer

        except APIConnectionError as e:
            logger.error(f"Generator: Không kết nối được LLM ({self.client.base_url}): {e}")
            return None
        except APIError as e:
            logger.error(f"Generator: LLM API lỗi (status={e.status_code}): {e.message}")
            return None
        except Exception as e:
            logger.error(f"Generator: Lỗi không xác định: {e}")
            return None

    # ── Streaming Generate ────────────────────────────────────────────────────

    def generate_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
    ) -> Iterator[str]:
        """
        Sinh câu trả lời pháp lý theo từng token (streaming).

        Dùng cho FastAPI StreamingResponse hoặc SSE.
        Yield từng đoạn text khi LLM sinh ra.

        Ví dụ:
            for token in generator.generate_stream(query, chunks):
                print(token, end="", flush=True)
        """
        if not chunks:
            logger.warning("Generator stream: không có chunks.")
            return

        messages = self._build_messages(query, chunks)
        logger.info(
            f"Stage 5 Stream | query='{query[:60]}...' | "
            f"chunks={min(len(chunks), MAX_CONTEXT_CHUNKS)}"
        )

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )

            for chunk_event in stream:
                delta = chunk_event.choices[0].delta if chunk_event.choices else None
                if delta and delta.content:
                    yield delta.content

        except APIConnectionError as e:
            logger.error(f"Generator stream: Không kết nối LLM: {e}")
        except APIError as e:
            logger.error(f"Generator stream: API lỗi: {e}")
        except Exception as e:
            logger.error(f"Generator stream: Lỗi: {e}")
