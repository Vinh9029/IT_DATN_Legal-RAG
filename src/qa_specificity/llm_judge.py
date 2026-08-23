"""
Tầng 3: LLM judge độc lập.

Ba ràng buộc thiết kế, phá vỡ cái nào thì tầng này mất giá trị kiểm chứng:

1. MODEL KHÁC model sinh. Một LLM có xu hướng chấm cao output do chính nó
   sinh ra (self-preference bias). Dùng cùng model vừa sinh vừa chấm sẽ cho ra
   một con số "độ đồng thuận" đẹp nhưng vô nghĩa.

2. KHÔNG tiết lộ provenance. Judge chỉ thấy câu hỏi trần — không biết câu này
   sinh ở nhánh broad hay narrow, không thấy văn bản gốc, không thấy câu còn
   lại trong cặp.

3. MỘT câu MỘT lần gọi. Gộp nhiều câu vào một prompt làm model bị ảnh hưởng bởi
   ngữ cảnh các câu lân cận (contamination) và phá vỡ tính độc lập của phép
   đánh giá. Chi phí gộp tiết kiệm được không đáng so với thiệt hại này.
"""

import json
import re

import openai

from loguru import logger
from tqdm import tqdm

from config.qa_prompts import build_judge_messages
from config.qa_settings import (
    JUDGE_LLM_API_KEY,
    JUDGE_LLM_BASE_URL,
    JUDGE_MAX_TOKENS,
    JUDGE_MODEL_NAME,
    JUDGE_REASONING_EFFORT,
    JUDGE_TEMPERATURE,
)
from src.llm_client import LLMClient
from src.qa_specificity.schema import QAItem, Specificity
from src.utils import append_jsonl, load_jsonl, truncate_text


# Model hay bọc JSON trong ```json ... ``` hoặc kèm lời dẫn
_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def parse_judge_response(text: str) -> dict:
    """
    Bóc object JSON từ output judge.

    Returns:
        {"label": Specificity|None, "reason": str, "axes": dict}
        `label=None` nghĩa là không parse được — caller coi như judge vắng mặt,
        KHÔNG được mặc định về broad/narrow (sẽ tạo nhãn giả).
    """
    result = {"label": None, "reason": "", "axes": {}}
    if not text:
        return result

    payload = None
    # Ưu tiên parse cả chuỗi; nếu không được thì bốc object JSON đầu tiên
    for candidate in (text.strip(), *(_JSON_BLOCK_RE.findall(text))):
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            payload = parsed
            break

    if payload is None:
        # Fallback cuối: model trả về mỗi chữ "narrow" / "broad" trần
        label = Specificity.parse(text.strip().strip(".\"' `"))
        if label:
            result["label"] = label
            result["reason"] = "parsed từ plain text (không có JSON)"
        return result

    result["label"] = Specificity.parse(payload.get("label"))
    result["reason"] = str(payload.get("reason", ""))[:200]
    result["axes"] = {
        key: payload.get(key)
        for key in ("axis1", "axis2", "axis3")
        if payload.get(key) is not None
    }
    return result


class JudgeClient:
    """
    Wrapper quanh `LLMClient` đã trỏ sẵn tới judge model.

    `LLMClient.__init__` cho override cả base_url/api_key/model_name nên không
    cần viết client mới cho judge (spec §2.2).

    Mượn `LLMClient` để dựng client và giữ health_check, nhưng KHÔNG gọi
    `LLMClient.chat()` — xem `_chat_raw()` để biết lý do (cần `extra_body`).
    Tiện thể tránh luôn được quirk `stop or STOP_TOKENS`: `STOP_TOKENS =
    ["<|eot_id|>"]` là token đặc thù Llama 3.1, và truyền `stop=[]` không vô
    hiệu hoá được vì list rỗng là falsy.
    """

    def __init__(self, base_url=None, api_key=None, model_name=None):
        self.model_name = model_name or JUDGE_MODEL_NAME
        self._reasoning_effort = JUDGE_REASONING_EFFORT
        self.client = LLMClient(
            base_url=base_url or JUDGE_LLM_BASE_URL,
            api_key=api_key or JUDGE_LLM_API_KEY,
            model_name=self.model_name,
        )

    def health_check(self) -> bool:
        return self.client.health_check()

    def _chat_raw(self, question: str) -> str:
        """
        Gọi thẳng OpenAI client thay vì `LLMClient.chat()`.

        Lý do: cần truyền `reasoning_effort` qua `extra_body`, mà `chat()` là
        file của Vinh, không được sửa. Retry vẫn có — `LLMClient.__init__` đã
        dựng sẵn client, ta chỉ mượn lại đối tượng đó.
        """
        extra_body = None
        if self._reasoning_effort:
            extra_body = {"reasoning_effort": self._reasoning_effort}

        try:
            response = self.client.client.chat.completions.create(
                model=self.model_name,
                messages=build_judge_messages(question),
                temperature=JUDGE_TEMPERATURE,
                max_tokens=JUDGE_MAX_TOKENS,
                extra_body=extra_body,
            )
        except openai.BadRequestError:
            # Server không nhận `reasoning_effort` (judge không phải reasoning
            # model, hoặc backend cũ). Tắt hẳn rồi thử lại — chỉ báo một lần.
            if not self._reasoning_effort:
                raise
            logger.warning(
                f"Server từ chối reasoning_effort={self._reasoning_effort!r}, "
                f"bỏ tham số này. Nếu judge là reasoning model, nhớ đặt "
                f"JUDGE_MAX_TOKENS đủ lớn (>= 2048)."
            )
            self._reasoning_effort = ""
            response = self.client.client.chat.completions.create(
                model=self.model_name,
                messages=build_judge_messages(question),
                temperature=JUDGE_TEMPERATURE,
                max_tokens=JUDGE_MAX_TOKENS,
            )

        choice = response.choices[0]
        # Suy luận ăn hết ngân sách token thì `content` rỗng — nói rõ nguyên
        # nhân ngay tại đây, đừng để nó chìm thành "không parse được nhãn".
        if choice.finish_reason == "length" and not (choice.message.content or "").strip():
            logger.warning(
                f"Judge bị cắt do hết token (max_tokens={JUDGE_MAX_TOKENS}) trước khi "
                f"kịp ghi JSON. Đặt JUDGE_REASONING_EFFORT=none hoặc tăng JUDGE_MAX_TOKENS."
            )
        return choice.message.content or ""

    def judge_one(self, question: str) -> dict:
        """Chấm MỘT câu hỏi. Trả về dict như `parse_judge_response`."""
        try:
            response = self._chat_raw(question)
        except Exception as e:
            logger.warning(f"Judge lỗi khi chấm câu hỏi: {e}")
            return {"label": None, "reason": f"judge_error: {e}", "axes": {}}

        result = parse_judge_response(response)
        if result["label"] is None:
            logger.debug(f"Không parse được output judge: {truncate_text(response, 200)}")
        return result


