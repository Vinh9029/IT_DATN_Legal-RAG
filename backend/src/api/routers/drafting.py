"""
Trợ lý AI cho trang Soạn thảo văn bản.

Nhận trạng thái biểu mẫu (danh sách ô + giá trị hiện tại) cùng yêu cầu của người dùng,
trả về câu trả lời ngắn + danh sách ô cần sửa. Frontend tự áp các thay đổi vào biểu mẫu
và giữ giá trị cũ để người dùng hoàn tác.

Chỉ gọi LLM (LM Studio, cùng cấu hình với Generator) — KHÔNG dùng pipeline RAG, nên không
kéo theo việc nạp Qdrant/BM25/reranker.

Chống bịa thông tin: mọi chuỗi số (CCCD, số điện thoại, số tiền, số bản án, năm…) trong
giá trị AI đề xuất phải xuất hiện trong lời người dùng hoặc trong biểu mẫu; không thì bỏ.

Chống chữ vỡ: model nhỏ thỉnh thoảng sinh ký tự lạ giữa chữ Việt ("ĐƷiễn kôan") — đo được
~1/5 lượt với Llama 3.1 8B, có hay không ép json_schema đều bị. Gặp thì gọi lại một lần với
temperature 0; vẫn lỗi thì bỏ riêng những ô có chữ vỡ.
"""

import json
import os
import re
from difflib import SequenceMatcher
from datetime import date
from typing import Dict, List, Literal, Optional, Union

from fastapi import APIRouter, HTTPException
from loguru import logger
from openai import APIConnectionError, APIError, APITimeoutError, BadRequestError, OpenAI
from pydantic import BaseModel, Field

from config.settings import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME

router = APIRouter()

DRAFTING_MODEL = os.getenv("DRAFTING_LLM_MODEL") or LLM_MODEL_NAME
DRAFTING_TEMPERATURE = float(os.getenv("DRAFTING_TEMPERATURE", "0.1"))
DRAFTING_MAX_TOKENS = int(os.getenv("DRAFTING_MAX_TOKENS", "1500"))
DRAFTING_TIMEOUT = float(os.getenv("DRAFTING_TIMEOUT", "120"))

HISTORY_TURNS = 8
HINT_CHARS = 180
TURN_CHARS = 1500

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=DRAFTING_TIMEOUT, max_retries=0)
    return _client


# ── Schemas ──────────────────────────────────────────────────────────────────

FieldKind = Literal["text", "textarea", "list", "date", "money"]
FieldValue = Union[str, List[str]]


class FieldSpec(BaseModel):
    id: str = Field(max_length=80)
    label: str = Field(max_length=200)
    kind: FieldKind
    group: Optional[str] = Field(None, max_length=200)
    hint: Optional[str] = Field(None, max_length=2000)
    required: bool = False


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AssistRequest(BaseModel):
    template_title: str = Field(max_length=200)
    fields: List[FieldSpec] = Field(max_length=200)
    values: Dict[str, FieldValue] = {}
    history: List[ChatTurn] = Field(default=[], max_length=50)
    message: str = Field(min_length=1, max_length=4000)
    # Ô người dùng đang đứng — ưu tiên khi yêu cầu mơ hồ ("viết giúp mục này")
    focus_field: Optional[str] = Field(None, max_length=80)


class FieldEditOut(BaseModel):
    field: str
    value: FieldValue


class DroppedEdit(BaseModel):
    field: str
    reason: str


class AssistResponse(BaseModel):
    reply: str
    edits: List[FieldEditOut]
    dropped: List[DroppedEdit] = []
    model: str


class StatusResponse(BaseModel):
    available: bool
    model: str
    detail: Optional[str] = None


# ── Prompt ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Bạn là trợ lý soạn thảo văn bản pháp lý tiếng Việt, đặt cạnh một biểu mẫu mà người dùng đang điền.
Nhiệm vụ: đọc yêu cầu của người dùng rồi điền hoặc sửa các ô của biểu mẫu.

