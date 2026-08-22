"""
Prompt templates cho QA Specificity Pipeline (Phần 3).

Ba nhóm:
  (a) SYSTEM_PAIR_GENERATOR + USER_PAIR_GENERATOR  — sinh cặp broad/narrow
  (b) SYSTEM_SPECIFICITY_JUDGE + USER_SPECIFICITY_JUDGE — LLM judge
  (c) Few-shot examples dùng chung, trích từ docs/specificity-guideline.md §5

NGUYÊN TẮC: mọi tiêu chí trong file này phải bám sát
`docs/specificity-guideline.md`. Khi hai bên mâu thuẫn, GUIDELINE THẮNG —
sửa guideline trước, sửa prompt sau, và ghi vào bảng nhật ký §8 của guideline.
"""

# ══════════════════════════════════════════════════════════════════
# (c) FEW-SHOT EXAMPLES — nguồn: guideline §5
# ══════════════════════════════════════════════════════════════════

FEWSHOT_NARROW = [
    "Theo khoản 1 Điều 35 Bộ luật Lao động 2019, người lao động làm việc theo hợp đồng "
    "không xác định thời hạn phải báo trước bao nhiêu ngày khi đơn phương chấm dứt hợp đồng?",

    "Chị B ký hợp đồng lao động xác định thời hạn 24 tháng với công ty X. Sau 14 tháng, "
    "chị B nghỉ việc và chỉ báo trước 10 ngày. Công ty yêu cầu chị bồi thường. "
    "Yêu cầu này có căn cứ pháp lý không?",
]

FEWSHOT_BROAD = [
    "Người lao động có những quyền gì theo pháp luật lao động Việt Nam?",

    "Khi phát sinh tranh chấp hợp đồng dân sự, các bên có những phương thức giải quyết nào "
    "và ưu nhược điểm của từng phương thức ra sao?",
]

# Câu vùng xám — dùng để dạy model KHÔNG sinh ra loại này (guideline §5.3)
FEWSHOT_AMBIGUOUS = [
    "Hợp đồng lao động vô hiệu thì xử lý thế nào?",
]

# Tiêu chí 3 trục, viết gọn để nhúng vào cả hai prompt (guideline §3)
CRITERIA_BLOCK = """TIÊU CHÍ PHÂN LOẠI — chấm trên 3 trục độc lập:

Trục 1 — Mức chỉ định văn bản/điều khoản:
  → NARROW: nêu đích danh số điều/khoản/điểm ("Điều 35", "khoản 2 Điều 468 BLDS"),
            hoặc nêu tên văn bản kèm chế định cụ thể.
  → BROAD:  không nêu văn bản nào, hoặc chỉ nêu tên lĩnh vực ("theo luật lao động").

Trục 2 — Số lượng điều luật cần để trả lời đầy đủ:
  → NARROW: 1-2 điều là đủ; câu trả lời có dạng "theo Điều X thì...".
  → BROAD:  từ 3 điều trở lên, phải tổng hợp nhiều văn bản (luật + nghị định + thông tư),
            hoặc câu trả lời đúng là một DANH SÁCH nhiều mục.

Trục 3 — Mức chi tiết của tình huống:
  → NARROW: có tình huống với chủ thể, hành vi, mốc thời gian, con số cụ thể
            ("Anh A làm việc 3 năm, bị cho nghỉ không báo trước 45 ngày...").
  → BROAD:  câu hỏi khái niệm/định nghĩa/tổng quan, hoặc tình huống chung chung
            không đủ dữ kiện.

QUY TẮC TỔNG HỢP: >= 2/3 trục nghiêng narrow ⇒ narrow; ngược lại ⇒ broad.

NGOẠI LỆ CÓ QUYỀN PHỦ QUYẾT:
  - Nêu đích danh CẢ điều VÀ khoản cụ thể ⇒ luôn narrow, bất kể 2 trục còn lại.
  - Câu hỏi chứa từ 2 vấn đề pháp lý độc lập trở lên ⇒ luôn broad.

LƯU Ý QUAN TRỌNG: nhãn này KHÔNG phải "khó/dễ", KHÔNG phải "dài/ngắn".
Nó mô tả HÌNH DẠNG TẬP TÀI LIỆU cần truy xuất để trả lời."""


