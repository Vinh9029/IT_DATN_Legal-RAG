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
    "Theo khoản 1 Điều 623 Bộ luật Dân sự 2015, thời hiệu để người thừa kế yêu cầu "
    "chia di sản là bất động sản là bao nhiêu năm?",

    "Ông A mất năm 2019, không để lại di chúc. Đến năm 2026, người con riêng của ông "
    "mới yêu cầu chia căn nhà mà ông đứng tên chung với vợ, hai người con chung phản "
    "đối vì cho rằng đã quá hạn. Yêu cầu chia di sản này có được chấp nhận không?",
]

FEWSHOT_BROAD = [
    "Người thừa kế có những quyền và nghĩa vụ gì theo pháp luật dân sự Việt Nam?",

    "Khi phát sinh tranh chấp hợp đồng dân sự, các bên có những phương thức giải quyết nào "
    "và ưu nhược điểm của từng phương thức ra sao?",
]

# Câu vùng xám — dùng để dạy model KHÔNG sinh ra loại này (guideline §5.3)
FEWSHOT_AMBIGUOUS = [
    "Giao dịch dân sự vô hiệu thì xử lý thế nào?",
]

# ══════════════════════════════════════════════════════════════════
# HAI KIỂU SINH CÂU NARROW — chống shortcut learning
# ══════════════════════════════════════════════════════════════════
# Guideline §3 công nhận HAI đường trở thành narrow: trục 1 (trích đích danh
# điều/khoản) và trục 3 (tình huống đủ dữ kiện). Cả hai đều là narrow THẬT,
# định nghĩa nhãn không có gì sai.
#
# Vấn đề nằm ở PHÂN BỐ DỮ LIỆU, không nằm ở định nghĩa. Bản đầu luôn đưa
# FEWSHOT_NARROW[0] (kiểu trích dẫn) làm ví dụ, nên model bắt chước: đo trên
# 15 cặp mẫu thì 10 câu narrow chỉ khác câu broad ở mỗi tiền tố "Theo Điều X".
# Khi ấy P(narrow | có trích dẫn) ≈ 1.0 còn P(có trích dẫn | broad) ≈ 0, và
# classifier chỉ cần dò chuỗi "Theo Điều" là đạt accuracy cao — nó học ĐẶC
# ĐIỂM BỀ MẶT chứ không học độ cụ thể. Trên truy vấn thật của người dùng
# (phần lớn không trích điều khoản) thì sập.
#
# Cách sửa: luân phiên hai kiểu ~50/50 theo document (xem `generate_pair`).
# Trích dẫn vẫn còn trong dataset — người dùng thật CÓ trích điều khoản, bỏ
# hẳn sẽ tạo lỗ hổng bao phủ ngược lại — nhưng không còn dự đoán được nhãn
# một mình.
NARROW_MODE_SITUATION = "situation"
NARROW_MODE_CITATION = "citation"

# Ví dụ few-shot RIÊNG cho generator ở nhánh situation.
#
# Vì sao không dùng lại FEWSHOT_NARROW[1]: câu đó kết thúc bằng "Yêu cầu chia
# di sản này có được chấp nhận không?" — một câu hỏi MỞ. Model bắt chước đúng
# cái đuôi ấy, và đó là nguyên nhân đo được của 54,6% câu narrow kiểu tình
# huống bị judge loại (đo trên 2.224 câu, 2026-09-11): hỏi mở thì muốn trả lời
# đầy đủ phải quét điều kiện + hậu quả + thủ tục, tức là BROAD đội lốt.
#
# FEWSHOT_NARROW[1] vẫn giữ NGUYÊN vì `JUDGE_FEWSHOT` dùng chung nó. Sửa vào
# đó là đổi luôn hành vi judge, và mọi so sánh với 4.084 câu đã verified trước
# đó mất giá trị — đổi hai biến cùng lúc thì không quy được kết quả cho biến
# nào. Tách hằng số riêng là cách đổi ĐÚNG MỘT biến.
FEWSHOT_NARROW_SITUATION = (
    "Ông A mất năm 2019, không để lại di chúc. Đến năm 2026, người con riêng của ông "
    "mới yêu cầu chia căn nhà mà ông đứng tên chung với vợ. Thời hiệu để người con "
    "riêng yêu cầu chia di sản này còn lại bao lâu?"
)

