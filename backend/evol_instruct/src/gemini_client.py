"""
Gemini Client - Wrapper cho Google Gemini API.

Sử dụng google-genai SDK (mới nhất) với gemini-2.5-flash.
Tích hợp retry, logging, và rate-limit handling.
"""

import time
import random
from loguru import logger
from google import genai
from google.genai import types

from config.settings import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_EVOL_TEMPERATURE,
    GEMINI_ANSWER_TEMPERATURE,
    GEMINI_MAX_RETRIES,
)


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
        logger.info(f"GeminiClient initialized | model={self.model}")

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_retries: int = None,
    ) -> str:
        """
        Gọi Gemini API với system + user prompt.

        Args:
            system_prompt: Vai trò/ngữ cảnh cho model.
            user_prompt: Nội dung câu hỏi/yêu cầu.
            temperature: 0.0-2.0 (None = dùng GEMINI_EVOL_TEMPERATURE).
            max_retries: Số lần retry tối đa (None = GEMINI_MAX_RETRIES).

        Returns:
            Text response từ Gemini.

        Raises:
            RuntimeError: Sau khi hết retry attempts.
        """
        temperature = temperature if temperature is not None else GEMINI_EVOL_TEMPERATURE
        max_retries = max_retries or GEMINI_MAX_RETRIES

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
        )

        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=user_prompt,
                    config=config,
                )
                text = response.text or ""
                logger.debug(
                    f"Gemini OK (attempt {attempt}) | "
                    f"temp={temperature} | chars={len(text)}"
                )
                return text.strip()

            except Exception as e:
                err_str = str(e)

                # Rate limit (429) → đợi lâu hơn
                if "429" in err_str or "quota" in err_str.lower():
                    wait = min(60 * attempt, 120)
                    logger.warning(
                        f"Rate limit (attempt {attempt}/{max_retries}). "
                        f"Chờ {wait}s..."
                    )
                    time.sleep(wait)

                # Server error tạm thời (5xx) → đợi ngắn
                elif "500" in err_str or "503" in err_str:
                    wait = 5 * attempt + random.uniform(0, 3)
                    logger.warning(
                        f"Server error (attempt {attempt}/{max_retries}). "
                        f"Chờ {wait:.1f}s..."
                    )
                    time.sleep(wait)

                # Lỗi khác không retry được → raise ngay
                else:
                    logger.error(f"Gemini error (không retry): {e}")
                    raise

        raise RuntimeError(
            f"Gemini API thất bại sau {max_retries} lần thử. "
            "Kiểm tra API key hoặc quota."
        )

    def evolve(self, system_prompt: str, user_prompt: str) -> str:
        """Gọi với temperature cao (evol phase)."""
        return self.chat(system_prompt, user_prompt, temperature=GEMINI_EVOL_TEMPERATURE)

    def answer(self, system_prompt: str, user_prompt: str) -> str:
        """Gọi với temperature thấp (answer/IRAC phase)."""
        return self.chat(system_prompt, user_prompt, temperature=GEMINI_ANSWER_TEMPERATURE)

    def health_check(self) -> bool:
        """Kiểm tra kết nối Gemini API."""
        try:
            result = self.chat(
                system_prompt="You are a helpful assistant.",
                user_prompt="Reply with exactly: OK",
                temperature=0.0,
                max_retries=1,
            )
            ok = "ok" in result.lower() or len(result) > 0
            if ok:
                logger.info(f"Gemini health check OK | model={self.model}")
            return ok
        except Exception as e:
            logger.error(f"Gemini health check FAILED: {e}")
            return False
