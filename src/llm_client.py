"""
LLM Client - Wrapper cho OpenAI-compatible API (LM Studio).
Hỗ trợ retry với exponential backoff qua tenacity.
"""

import openai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from loguru import logger

from config.settings import (
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL_NAME,
    MAX_TOKENS,
    TOP_P,
    STOP_TOKENS,
    MAX_RETRIES,
)


class LLMClient:
    """
    Client gọi LLM qua OpenAI-compatible API.

    Tương thích với LM Studio local server tại localhost:1234.
    Tự động retry khi gặp lỗi kết nối hoặc API quá tải.
    """

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        model_name: str = None,
    ):
        self.base_url = base_url or LLM_BASE_URL
        self.api_key = api_key or LLM_API_KEY
        self.model_name = model_name or LLM_MODEL_NAME

        self.client = openai.OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

        logger.info(
            f"LLMClient initialized → {self.base_url} | model={self.model_name}"
        )

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type((
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.RateLimitError,
            openai.InternalServerError,
        )),
        before_sleep=before_sleep_log(logger, "WARNING"),
        reraise=True,
    )
    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = None,
        top_p: float = None,
        stop: list[str] = None,
    ) -> str:
        """
        Gọi LLM chat completion.

        Args:
            messages: Danh sách messages [{"role": "system/user", "content": "..."}]
            temperature: Nhiệt độ sampling (0.0 - 2.0)
            max_tokens: Số token tối đa cho response
            top_p: Nucleus sampling threshold
            stop: Danh sách stop tokens

        Returns:
            Nội dung response từ LLM (string).

        Raises:
            openai.APIError: Khi tất cả retry attempts đều thất bại.
        """
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens or MAX_TOKENS,
            top_p=top_p or TOP_P,
            stop=stop or STOP_TOKENS,
        )

        content = response.choices[0].message.content
        if content:
            content = content.strip()

        # Log thống kê usage nếu có
        if response.usage:
            logger.debug(
                f"LLM usage: prompt={response.usage.prompt_tokens}, "
                f"completion={response.usage.completion_tokens}, "
                f"total={response.usage.total_tokens}"
            )

        return content or ""

    def health_check(self) -> bool:
        """Kiểm tra kết nối đến LM Studio server."""
        try:
            result = self.chat(
                messages=[{"role": "user", "content": "Xin chào, trả lời ngắn gọn."}],
                temperature=0.1,
                max_tokens=50,
            )
            logger.info(f"Health check OK → response: {result[:80]}...")
            return True
        except Exception as e:
            logger.error(f"Health check FAILED → {e}")
            return False