QUY TẮC BẮT BUỘC:
1. KHÔNG BỊA THÔNG TIN. Họ tên, ngày sinh, số CCCD, địa chỉ, số điện thoại, email, số tiền, số và ngày của bản án,
   tên Tòa án… chỉ được lấy từ lời người dùng hoặc từ giá trị đã có trong biểu mẫu. Thiếu thì KHÔNG điền ô đó,
   và hỏi lại người dùng trong "reply".
2. ĐIỀN ĐÚNG Ô. Các ô được chia theo nhóm (dòng "## …"); mỗi nhóm là một bên hoặc một phần của văn bản.
   Thông tin của ai thì điền vào ô thuộc nhóm của người đó. Người dùng xưng "tôi" là người làm đơn / bên lập văn bản.
   Danh sách giấy tờ, tài liệu kèm theo chỉ điền vào ô tài liệu; không trộn sang ô khác.
3. Ô ĐÃ CÓ GIÁ TRỊ: chỉ sửa khi người dùng yêu cầu sửa đúng nội dung đó. Không ghi đè thông tin của bên này bằng bên khác.
4. Ô nội dung tự do (lý do, yêu cầu, mục đích, phạm vi…): viết lại tình tiết người dùng kể thành văn phong
   pháp lý trang trọng, mạch lạc, dùng HẾT các chi tiết liên quan người dùng đã nêu (tài sản, số tiền, giá,
   thời hạn, ngày tháng, giấy tờ…) — không chép nguyên lời kể, không thêm tình tiết mới.
   Ô yêu cầu gửi Tòa án: mỗi yêu cầu bắt đầu bằng động từ (Buộc…, Tuyên bố…, Hủy…) và nêu rõ đối tượng, số tiền.
5. Họ tên ghi đúng họ và tên, không kèm danh xưng (ông, bà, anh, chị…).
6. Định dạng giá trị theo kiểu ô:
   - text: một dòng, không xuống dòng.
   - textarea: đoạn văn, có thể nhiều dòng (ngăn bằng \\n).
   - list: MẢNG chuỗi, mỗi phần tử là một mục, KHÔNG tự đánh số "1.", "2.".
   - date: dạng YYYY-MM-DD.
   - money: chỉ chữ số, không dấu chấm, không chữ "đồng" (ví dụ "50000000").
7. Không ghi lại các số chú thích (1), (2)… của mẫu. Không ghi nhãn ô vào giá trị (ví dụ ô "Người khởi kiện"
   chỉ ghi "Nguyễn Văn A", không ghi "Người khởi kiện: Nguyễn Văn A").
8. "reply" viết tiếng Việt, 1–4 câu, xưng "tôi", gọi ô bằng TÊN ô (không dùng id), nói đã điền gì và còn thiếu
   thông tin gì. Không dùng Markdown, không chép lại toàn bộ nội dung đã điền.
9. Nếu người dùng chỉ hỏi (không yêu cầu sửa), trả lời trong "reply" và để "edits" rỗng.
10. Chưa có thông tin thì BỎ ô đó khỏi "edits" — không điền giá trị giữ chỗ như "...", "chưa rõ", "(trống)".

CÁCH LÀM (đúng thứ tự các khoá JSON):
- "facts": liệt kê ngắn từng thông tin CỤ THỂ người dùng vừa đưa ra, kèm của ai (vd. "Bên nhận: Trần Thị Lan").
- "edits": mỗi fact cần điền → một ô phù hợp nhất. Ô nào chưa có fact thì KHÔNG đưa vào.
- "reply": viết SAU CÙNG, chỉ nói những ô thật sự có trong "edits" và thông tin còn thiếu.