# ══════════════════════════════════════════════════════════════════
# (a) SINH CẶP CÂU HỎI ĐỐI CHỨNG
# ══════════════════════════════════════════════════════════════════

SYSTEM_PAIR_GENERATOR = """Bạn là chuyên gia pháp luật Việt Nam, chuyên xây dựng bộ dữ liệu đánh giá cho hệ thống tra cứu pháp lý.

NHIỆM VỤ: Từ MỘT văn bản pháp luật được cung cấp, sinh ra ĐÚNG MỘT CẶP câu hỏi đối chứng:
  - 1 câu BROAD (rộng)
  - 1 câu NARROW (hẹp)

RÀNG BUỘC THIẾT KẾ CẶP ĐỐI CHỨNG (quan trọng nhất):
Hai câu phải cùng CHỦ ĐỀ, cùng CHẾ ĐỊNH PHÁP LÝ, cùng bám vào nội dung văn bản đã cho.
Biến duy nhất được phép khác nhau giữa hai câu là ĐỘ CỤ THỂ. Nếu hai câu hỏi về hai
chủ đề khác nhau thì cặp đó VÔ GIÁ TRỊ và bị loại.

{criteria}

YÊU CẦU CHẤT LƯỢNG:
1. Cả hai câu phải trả lời được từ nội dung văn bản đã cho, KHÔNG bịa quy định.
2. Câu NARROW: hoặc trích đích danh điều/khoản, hoặc dựng tình huống đủ dữ kiện
   (chủ thể, mốc thời gian, con số). Dùng tên người Việt Nam (Anh A, Chị B, Công ty X).
3. Câu BROAD: hỏi tổng quan/liệt kê/so sánh, cần tổng hợp từ 3 điều luật trở lên.
4. TRÁNH câu vùng xám: câu ngắn không nêu điều luật, không có tình huống, mà lại
   không rõ cần bao nhiêu điều luật để trả lời (ví dụ SAI: "{ambiguous_example}").
5. Mỗi câu là MỘT câu hỏi hoàn chỉnh, tự đứng độc lập, không tham chiếu "văn bản trên".
6. Viết tiếng Việt tự nhiên như người dùng thật hỏi, KHÔNG dùng ngôn ngữ hàn lâm.

ĐỊNH DẠNG ĐẦU RA — BẮT BUỘC ĐÚNG 4 DÒNG, KHÔNG THÊM BẤT KỲ CHỮ NÀO KHÁC:
[BROAD]
<câu hỏi rộng>
[NARROW]
<câu hỏi hẹp>

KHÔNG giải thích. KHÔNG đánh số. KHÔNG dùng markdown. KHÔNG thêm lời dẫn."""


USER_PAIR_GENERATOR = """Lĩnh vực: {linh_vuc}
Ngành: {nganh}
Số hiệu văn bản: {so_hieu}

NỘI DUNG VĂN BẢN:
---
{content}
---

VÍ DỤ MẪU (chỉ để tham khảo văn phong, KHÔNG sao chép nội dung):
[BROAD]
{example_broad}
[NARROW]
{example_narrow}

Bây giờ hãy sinh cặp câu hỏi đối chứng từ NỘI DUNG VĂN BẢN ở trên.
Trả lời đúng định dạng 4 dòng."""


# Marker dùng cho parser — đổi ở đây thì parse_pair_response() tự bám theo
PAIR_MARKER_BROAD = "BROAD"
PAIR_MARKER_NARROW = "NARROW"


# ══════════════════════════════════════════════════════════════════
# (b) LLM JUDGE
# ══════════════════════════════════════════════════════════════════
# CỐ Ý không tiết lộ provenance (câu này sinh ở nhánh nào), không đưa
# văn bản gốc, không đưa câu còn lại trong cặp. Judge chỉ thấy đúng
# một câu hỏi trần → giữ tính độc lập của phép đánh giá.

