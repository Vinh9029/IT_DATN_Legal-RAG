"""
Gemini Client - Wrapper cho Google Gemini API.

Sử dụng google-genai SDK (mới nhất) với gemini-2.5-flash.
Tích hợp retry, logging, và rate-limit handling.
"""

import os
import time
import random
from loguru import logger
from google import genai
from google.genai import types, errors

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_EVOL_TEMPERATURE,
    GEMINI_ANSWER_TEMPERATURE,
    GEMINI_MAX_RETRIES,
)

# Các knob mới đọc thẳng từ env thay vì thêm vào config/settings.py — file đó là
# nơi hay phát sinh merge conflict nhất, nên phần Evol-Instruct tự lo boilerplate.
# (settings.py đã gọi load_dotenv() lúc import nên os.getenv ở đây có giá trị.)
_THINKING_BUDGET_ENV = os.getenv("GEMINI_THINKING_BUDGET", "auto").strip().lower()
_MAX_OUTPUT_TOKENS = os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "").strip()
_SAFETY_THRESHOLD = os.getenv("GEMINI_SAFETY_THRESHOLD", "BLOCK_ONLY_HIGH").strip().upper()

_UNSET = object()

# finish_reason nghĩa là "nội dung bị chặn", khác hẳn với lỗi mạng: retry vô ích.
_BLOCKED_REASONS = {
    types.FinishReason.SAFETY,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.RECITATION,
    types.FinishReason.BLOCKLIST,
}


class GeminiTruncatedError(RuntimeError):
    """Response chạm trần max_output_tokens → nội dung cụt."""


class GeminiBlockedError(RuntimeError):
    """Response bị safety filter chặn. Nội dung pháp luật hình sự hay dính."""


def _safety_settings() -> list[types.SafetySetting] | None:
    """
    Nới safety cho nội dung pháp lý.

    Văn bản về tội phạm, thương tích, ma tuý là chủ đề pháp luật chính đáng nhưng
    rất dễ bị chặn ở ngưỡng mặc định. Dùng BLOCK_ONLY_HIGH thay vì BLOCK_NONE vì
    BLOCK_NONE cần tài khoản được allowlist, đặt bừa sẽ lỗi cứng lúc gọi API.
    """
    if _SAFETY_THRESHOLD in ("", "DEFAULT"):
        return None
    try:
        threshold = types.HarmBlockThreshold(_SAFETY_THRESHOLD)
    except ValueError:
        logger.warning(
            f"GEMINI_SAFETY_THRESHOLD='{_SAFETY_THRESHOLD}' không hợp lệ, dùng mặc định."
        )
        return None
    return [
        types.SafetySetting(category=c, threshold=threshold)
        for c in (
            types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        )
    ]