def _load_cache(cache_path) -> dict:
    """Đọc cache judge đã có → {item_id: kết quả}."""
    if cache_path is None:
        return {}
    cache = {}
    n_skipped = 0
    for record in load_jsonl(cache_path):
        item_id = record.get("item_id")
        if not item_id:
            continue
        # KHÔNG nhận cache của lần chấm THẤT BẠI. Nếu nhận, một lần chạy hỏng
        # (judge timeout, JUDGE_MAX_TOKENS quá nhỏ với reasoning model...) sẽ
        # đóng băng vĩnh viễn: mọi lần chạy sau đọc `None` từ cache rồi bỏ qua,
        # không bao giờ gọi lại — sửa xong cấu hình cũng vô ích, mà không có
        # thông báo lỗi nào cho biết vì sao.
        if record.get("judge_label") is None:
            n_skipped += 1
            continue
        cache[item_id] = record
    if cache:
        logger.info(f"Judge cache: {len(cache)} câu đã chấm trước đó, sẽ bỏ qua")
    if n_skipped:
        logger.info(f"Judge cache: {n_skipped} câu hỏng ở lần trước, sẽ chấm lại")
    return cache


def judge_batch(
    items: list[QAItem],
    judge: "JudgeClient | None" = None,
    cache_path=None,
) -> list[QAItem]:
    """
    Chấm nhãn judge cho danh sách QAItem, gán tại chỗ.

    "batch" ở đây chỉ nghĩa là duyệt qua một danh sách — MỖI CÂU VẪN LÀ MỘT
    LƯỢT GỌI RIÊNG, cố ý không gộp prompt (xem docstring đầu file).

    Args:
        items: danh sách QAItem cần chấm.
        judge: JudgeClient; None thì tự khởi tạo từ config.
        cache_path: file JSONL lưu kết quả từng câu. Có cache thì chạy lại
            script không phải trả tiền API lần hai cho câu đã chấm.
    """
    judge = judge or JudgeClient()
    cache = _load_cache(cache_path)

    n_cached = 0
    n_called = 0
    n_failed = 0

    for item in tqdm(items, desc="LLM judge"):
        cached = cache.get(item.item_id)
        if cached is not None:
            result = {
                "label": Specificity.parse(cached.get("judge_label")),
                "reason": cached.get("judge_reason", ""),
                "axes": cached.get("judge_axes") or {},
            }
            n_cached += 1
        else:
            result = judge.judge_one(item.question)
            n_called += 1
            if cache_path is not None:
                append_jsonl(
                    {
                        "item_id": item.item_id,
                        "judge_label": result["label"].value if result["label"] else None,
                        "judge_reason": result["reason"],
                        "judge_axes": result["axes"],
                        "judge_model": judge.model_name,
                    },
                    cache_path,
                )

        item.judge_label = result["label"]
        item.judge_reason = result["reason"]
        item.judge_axes = result["axes"]
        if result["label"] is None:
            n_failed += 1

    logger.info(
        f"Judge xong: {n_called} lượt gọi mới, {n_cached} lấy từ cache, "
        f"{n_failed} không parse được nhãn"
    )
    if n_failed and n_failed / max(len(items), 1) > 0.1:
        logger.warning(
            f"{n_failed}/{len(items)} câu judge không trả về nhãn hợp lệ (>10%). "
            f"Nghi can số 1: JUDGE_MAX_TOKENS quá nhỏ. Với REASONING MODEL "
            f"(Gemma-4, Qwen3, DeepSeek-R1...), token bị kênh suy luận tiêu hết "
            f"trước khi model kịp ghi JSON — server trả finish_reason='length' và "
            f"`content` RỖNG, nhìn log chỉ thấy 'không parse được' nên rất dễ đổ oan "
            f"cho prompt. Đo thực tế Gemma-4-12b cần ~675 token suy luận; "
            f"JUDGE_MAX_TOKENS đang là {JUDGE_MAX_TOKENS}. Nếu tỷ lệ hỏng gần 100% "
            f"thì gần như chắc chắn là nguyên nhân này. "
            f"Nghi can số 2: model không tuân định dạng JSON."
        )

    return items