NARROW_MODE_BLOCK = {
    NARROW_MODE_SITUATION: """2. Câu NARROW lần này phải hẹp bằng TÌNH HUỐNG CỤ THỂ (trục 3), KHÔNG bằng trích dẫn:
   - Dựng một tình huống có chủ thể, hành vi, mốc thời gian, con số cụ thể.
     Dùng tên người/công ty Việt Nam: Anh A, Chị B, Công ty X.
   - CẤM TUYỆT ĐỐI nhắc số điều, số khoản, số hiệu văn bản trong câu NARROW.
     Không được viết "Theo Điều 5...", "Theo Nghị định 100/2020/NĐ-CP...",
     "Căn cứ khoản 2...". Câu hỏi phải tự nhiên như người dân hỏi, người dân
     không thuộc số hiệu văn bản.
   - Tình huống phải đủ dữ kiện để áp thẳng quy định vào, không được chung chung.
   - CÂU HỎI CHỐT PHẢI NHẮM ĐÚNG MỘT HỆ QUẢ PHÁP LÝ XÁC ĐỊNH, nằm gọn trong
     văn bản đã cho và trả lời được bằng 1-2 điều luật: một mốc thời hiệu, một
     thời điểm, một điều kiện, một mức tiền/tỷ lệ, hoặc bên nào gánh nghĩa vụ.
       ĐÚNG: "...thì thời hiệu yêu cầu chia di sản còn lại bao lâu?"
             "...thì hợp đồng này có hiệu lực từ thời điểm nào?"
             "...thì bên nào phải chịu chi phí vận chuyển?"
       SAI : "...thì xử lý thế nào?"
             "...có hợp pháp không?"
             "...yêu cầu này có được chấp nhận không?"
             "...thì phải làm gì?"
     Mấy câu SAI nghe rất cụ thể nhưng để trả lời ĐẦY ĐỦ phải quét nhiều chế
     định cùng lúc (điều kiện có hiệu lực + hậu quả + thủ tục), nên chúng là
     câu BROAD đội lốt tình huống và sẽ bị loại ở khâu kiểm chứng.""",

    NARROW_MODE_CITATION: """2. Câu NARROW lần này phải hẹp bằng TRÍCH DẪN ĐÍCH DANH (trục 1):
   - Nêu rõ số điều (và khoản nếu có) của văn bản đã cho.
   - Sau phần trích dẫn phải là một câu hỏi thực sự về nội dung quy định đó,
     KHÔNG phải chép lại nội dung điều luật rồi chấm hết.""",
}


# Tiêu chí 3 trục, viết gọn để nhúng vào cả hai prompt (guideline §3)
CRITERIA_BLOCK = """TIÊU CHÍ PHÂN LOẠI — chấm trên 3 trục độc lập:

Trục 1 — Mức chỉ định văn bản/điều khoản:
  → NARROW: nêu đích danh số điều/khoản/điểm ("Điều 623", "khoản 2 Điều 468 BLDS"),
            hoặc nêu tên văn bản kèm chế định cụ thể.
  → BROAD:  không nêu văn bản nào, hoặc chỉ nêu tên lĩnh vực ("theo pháp luật dân sự").

Trục 2 — Số lượng điều luật cần để trả lời đầy đủ:
  → NARROW: 1-2 điều là đủ; câu trả lời có dạng "theo Điều X thì...".
  → BROAD:  từ 3 điều trở lên, phải tổng hợp nhiều văn bản (luật + nghị định + thông tư),
            hoặc câu trả lời đúng là một DANH SÁCH nhiều mục.

Trục 3 — Mức chi tiết của tình huống:
  → NARROW: có tình huống với chủ thể, hành vi, mốc thời gian, con số cụ thể
            ("Anh A vay của chị B 200 triệu, quá hạn 6 tháng chưa trả...").
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
{narrow_mode_block}
3. Câu BROAD: hỏi tổng quan/liệt kê/so sánh, cần tổng hợp từ 3 điều luật trở lên.
4. TRÁNH câu vùng xám: câu ngắn không nêu điều luật, không có tình huống, mà lại
   không rõ cần bao nhiêu điều luật để trả lời (ví dụ SAI: "{ambiguous_example}").
5. CẢ HAI DÒNG PHẢI LÀ CÂU HỎI, kết thúc bằng dấu "?". Đây là lỗi hay gặp nhất:
   chép lại nội dung điều luật thành câu khẳng định thì KHÔNG PHẢI câu hỏi và bị
   loại cả cặp. Ví dụ SAI: "Theo Điều 2 Nghị định 170-CP, Bộ Điện lực có nhiệm vụ
   trình Chính phủ xét duyệt quy hoạch phát triển ngành điện." — đó là câu trả lời.
   Cũng KHÔNG được nối hai mệnh đề bằng "Hoặc" để né việc phải hỏi.
6. Mỗi câu tự đứng độc lập, không tham chiếu "văn bản trên", "tài liệu đã cho".
7. Viết tiếng Việt tự nhiên như người dùng thật hỏi, KHÔNG dùng ngôn ngữ hàn lâm.

ĐỊNH DẠNG ĐẦU RA — BẮT BUỘC ĐÚNG 4 DÒNG, KHÔNG THÊM BẤT KỲ CHỮ NÀO KHÁC:
[BROAD]
<câu hỏi rộng>
[NARROW]
<câu hỏi hẹp>

KHÔNG giải thích. KHÔNG đánh số. KHÔNG dùng markdown. KHÔNG thêm lời dẫn."""