class GeminiClient:
    """
    Client gọi Google Gemini API.

    - Retry tự động khi gặp quota/rate-limit (429) hoặc lỗi tạm thời
    - Hỗ trợ 2 mode nhiệt độ: evol (sáng tạo) và answer (chính xác)
    - Thread-safe (dùng trong pipeline tuần tự)
    """

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY không được để trống. "
                "Thêm vào file .env: GEMINI_API_KEY=your_key"
            )

        self.client = genai.Client(api_key=self.api_key)
        self._safety = _safety_settings()
        logger.info(
            f"GeminiClient initialized | model={self.model} | "
            f"thinking={_THINKING_BUDGET_ENV} | safety={_SAFETY_THRESHOLD}"
        )

    # ── Thinking budget ───────────────────────────────────────────

    def _resolve_thinking_budget(self, phase: str, explicit) -> int | None:
        """
        Quyết định thinking budget.

        Gemini 2.5 bật thinking mặc định. Với phase 'evolve' (chỉ viết lại một câu
        hỏi) thì suy luận là lãng phí token thuần tuý; với phase 'answer' (lập luận
        IRAC) thì thinking giúp chất lượng nên để nguyên mặc định.

        Chỉ tự đặt budget=0 cho model 'flash' — 'pro' không nhận budget 0 và sẽ lỗi.
        """
        if explicit is not _UNSET:
            return explicit
        if _THINKING_BUDGET_ENV in ("", "none", "default", "unset"):
            return None
        if _THINKING_BUDGET_ENV != "auto":
            try:
                return int(_THINKING_BUDGET_ENV)
            except ValueError:
                logger.warning(
                    f"GEMINI_THINKING_BUDGET='{_THINKING_BUDGET_ENV}' không phải số, bỏ qua."
                )
                return None
        if phase == "evolve" and "flash" in self.model.lower():
            return 0
        return None

    def _build_config(self, system_prompt, temperature, phase, thinking_budget,
                      max_output_tokens) -> types.GenerateContentConfig:
        kwargs = {
            "system_instruction": system_prompt,
            "temperature": temperature,
        }
        if self._safety:
            kwargs["safety_settings"] = self._safety

        budget = self._resolve_thinking_budget(phase, thinking_budget)
        if budget is not None:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=budget)

        tokens = max_output_tokens
        if tokens is None and _MAX_OUTPUT_TOKENS:
            try:
                tokens = int(_MAX_OUTPUT_TOKENS)
            except ValueError:
                tokens = None
        if tokens:
            kwargs["max_output_tokens"] = tokens

        return types.GenerateContentConfig(**kwargs)

    # ── Kiểm tra response ─────────────────────────────────────────

    def _extract_text(self, response, allow_truncated: bool) -> str:
        """
        Lấy text và phân biệt rõ 3 trường hợp mà `response.text or ""` gộp làm một:
        bình thường / bị cắt / bị chặn.
        """
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            feedback = getattr(response, "prompt_feedback", None)
            raise GeminiBlockedError(f"Không có candidate nào. prompt_feedback={feedback}")

        cand = candidates[0]
        reason = getattr(cand, "finish_reason", None)

        if reason in _BLOCKED_REASONS:
            raise GeminiBlockedError(
                f"Bị chặn (finish_reason={reason}). "
                f"safety_ratings={getattr(cand, 'safety_ratings', None)}"
            )

        text = getattr(response, "text", None) or ""

        if reason == types.FinishReason.MAX_TOKENS:
            msg = f"Response bị cắt (MAX_TOKENS), {len(text)} ký tự: {text[-60:]!r}"
            if allow_truncated:
                logger.warning(f"⚠️  {msg}")
            else:
                raise GeminiTruncatedError(msg)

        return text.strip()

    # ── Gọi API ───────────────────────────────────────────────────

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_retries: int = None,
        phase: str = "evolve",
        thinking_budget=_UNSET,
        max_output_tokens: int = None,
        allow_truncated: bool = True,
    ) -> str:
        """
        Gọi Gemini API với system + user prompt.

        Args:
            system_prompt: Vai trò/ngữ cảnh cho model.
            user_prompt: Nội dung câu hỏi/yêu cầu.
            temperature: 0.0-2.0 (None = dùng GEMINI_EVOL_TEMPERATURE).
            max_retries: Số lần retry tối đa (None = GEMINI_MAX_RETRIES).
            phase: 'evolve' hoặc 'answer' — quyết định thinking budget mặc định.
            thinking_budget: Ghi đè budget cho lần gọi này.
            max_output_tokens: Giới hạn độ dài output.
            allow_truncated: False thì raise GeminiTruncatedError khi bị cắt.

        Returns:
            Text response từ Gemini.

        Raises:
            GeminiBlockedError: Bị safety filter chặn.
            GeminiTruncatedError: Bị cắt và allow_truncated=False.
            RuntimeError: Sau khi hết retry attempts.
        """
        temperature = temperature if temperature is not None else GEMINI_EVOL_TEMPERATURE
        max_retries = max_retries or GEMINI_MAX_RETRIES

        config = self._build_config(
            system_prompt, temperature, phase, thinking_budget, max_output_tokens
        )

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )
                text = self._extract_text(response, allow_truncated)
                logger.debug(
                    f"Gemini OK (attempt {attempt}) | "
                    f"temp={temperature} | phase={phase} | chars={len(text)}"
                )
                return text

            except (GeminiBlockedError, GeminiTruncatedError):
                # Lỗi nội dung, không phải lỗi mạng — retry chỉ tốn quota.
                raise

            except errors.APIError as e:
                last_error = e
                code = getattr(e, "code", None)
                is_last = attempt >= max_retries

                if code == 429:
                    if is_last:
                        break
                    wait = min(60 * attempt, 120)
                    logger.warning(
                        f"Rate limit 429 (attempt {attempt}/{max_retries}). Chờ {wait}s..."
                    )
                elif isinstance(e, errors.ServerError):
                    if is_last:
                        break
                    wait = 5 * attempt + random.uniform(0, 3)
                    logger.warning(
                        f"Server error {code} (attempt {attempt}/{max_retries}). "
                        f"Chờ {wait:.1f}s..."
                    )
                else:
                    # 400/401/403/404… retry không giúp gì.
                    logger.error(f"Gemini client error {code} (không retry): {e}")
                    raise
                time.sleep(wait)

        raise RuntimeError(
            f"Gemini API thất bại sau {max_retries} lần thử. "
            f"Lỗi cuối: {last_error}. Kiểm tra API key hoặc quota."
        )

    def evolve(self, system_prompt: str, user_prompt: str, **kw) -> str:
        """Gọi với temperature cao (evol phase)."""
        # setdefault chứ không truyền thẳng: caller có quyền ghi đè temperature
        # mà không gây TypeError "got multiple values".
        kw.setdefault("phase", "evolve")
        kw.setdefault("temperature", GEMINI_EVOL_TEMPERATURE)
        return self.chat(system_prompt, user_prompt, **kw)

    def answer(self, system_prompt: str, user_prompt: str, **kw) -> str:
        """Gọi với temperature thấp (answer/IRAC phase)."""
        kw.setdefault("phase", "answer")
        kw.setdefault("temperature", GEMINI_ANSWER_TEMPERATURE)
        return self.chat(system_prompt, user_prompt, **kw)

    def health_check(self) -> bool:
        """Kiểm tra kết nối Gemini API."""
        try:
            result = self.chat(
                system_prompt="You are a helpful assistant.",
                user_prompt="Reply with exactly: OK",
                temperature=0.0,
                max_retries=1,
                allow_truncated=True,   # ping ngắn, bị cắt cũng không sao
            )
            ok = "ok" in result.lower() or len(result) > 0
            if ok:
                logger.info(f"Gemini health check OK | model={self.model}")
            return ok
        except Exception as e:
            logger.error(f"Gemini health check FAILED: {e}")
            return False
