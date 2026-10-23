"""
Stage 5: LLM Generator — Sinh câu trả lời pháp lý từ context đã Rerank.

Nhận top-K chunks sau Reranker, xây dựng system prompt chuyên pháp lý,
gửi đến LLM và trả về câu trả lời.

Backend được hỗ trợ:
- LM Studio / OpenAI-compatible (local, mặc định)
- Google Gemini API (cloud, free-tier, ưu tiên nếu GEMINI_API_KEY được set)

Thiết kế:
- Không dùng LangChain (kiểm soát prompt trực tiếp, dễ debug cho nghiên cứu)
- Hỗ trợ streaming (generator) và non-streaming (một lần)
- Fallback an toàn: nếu LLM lỗi → trả về None thay vì raise
- Context window budget: mỗi chunk bị cắt theo MAX_CHUNK_CHARS
"""

import os
from typing import List, Dict, Any, Optional, Iterator
from openai import OpenAI, APIError, APIConnectionError
from loguru import logger

# Google Gemini SDK (chuẩn mới google-genai, thay thế google-generativeai đã deprecated)
try:
    from google import genai
    from google.genai import types as genai_types
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False
    logger.warning(
        "google-genai chưa được cài đặt. Gemini backend không khả dụng. "
        "Chạy: pip install google-genai"
    )

# ── Prompt Templates ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Bạn là chuyên gia tư vấn pháp lý Việt Nam — am hiểu sâu pháp luật, diễn đạt rõ ràng và gần gũi với người dùng không chuyên.

## Nguyên tắc tư duy (IRAC nội bộ)
Trước khi trả lời, hãy tự phân tích theo khung IRAC trong đầu:
- **Issue**: Câu hỏi thực sự đang hỏi vấn đề pháp lý gì?
- **Rule**: Điều khoản nào trong [CONTEXT] áp dụng trực tiếp?
- **Application**: Quy định đó giải quyết tình huống cụ thể này ra sao?
- **Conclusion**: Kết luận pháp lý là gì?

## Cách trình bày câu trả lời (linh hoạt theo độ phức tạp)

**Câu hỏi đơn giản / tra cứu nhanh** (ví dụ: "mức phạt là bao nhiêu?", "điều kiện X là gì?"):
→ Trả lời trực tiếp, súc tích 2–4 câu. Trích dẫn điều khoản gọn trong câu. Không cần đặt heading.

**Câu hỏi tình huống / tranh chấp / phân tích** (ví dụ: "trường hợp này có vi phạm không?", "ai chịu trách nhiệm?"):
→ Dùng cấu trúc rõ ràng hơn, có thể đặt tiêu đề từng phần nếu cần.
→ Phân tích từng yếu tố cấu thành, đối chiếu với điều khoản, rồi kết luận.

**Câu hỏi so sánh / nhiều phương án** (ví dụ: "khác nhau thế nào?", "áp dụng luật nào?"):
→ Có thể dùng danh sách hoặc bảng để so sánh rõ ràng.

## Quy tắc bất biến
- Trả lời bằng tiếng Việt, ngôn ngữ chuyên nghiệp nhưng dễ hiểu.
- Trích dẫn chính xác: số điều, khoản, điểm + tên văn bản pháp lý từ [CONTEXT].
- Nếu [CONTEXT] không đủ thông tin → thành thật nói: *"Tôi không tìm thấy điều khoản phù hợp trong cơ sở dữ liệu hiện tại"* và gợi ý hướng tra cứu thêm nếu có thể.
- TUYỆT ĐỐI không bịa đặt hoặc suy diễn điều luật ngoài [CONTEXT]."""

CONTEXT_TEMPLATE = """[CONTEXT — Các điều khoản pháp luật liên quan]
{chunks}

[CÂU HỎI]
{query}