SYSTEM_SPECIFICITY_JUDGE = """Bạn là chuyên gia phân loại truy vấn cho hệ thống tra cứu pháp luật Việt Nam.

NHIỆM VỤ: Đọc MỘT câu hỏi pháp lý và phân loại độ cụ thể của nó thành `narrow`, `broad`, hoặc `ambiguous`.

{criteria}

KHI NÀO TRẢ VỀ `ambiguous`:
Khi có ít nhất một trục KHÔNG chấm được vì câu hỏi không đủ thông tin để quyết.
Ví dụ: "{ambiguous_example}" — không rõ vô hiệu toàn bộ hay từng phần, nên
số điều luật cần dẫn khác nhau rõ rệt ⇒ ambiguous.
Trả về `ambiguous` là ĐÚNG QUY TRÌNH, không phải thất bại. Đừng ép nhãn khi phân vân.

ĐỊNH DẠNG ĐẦU RA — CHỈ một object JSON hợp lệ, không kèm markdown, không giải thích thêm:
{{"axis1": "narrow|broad", "axis2": "narrow|broad|unknown", "axis3": "narrow|broad", "label": "narrow|broad|ambiguous", "reason": "<tối đa 20 từ>"}}"""


USER_SPECIFICITY_JUDGE = """Câu hỏi cần phân loại:
---
{question}
---

Chấm 3 trục rồi kết luận. Trả về đúng một object JSON."""


# Few-shot cho judge: cặp (câu hỏi, JSON kỳ vọng). Nguồn: guideline §5.
JUDGE_FEWSHOT = [
    (
        FEWSHOT_NARROW[0],
        '{"axis1": "narrow", "axis2": "narrow", "axis3": "broad", "label": "narrow", '
        '"reason": "Nêu đích danh khoản 1 Điều 35, phủ quyết trục 1"}',
    ),
    (
        FEWSHOT_NARROW[1],
        '{"axis1": "broad", "axis2": "narrow", "axis3": "narrow", "label": "narrow", '
        '"reason": "Tình huống đủ dữ kiện, khoá vào khoảng 2 điều luật"}',
    ),
    (
        FEWSHOT_BROAD[0],
        '{"axis1": "broad", "axis2": "broad", "axis3": "broad", "label": "broad", '
        '"reason": "Hỏi liệt kê quyền, phải tổng hợp nhiều điều"}',
    ),
    (
        FEWSHOT_BROAD[1],
        '{"axis1": "broad", "axis2": "broad", "axis3": "broad", "label": "broad", '
        '"reason": "Nhiều phương thức, nhiều chế định, nhiều văn bản"}',
    ),
    (
        FEWSHOT_AMBIGUOUS[0],
        '{"axis1": "broad", "axis2": "unknown", "axis3": "broad", "label": "ambiguous", '
        '"reason": "Không rõ vô hiệu toàn bộ hay từng phần, trục 2 không chấm được"}',
    ),
]


def build_pair_generator_messages(
    content: str,
    linh_vuc: str = "",
    nganh: str = "",
    so_hieu: str = "",
) -> list[dict]:
    """Dựng messages hoàn chỉnh cho bước sinh cặp câu hỏi."""
    system = SYSTEM_PAIR_GENERATOR.format(
        criteria=CRITERIA_BLOCK,
        ambiguous_example=FEWSHOT_AMBIGUOUS[0],
    )
    user = USER_PAIR_GENERATOR.format(
        linh_vuc=linh_vuc or "Chưa xác định",
        nganh=nganh or "Chưa xác định",
        so_hieu=so_hieu or "Chưa xác định",
        content=content,
        example_broad=FEWSHOT_BROAD[0],
        example_narrow=FEWSHOT_NARROW[0],
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_judge_messages(question: str, use_fewshot: bool = True) -> list[dict]:
    """
    Dựng messages cho LLM judge — MỘT câu hỏi một lần gọi.

    Few-shot đưa vào dưới dạng lượt hội thoại giả (user/assistant) thay vì nhồi
    vào system prompt: model bám định dạng JSON tốt hơn rõ rệt.
    """
    system = SYSTEM_SPECIFICITY_JUDGE.format(
        criteria=CRITERIA_BLOCK,
        ambiguous_example=FEWSHOT_AMBIGUOUS[0],
    )
    messages: list[dict] = [{"role": "system", "content": system}]

    if use_fewshot:
        for example_q, example_json in JUDGE_FEWSHOT:
            messages.append(
                {"role": "user", "content": USER_SPECIFICITY_JUDGE.format(question=example_q)}
            )
            messages.append({"role": "assistant", "content": example_json})

    messages.append(
        {"role": "user", "content": USER_SPECIFICITY_JUDGE.format(question=question)}
    )
    return messages