USER_PAIR_GENERATOR = """Lĩnh vực: {linh_vuc}
Ngành: {nganh}
Văn bản: {so_hieu}

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
        '"reason": "Nêu đích danh khoản 1 Điều 623, phủ quyết trục 1"}',
    ),
    (
        FEWSHOT_NARROW[1],
        '{"axis1": "broad", "axis2": "narrow", "axis3": "narrow", "label": "narrow", '
        '"reason": "Tình huống đủ dữ kiện, khoá vào khoảng 2 điều luật"}',
    ),
    (
        FEWSHOT_BROAD[0],
        '{"axis1": "broad", "axis2": "broad", "axis3": "broad", "label": "broad", '
        '"reason": "Hỏi liệt kê quyền và nghĩa vụ, phải tổng hợp nhiều điều"}',
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
    narrow_mode: str = NARROW_MODE_SITUATION,
) -> list[dict]:
    """
    Dựng messages hoàn chỉnh cho bước sinh cặp câu hỏi.

    Args:
        narrow_mode: `NARROW_MODE_SITUATION` (hẹp bằng tình huống) hoặc
            `NARROW_MODE_CITATION` (hẹp bằng trích dẫn điều/khoản). Caller
            luân phiên hai kiểu để chống shortcut learning — xem khối chú
            thích ở đầu file. Giá trị lạ thì raise thay vì âm thầm rơi về
            một kiểu: sinh lệch phân bố là lỗi không có thông báo.
    """
    if narrow_mode not in NARROW_MODE_BLOCK:
        raise ValueError(
            f"narrow_mode={narrow_mode!r} không hợp lệ, "
            f"phải là một trong {sorted(NARROW_MODE_BLOCK)}"
        )

    system = SYSTEM_PAIR_GENERATOR.format(
        criteria=CRITERIA_BLOCK,
        ambiguous_example=FEWSHOT_AMBIGUOUS[0],
        narrow_mode_block=NARROW_MODE_BLOCK[narrow_mode],
    )
    # Ví dụ few-shot phải KHỚP kiểu narrow đang yêu cầu — đưa ví dụ trích dẫn
    # rồi bảo model đừng trích dẫn thì model nghe theo ví dụ, không nghe lời dặn.
    example_narrow = (
        FEWSHOT_NARROW_SITUATION
        if narrow_mode == NARROW_MODE_SITUATION
        else FEWSHOT_NARROW[0]
    )
    user = USER_PAIR_GENERATOR.format(
        linh_vuc=linh_vuc or "Chưa xác định",
        nganh=nganh or "Chưa xác định",
        so_hieu=so_hieu or "Chưa xác định",
        content=content,
        example_broad=FEWSHOT_BROAD[0],
        example_narrow=example_narrow,
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