[YÊU CẦU]
Dựa vào các điều khoản trong [CONTEXT], hãy trả lời câu hỏi trên.
Trích dẫn chính xác số điều, khoản, điểm và tên văn bản pháp lý khi lập luận."""

# Giới hạn ký tự mỗi chunk để tránh vượt context window
MAX_CHUNK_CHARS = 2048
# Số chunk tối đa đưa vào context (tránh quá dài)
MAX_CONTEXT_CHUNKS= 10
# Đoạn văn ngắn hơn mức này (gạch đầu dòng rỗng, tiêu đề) không tính khi dò lặp
MIN_LOOP_PARAGRAPH_CHARS = 40


def find_loop_cut(text: str) -> Optional[int]:
    """
    Model nhỏ ở temperature thấp đôi khi lặp nguyên một khối đến hết max_tokens.
    Trả về vị trí bắt đầu khối lặp (để cắt), hoặc None nếu không lặp.
    Chỉ tính là lặp khi >= 2 đoạn dài liên tiếp trùng nguyên văn và đúng thứ tự với
    một khối trước đó — một tiêu đề lặp lại giữa các phần không bị coi là lặp.
    """
    keys: List[str] = []
    starts: List[int] = []
    pos = 0
    for para in text.split("\n"):
        key = " ".join(para.split()).strip("•*-– ").lower()
        if len(key) >= MIN_LOOP_PARAGRAPH_CHARS:
            keys.append(key)
            starts.append(pos)
        pos += len(para) + 1

    for i in range(1, len(keys) - 1):
        for j in range(i):
            if keys[j] == keys[i] and keys[j + 1] == keys[i + 1]:
                return starts[i]
    return None


class LegalGenerator:
    """
    Stage 5: Dùng LLM để sinh câu trả lời pháp lý từ top-K chunks đã rerank.

    Hỗ trợ 2 backend (chọn tự động qua GEMINI_API_KEY trong .env):
    - Gemini (Google Cloud free-tier): ưu tiên khi GEMINI_API_KEY được set
    - LM Studio / OpenAI-compatible (local): mặc định khi không có Gemini key

    Sử dụng trong query router sau Stage 4 (Reranker).
    """

    # Số lượt hội thoại (user+assistant) tối đa được giữ lại
    MAX_HISTORY_TURNS = 10

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 1024,
        timeout: float = 60.0,
        # Gemini config (ưu tiên nếu được cung cấp hoặc có trong env)
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        # ── Conversation history (sliding window, chỉ dùng cho LM Studio) ──
        # Mỗi phần tử: {"role": "user"|"assistant", "content": str}
        self._history: List[Dict[str, str]] = []

        # ── Chọn backend: Gemini ưu tiên nếu có key ──────────────
        _gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        _gemini_model = gemini_model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        if _gemini_key and _GEMINI_AVAILABLE:
            self._gemini_client = genai.Client(api_key=_gemini_key)
            self._gemini_config = genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            self._backend = "gemini"
            self._gemini_model_name = _gemini_model
            self.client = None  # LM Studio client không cần
            logger.info(
                f"LegalGenerator khởi tạo | backend=Gemini | model={_gemini_model} | "
                f"temperature={temperature} | max_output_tokens={max_tokens}"
            )
        else:
            if _gemini_key and not _GEMINI_AVAILABLE:
                logger.warning(
                    "GEMINI_API_KEY được set nhưng google-genai chưa cài. "
                    "Fallback sang LM Studio. Chạy: pip install google-genai"
                )
            self._gemini_client = None
            self._backend = "lmstudio"
            self.client = OpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=timeout,
            )
            logger.info(
                f"LegalGenerator khởi tạo | backend=LMStudio | model={model} | "
                f"base_url={base_url} | temperature={temperature} | max_tokens={max_tokens}"
            )

    # ── Conversation History Management ──────────────────────────────────────

    def add_to_history(self, user_msg: str, assistant_msg: str) -> None:
        """
        Thêm một lượt hội thoại vào history.
        Giữ tối đa MAX_HISTORY_TURNS lượt (sliding window).
        """
        self._history.append({"role": "user", "content": user_msg})
        self._history.append({"role": "assistant", "content": assistant_msg})
        # Giữ tối đa MAX_HISTORY_TURNS lượt (mỗi lượt = 2 messages: user + assistant)
        max_messages = self.MAX_HISTORY_TURNS * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
            logger.debug(
                f"History trimmed → giữ {self.MAX_HISTORY_TURNS} lượt gần nhất "
                f"({max_messages} messages)"
            )

    def clear_history(self) -> None:
        """Xóa toàn bộ lịch sử hội thoại (dùng khi bắt đầu phiên mới)."""
        self._history.clear()
        logger.info("Conversation history đã được xóa.")

    @property
    def history_turns(self) -> int:
        """Số lượt hội thoại hiện đang lưu trong history."""
        return len(self._history) // 2

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

    def _build_messages(
        self, query: str, chunks: List[Dict[str, Any]], include_history: bool = True
    ) -> List[Dict[str, str]]:
        """
        Xây dựng danh sách messages theo định dạng OpenAI Chat.
        Chèn conversation history (nếu có) giữa system prompt và câu hỏi hiện tại.
        """
        context_str = self._build_context(chunks)
        user_content = CONTEXT_TEMPLATE.format(chunks=context_str, query=query)

        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Chèn lịch sử hội thoại trước câu hỏi hiện tại (chỉ LM Studio)
        if include_history and self._history:
            messages.extend(self._history)
            logger.debug(f"Đã chèn {self.history_turns} lượt hội thoại vào messages.")

        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_user_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """Xây dựng user prompt (dùng cho Gemini, system prompt đã set ở constructor)."""
        context_str = self._build_context(chunks)
        return CONTEXT_TEMPLATE.format(chunks=context_str, query=query)

    # ── Gemini Backend ────────────────────────────────────────────────────────
 
    def _generate_gemini(self, query: str, chunks: List[Dict[str, Any]]) -> Optional[str]:
        """Sinh câu trả lời qua Gemini API (non-streaming)."""
        user_prompt = self._build_user_prompt(query, chunks)
        try:
            response = self._gemini_client.models.generate_content(
                model=self._gemini_model_name,
                contents=user_prompt,
                config=self._gemini_config,
            )
            text = response.text.strip() if response.text else ""
            if not text:
                logger.warning("Gemini trả về response rỗng.")
                return None
            return text
        except Exception as e:
            logger.error(f"Gemini generate lỗi: {e}")
            return None

    def _generate_stream_gemini(self, query: str, chunks: List[Dict[str, Any]]) -> Iterator[str]:
        """Sinh câu trả lời qua Gemini API (streaming)."""
        user_prompt = self._build_user_prompt(query, chunks)
        try:
            for chunk_resp in self._gemini_client.models.generate_content_stream(
                model=self._gemini_model_name,
                contents=user_prompt,
                config=self._gemini_config,
            ):
                if chunk_resp.text:
                    yield chunk_resp.text
        except Exception as e:
            logger.error(f"Gemini stream lỗi: {e}")

    # ── Non-streaming Generate ────────────────────────────────────────────────

    def generate(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Sinh câu trả lời pháp lý (non-streaming).

        Tự động chọn backend Gemini hoặc LM Studio dựa trên cấu hình.

        Args:
            query: Câu hỏi gốc của user.
            chunks: Danh sách chunks đã rerank từ Stage 4.

        Returns:
            Câu trả lời dạng chuỗi, hoặc None nếu LLM lỗi.
        """
        if not chunks:
            logger.warning("Generator: không có chunks → bỏ qua generation.")
            return None

        logger.info(
            f"Stage 5 Generate | backend={self._backend} | query='{query[:60]}...' | "
            f"chunks={min(len(chunks), MAX_CONTEXT_CHUNKS)}"
        )

        # ── Gemini backend ───────────────────────────────────────
        if self._backend == "gemini":
            answer = self._generate_gemini(query, chunks)
            if answer:
                logger.info(f"Stage 5 done (Gemini) | answer_len={len(answer)} chars")
            return answer

        # ── LM Studio backend (stream nội bộ để detect loop sớm) ─
        messages = self._build_messages(query, chunks, include_history=True)
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )

            content = ""
            for chunk_event in stream:
                delta = chunk_event.choices[0].delta if chunk_event.choices else None
                if not (delta and delta.content):
                    continue
                content += delta.content
                if "\n" in delta.content:
                    cut = find_loop_cut(content)
                    if cut is not None:
                        logger.warning(f"Generator: phát hiện lặp khối ở ký tự {cut} → dừng sinh và cắt.")
                        content = content[:cut]
                        stream.close()
                        break
            else:
                cut = find_loop_cut(content)
                if cut is not None:
                    content = content[:cut]

            if not content or not content.strip():
                logger.warning("Generator: LLM trả về content rỗng.")
                return None

            answer = content.strip()
            # ── Lưu lượt này vào conversation history ────────────
            self.add_to_history(query, answer)
            logger.info(
                f"Stage 5 done (LMStudio) | answer_len={len(answer)} chars | "
                f"history={self.history_turns}/{self.MAX_HISTORY_TURNS} turns"
            )
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

        Tự động chọn backend Gemini hoặc LM Studio.
        Dùng cho FastAPI StreamingResponse hoặc SSE.

        Ví dụ:
            for token in generator.generate_stream(query, chunks):
                print(token, end="", flush=True)
        """
        if not chunks:
            logger.warning("Generator stream: không có chunks.")
            return

        logger.info(
            f"Stage 5 Stream | backend={self._backend} | query='{query[:60]}...' | "
            f"chunks={min(len(chunks), MAX_CONTEXT_CHUNKS)}"
        )

        # ── Gemini streaming ─────────────────────────────────────
        if self._backend == "gemini":
            yield from self._generate_stream_gemini(query, chunks)
            return

        # ── LM Studio streaming ───────────────────────────────────
        messages = self._build_messages(query, chunks, include_history=True)
        collected: List[str] = []
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
                    collected.append(delta.content)
                    yield delta.content

        except APIConnectionError as e:
            logger.error(f"Generator stream: Không kết nối LLM: {e}")
        except APIError as e:
            logger.error(f"Generator stream: API lỗi: {e}")
        except Exception as e:
            logger.error(f"Generator stream: Lỗi: {e}")
        finally:
            # Lưu lượt hội thoại vào history sau khi stream hoàn tất
            if collected:
                full_answer = "".join(collected).strip()
                self.add_to_history(query, full_answer)
                logger.info(
                    f"Stage 5 stream done (LMStudio) | answer_len={len(full_answer)} chars | "
                    f"history={self.history_turns}/{self.MAX_HISTORY_TURNS} turns"
                )