CHỈ TRẢ VỀ JSON đúng dạng:
{"facts": ["…"], "edits": [{"field": "<id ô>", "value": "…"}], "reply": "…"}"""

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "draft_edits",
        "strict": True,
        "schema": {
            "type": "object",
            # Thứ tự khoá = thứ tự model sinh: rút sự kiện → gán ô → tóm tắt (reply viết sau nên khớp edits)
            "properties": {
                "facts": {"type": "array", "items": {"type": "string"}},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "value": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                        },
                        "required": ["field", "value"],
                    },
                },
                "reply": {"type": "string"},
            },
            "required": ["facts", "edits", "reply"],
        },
    },
}

KIND_LABEL = {"text": "một dòng", "textarea": "đoạn văn", "list": "danh sách", "date": "ngày", "money": "số tiền"}


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _field_line(f: FieldSpec, req: AssistRequest) -> str:
    value = req.values.get(f.id)
    shown = json.dumps(value, ensure_ascii=False) if value not in (None, "", []) else "(trống)"
    flags = KIND_LABEL[f.kind] + (", bắt buộc" if f.required else "")
    hint = f" | {_short(f.hint, HINT_CHARS)}" if f.hint else ""
    return f"- {f.id} | {f.label} | {flags} | {shown}{hint}"


def _form_context(req: AssistRequest) -> str:
    lines = [f"Biểu mẫu: {req.template_title}", f"Hôm nay: {date.today().isoformat()}", "", "Các ô (id | tên | kiểu | giá trị hiện tại | hướng dẫn):"]
    # Gom theo nhóm, giữ thứ tự xuất hiện — nhóm cho model biết ô nào thuộc bên nào
    current_group = object()
    for f in req.fields:
        if f.group != current_group:
            current_group = f.group
            if f.group:
                lines.append(f"## {f.group}")
        lines.append(_field_line(f, req))
    if req.focus_field:
        focus = next((f for f in req.fields if f.id == req.focus_field), None)
        if focus:
            lines += ["", f"Người dùng đang đặt con trỏ ở ô: {focus.id} ({focus.label}). Yêu cầu mơ hồ thì hiểu là cho ô này."]
    return "\n".join(lines)


def _build_messages(req: AssistRequest) -> List[Dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "system", "content": _form_context(req)}]
    for turn in req.history[-HISTORY_TURNS:]:
        messages.append({"role": turn.role, "content": _short(turn.content, TURN_CHARS)})
    messages.append({"role": "user", "content": req.message})
    return messages


# ── Đọc & kiểm tra kết quả của LLM ──────────────────────────────────────────


def _parse_json(text: str) -> dict:
    text = text.strip()
    # Model không hỗ trợ structured output đôi khi bọc trong ```json … ```
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Không có JSON trong câu trả lời")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON không phải object")
    return data


NUMBERING = re.compile(r"^\s*(?:\d{1,2}[.)]|[-•*])\s+")
NOTE_MARK = re.compile(r"\s*\(\d{1,2}\)\s*")
DMY = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
DIGIT_RUN = re.compile(r"\d{3,}")


PLACEHOLDER = re.compile(r"^[\s.…_\-–—?]*$|^\(?\s*(trống|chưa rõ|chưa có|không rõ|n/?a|null|none|xxx+)\s*\)?$", re.I)


def _is_placeholder(value: FieldValue) -> bool:
    """Model nhỏ hay điền "..." / "chưa rõ" thay vì bỏ trống ô"""
    items = value if isinstance(value, list) else [value]
    return all(PLACEHOLDER.match(str(v).strip()) for v in items)


# "Chị Trần Thị Lan" → "Trần Thị Lan": chỉ bỏ khi phía sau là họ tên (≥ 2 từ viết hoa)
HONORIFIC = re.compile(r"^(?:ông|bà|anh|chị|em|cô|chú|bác|cậu|dì|ngài)\s+(?=[A-ZĐÀ-Ỹ][^\s]*\s+[A-ZĐÀ-Ỹ])", re.I)


def _coerce(kind: str, value) -> Optional[FieldValue]:
    """Ép giá trị về đúng kiểu ô; None nếu không ép được"""
    if kind == "list":
        items = value if isinstance(value, list) else str(value).split("\n")
        cleaned = [NUMBERING.sub("", str(v)).strip() for v in items]
        return [v for v in cleaned if v]
    text = "\n".join(map(str, value)) if isinstance(value, list) else str(value)
    text = NOTE_MARK.sub(" ", text).strip()
    if kind == "text":
        return HONORIFIC.sub("", " ".join(text.split()))
    if kind == "textarea":
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if kind == "date":
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            try:
                return date.fromisoformat(text).isoformat()
            except ValueError:
                return None
        m = DMY.match(text)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
            except ValueError:
                return None
        return None
    if kind == "money":
        digits = re.sub(r"\D", "", text).lstrip("0")
        return digits or None
    return text


def _same(a, b) -> bool:
    norm = lambda v: [x for x in v] if isinstance(v, list) else ([] if v in (None, "") else v)
    return norm(a) == norm(b)


def _known_digits(req: AssistRequest) -> str:
    """Mọi chữ số người dùng đã cung cấp (lời nói + giá trị trong biểu mẫu), nối liền để tra chuỗi con"""
    parts = [req.message] + [t.content for t in req.history if t.role == "user"]
    for v in req.values.values():
        parts.extend(v if isinstance(v, list) else [v])
    parts.append(date.today().isoformat())
    # Bỏ dấu phân cách hàng nghìn: "50.000.000" và "50000000" coi như một
    return " ".join(re.sub(r"(?<=\d)[.,\s](?=\d{3}\b)", "", p) for p in parts)


def _significant(digits: str) -> str:
    """Phần số có nghĩa: bỏ số 0 ở đuôi — "50" (triệu) và "50000000" cùng là 5"""
    return digits.rstrip("0") or "0"


def _known_cores(known: str) -> set:
    # "2,1 tỷ" → "21": bỏ dấu thập phân giữa các chữ số rồi mới tách
    runs = re.findall(r"\d+", re.sub(r"(?<=\d)[.,](?=\d)", "", known))
    return {_significant(r) for r in runs}


def _invented_number(kind: str, value: FieldValue, known: str) -> Optional[str]:
    """Chuỗi số đầu tiên trong `value` mà người dùng chưa từng đưa ra; None nếu không có"""
    cores = _known_cores(known)
    if kind == "date":
        year = str(value)[:4]
        return None if year in known else year
    if kind == "money":
        return None if _significant(str(value)) in cores else str(value)
    texts = value if isinstance(value, list) else [value]
    for t in texts:
        for run in DIGIT_RUN.findall(re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", t)):
            # Số viết đầy đủ ("2100000000") của số người dùng nói gọn ("2,1 tỷ") vẫn hợp lệ
            if run not in known and _significant(run) not in cores:
                return run
    return None


_VI_LETTERS = "aàáảãạăằắẳẵặâầấẩẫậbcdđeèéẻẽẹêềếểễệfghiìíỉĩịjklmnoòóỏõọôồốổỗộơờớởỡợpqrstuùúủũụưừứửữựvwxyỳýỷỹỵz"
_ALLOWED_CHARS = set(_VI_LETTERS + _VI_LETTERS.upper() + "0123456789" + " \n\t.,;:!?()\"'-–—/%&+*=#@…_\u00a0")


def _garbled(value: FieldValue, known: str) -> bool:
    """Có ký tự ngoài bảng chữ Việt mà người dùng cũng chưa từng gõ"""
    text = "".join(value) if isinstance(value, list) else value
    return any(c not in _ALLOWED_CHARS and c not in known for c in text)


CAPITALIZED = re.compile(r"\b[^\W\d_][\w]*", re.U)


def _unknown_proper_noun(value: str, known_lower: str) -> Optional[str]:
    """
    Ô một dòng (họ tên, địa chỉ, tên Tòa án…): từ viết hoa nào cũng phải có trong lời người dùng.
    Bắt được cả tên bịa lẫn chữ vỡ mà vẫn đúng bảng chữ ("Trần" → "Tràn").
    """
    for word in CAPITALIZED.findall(value):
        if word[0].isupper() and word.lower() not in known_lower:
            return word
    return None


GARBLED_REASON = "Trợ lý trả về chữ bị lỗi, bạn thử hỏi lại"


def _known_text(req: AssistRequest) -> str:
    """Mọi chữ người dùng đã đưa ra: lời nhắn + giá trị trong biểu mẫu (không tính lời của AI)"""
    parts = [req.message, *(t.content for t in req.history if t.role == "user")]
    parts += [json.dumps(v, ensure_ascii=False) for v in req.values.values()]
    return " ".join(parts)


def _validate(req: AssistRequest, raw_edits) -> tuple[List[FieldEditOut], List[DroppedEdit]]:
    fields = {f.id: f for f in req.fields}
    known = _known_digits(req)
    known_text = _known_text(req)
    known_lower = known_text.lower()
    edits: List[FieldEditOut] = []
    dropped: List[DroppedEdit] = []
    seen = set()
    for item in raw_edits if isinstance(raw_edits, list) else []:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("field", "")).strip()
        spec = fields.get(fid)
        if spec is None:
            if fid:
                dropped.append(DroppedEdit(field=fid, reason="Ô không có trong biểu mẫu"))
            continue
        if fid in seen:
            continue
        value = _coerce(spec.kind, item.get("value", ""))
        if value is not None and value not in ("", []) and _is_placeholder(value):
            continue
        if value is None:
            dropped.append(DroppedEdit(field=fid, reason="Giá trị không đúng định dạng của ô"))
            continue
        if _same(value, req.values.get(fid)):
            continue
        if _garbled(value, known_text):
            dropped.append(DroppedEdit(field=fid, reason=GARBLED_REASON))
            continue
        invented = _invented_number(spec.kind, value, known) if value not in ("", []) else None
        if invented:
            dropped.append(DroppedEdit(field=fid, reason=f"Có số liệu \"{invented}\" không thấy trong thông tin bạn cung cấp"))
            continue
        noun = _unknown_proper_noun(value, known_lower) if spec.kind == "text" else None
        if noun:
            dropped.append(DroppedEdit(field=fid, reason=f"Có tên \"{noun}\" không thấy trong thông tin bạn cung cấp"))
            continue
        seen.add(fid)
        edits.append(FieldEditOut(field=fid, value=value))
    return edits, dropped


# ── Endpoints ────────────────────────────────────────────────────────────────


def _echoes(reply: str, message: str) -> bool:
    """Model nhỏ đôi khi trả lời bằng cách chép lại nguyên lời người dùng"""
    return SequenceMatcher(None, reply.lower(), message.lower()).ratio() > 0.6


def _clean_reply(req: AssistRequest, reply: str) -> str:
    """Thay id ô lọt vào câu trả lời (nkc_dia_chi) bằng tên ô người dùng nhìn thấy"""
    for f in sorted(req.fields, key=lambda x: -len(x.id)):
        reply = re.sub(rf"(?<![\w]){re.escape(f.id)}(?![\w])", f"“{f.label}”", reply)
    return reply.replace("ô “", "“")


def _fallback_reply(req: AssistRequest, edits: List[FieldEditOut]) -> str:
    labels = {f.id: f.label for f in req.fields}
    if not edits:
        return "Tôi chưa điền được ô nào từ thông tin này. Bạn cho biết thêm chi tiết nhé."
    return "Tôi đã điền: " + ", ".join(labels.get(e.field, e.field) for e in edits) + "."


def _complete(client: OpenAI, base: dict) -> tuple[Optional[dict], str]:
    """Gọi LLM, trả (JSON đã đọc hoặc None, nội dung thô)"""
    try:
        completion = client.chat.completions.create(**base, response_format=RESPONSE_SCHEMA)
    except BadRequestError as e:
        # Bản LM Studio/model không hỗ trợ json_schema → gọi lại không ràng buộc, tự tách JSON
        logger.warning(f"Drafting: structured output bị từ chối ({e}); thử lại không ràng buộc")
        completion = client.chat.completions.create(**base)
    content = (completion.choices[0].message.content or "").strip()
    try:
        return _parse_json(content), content
    except (ValueError, json.JSONDecodeError):
        return None, content


def _has_garbled(req: AssistRequest, data: dict) -> bool:
    known = _known_text(req)
    texts = [str(data.get("reply", ""))]
    for item in data.get("edits") or []:
        if isinstance(item, dict):
            v = item.get("value", "")
            texts.extend(map(str, v) if isinstance(v, list) else [str(v)])
    return any(_garbled(t, known) for t in texts)


@router.get("/drafting/status", response_model=StatusResponse)
def drafting_status():
    """Kiểm tra nhanh LLM có đang chạy không — frontend dùng để bật/tắt khung trợ lý"""
    try:
        client = _get_client().with_options(timeout=3.0)
        models = [m.id for m in client.models.list().data]
        return StatusResponse(available=True, model=DRAFTING_MODEL, detail=None if DRAFTING_MODEL in models else "Model chưa được nạp, LM Studio sẽ tự nạp ở lần gọi đầu")
    except Exception as e:  # noqa: BLE001 — mọi lỗi đều nghĩa là "chưa dùng được"
        return StatusResponse(available=False, model=DRAFTING_MODEL, detail=type(e).__name__)


@router.post("/drafting/assist", response_model=AssistResponse)
def drafting_assist(req: AssistRequest):
    messages = _build_messages(req)
    client = _get_client()
    base = dict(model=DRAFTING_MODEL, messages=messages, temperature=DRAFTING_TEMPERATURE, max_tokens=DRAFTING_MAX_TOKENS)

    try:
        data, content = _complete(client, base)
        edits, dropped = _validate(req, data.get("edits")) if data is not None else ([], [])
        # Chữ vỡ / tên lạ → gọi lại một lần, lần này không ngẫu nhiên; giữ lượt ít ô bị loại hơn
        suspicious = lambda d: any(x.reason == GARBLED_REASON or x.reason.startswith("Có tên") for x in d)
        if data is not None and (_has_garbled(req, data) or suspicious(dropped)):
            logger.warning("Drafting: kết quả có chữ vỡ/tên lạ, gọi lại với temperature 0")
            data2, content2 = _complete(client, {**base, "temperature": 0.0})
            if data2 is not None:
                edits2, dropped2 = _validate(req, data2.get("edits"))
                if len(dropped2) <= len(dropped):
                    data, content, edits, dropped = data2, content2, edits2, dropped2
    except (APIConnectionError, APITimeoutError) as e:
        logger.error(f"Drafting: không kết nối được LLM ({LLM_BASE_URL}): {e}")
        raise HTTPException(status_code=503, detail="Trợ lý AI chưa sẵn sàng (LM Studio chưa chạy hoặc quá thời gian chờ).")
    except APIError as e:
        logger.error(f"Drafting: LLM lỗi: {e}")
        raise HTTPException(status_code=502, detail=f"LLM báo lỗi: {e}")

    if not content:
        raise HTTPException(status_code=502, detail="LLM không trả về nội dung (model suy luận có thể đã dùng hết token).")
    if data is None:
        # Không ra JSON: vẫn trả lời người dùng, chỉ là không sửa ô nào
        logger.warning(f"Drafting: không đọc được JSON, trả nguyên văn | {content[:200]!r}")
        return AssistResponse(reply=_short(content, 1500), edits=[], dropped=[], model=DRAFTING_MODEL)

    reply = _clean_reply(req, str(data.get("reply") or "").strip())
    if not reply or _invented_number("text", reply, _known_digits(req)) or _garbled(reply, _known_text(req)) or _echoes(reply, req.message):
        reply = _fallback_reply(req, edits)
    logger.info(f"Drafting: {req.template_title} | {len(edits)} ô sửa, {len(dropped)} ô bị loại")
    return AssistResponse(reply=reply, edits=edits, dropped=dropped, model=DRAFTING_MODEL)
