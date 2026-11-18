"""
C4 — Sửa câu trả lời một lần khi verifier phát hiện trích dẫn KHÔNG HỢP LỆ.

Chỉ kích hoạt với trạng thái "invalid" (Điều không tồn tại, hết hiệu lực, nội dung
không khớp). "unverifiable" không kích hoạt: văn bản ngoài corpus chưa chắc là sai.

Không sửa generator.py: dựng messages riêng, KHÔNG kèm conversation history của
generator (history là dùng chung giữa các request — đưa vào sẽ lẫn ngữ cảnh), và
gọi thẳng client mà generator đã khởi tạo.
"""

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from loguru import logger

from src.retrieval.generator import CONTEXT_TEMPLATE, SYSTEM_PROMPT, find_loop_cut
from src.verification.verifier import REASON_TEXT, CitationResult, VerificationReport

FEEDBACK_TEMPLATE = """Hệ thống kiểm chứng phát hiện các trích dẫn sau trong câu trả lời trên KHÔNG hợp lệ:
{problems}

Các Điều có trong [CONTEXT] (chỉ được trích dẫn các Điều này):
{sources}

Hãy viết lại TOÀN BỘ câu trả lời:
- Sửa hoặc bỏ các trích dẫn không hợp lệ ở trên; ghi đúng số Điều và số hiệu văn bản như trong [CONTEXT].
- Nhận định nào không có căn cứ trong [CONTEXT] thì bỏ, không thay bằng điều luật khác ngoài [CONTEXT].
- Giữ cách trình bày như câu trả lời trước. Không nhắc tới việc kiểm chứng."""


@dataclass
class RepairOutcome:
    attempted: bool = False
    accepted: bool = False
    invalid_before: int = 0
    invalid_after: Optional[int] = None
    note: Optional[str] = None


def _label(r: CitationResult) -> str:
    doc = " ".join(x for x in (r.loai, r.so_hieu) if x) or "không rõ văn bản"
    return f'"{r.text}" ({doc})'


def build_feedback(report: VerificationReport, chunks: Sequence[dict]) -> str:
    seen, problems = set(), []
    for r in report.citations:
        if r.status != "invalid":
            continue
        key = (r.doc_id, r.dieu, r.khoan)
        if key in seen:
            continue
        seen.add(key)
        why = "; ".join(REASON_TEXT.get(x, x) for x in r.reasons
                        if x in ("dieu_out_of_range", "khoan_not_found", "expired",
                                 "content_mismatch", "quote_mismatch"))
        problems.append(f"- {_label(r)}: {why or 'không hợp lệ'}")
    sources = []
    for i, ch in enumerate(chunks, start=1):
        meta = ch.get("metadata") if isinstance(ch.get("metadata"), dict) else {}
        so = meta.get("so_hieu") or ch.get("doc_id", "")
        loai = meta.get("loai_van_ban", "")
        if ch.get("dieu"):
            sources.append(f"- [{i}] {loai} {so} — Điều {ch['dieu']}".replace("  ", " "))
    return FEEDBACK_TEMPLATE.format(problems="\n".join(problems),
                                    sources="\n".join(sources) or "(không có)")


def _call_llm(generator: Any, query: str, chunks: Sequence[dict], answer: str,
              feedback: str) -> Optional[str]:
    from src.retrieval.generator import MAX_CONTEXT_CHUNKS
    chunks = list(chunks)[:MAX_CONTEXT_CHUNKS]
    user_content = CONTEXT_TEMPLATE.format(chunks=generator._build_context(chunks), query=query)

    if getattr(generator, "_backend", "lmstudio") == "gemini":
        prompt = f"{user_content}\n\n[CÂU TRẢ LỜI TRƯỚC]\n{answer}\n\n[YÊU CẦU SỬA]\n{feedback}"
        resp = generator._gemini_client.models.generate_content(
            model=generator._gemini_model_name, contents=prompt, config=generator._gemini_config)
        text = (resp.text or "").strip() if resp else ""
    else:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": answer},
            {"role": "user", "content": feedback},
        ]
        resp = generator.client.chat.completions.create(
            model=generator.model, messages=messages,
            temperature=generator.temperature, max_tokens=generator.max_tokens)
        text = (resp.choices[0].message.content or "").strip() if resp.choices else ""
    if text:
        cut = find_loop_cut(text)
        text = text[:cut].strip() if cut is not None else text
    return text or None


def repair_answer(verifier: Any, generator: Any, query: str, answer: str,
                  chunks: Sequence[dict], report: VerificationReport
                  ) -> tuple[str, VerificationReport, RepairOutcome]:
    """
    Trả về (câu trả lời cuối, báo cáo của câu trả lời cuối, kết quả sửa).
    Chỉ nhận bản sửa khi số trích dẫn không hợp lệ GIẢM và bản sửa không phải là bỏ
    sạch trích dẫn (bỏ hết trích dẫn thì 0 lỗi nhưng mất căn cứ — không phải sửa).
    """
    out = RepairOutcome(invalid_before=report.n_invalid)
    if report.n_invalid == 0:
        return answer, report, out
    out.attempted = True
    try:
        new = _call_llm(generator, query, chunks, answer, build_feedback(report, chunks))
    except Exception as e:
        out.note = f"llm_error: {type(e).__name__}"
        logger.warning(f"Stage 6 repair: gọi LLM lỗi: {e}")
        return answer, report, out
    if not new:
        out.note = "empty_response"
        return answer, report, out

    new_report = verifier.verify(new, chunks)
    out.invalid_after = new_report.n_invalid
    # Bản sửa phải còn ít nhất một trích dẫn không sai. Nếu không, giữ bản gốc kèm cờ
    # lỗi cho người dùng thấy — câu trả lời không căn cứ không phải là "đã sửa".
    new_ok = new_report.counts["valid"] + new_report.counts["warning"]
    if new_report.n_invalid < report.n_invalid and new_ok >= 1:
        out.accepted = True
        return new, new_report, out
    out.note = "not_better"
    return answer, report, out
