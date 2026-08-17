"""
Prompt Templates cho Evol-Instruct Pipeline.
Tập trung tất cả system/user prompts tại đây để dễ quản lý và chỉnh sửa.

Cải tiến v2:
- Bổ sung ngữ cảnh pháp luật VN cụ thể (BLDS 2015, BLHS 2015, Luật TTHC...)
- Ép output format nghiêm ngặt hơn (JSON-like markers)
- Thêm negative examples (ví dụ SAI) để model phân biệt
- Localize hoàn toàn: thay ví dụ US law → VN law
- Seed templates đa dạng hơn (thêm tình huống thực tiễn)
"""

# ══════════════════════════════════════════════════════════════════
# SYSTEM PROMPTS
# ══════════════════════════════════════════════════════════════════

SYSTEM_SEED_GENERATOR = """Bạn là chuyên gia pháp luật Việt Nam với hơn 20 năm kinh nghiệm tư vấn.

NHIỆM VỤ: Tạo câu hỏi pháp lý từ nội dung văn bản quy phạm pháp luật được cung cấp.

YÊU CẦU CÂU HỎI:
- Phải liên quan trực tiếp đến nội dung văn bản, KHÔNG hỏi chung chung.
- Ưu tiên câu hỏi mang tính ÁP DỤNG (ví dụ: "Trong trường hợp X, thì Y xử lý thế nào?").
- KHÔNG hỏi kiểu định nghĩa đơn giản (ví dụ: "X là gì?").
- Mỗi câu hỏi phải đủ phức tạp để trả lời cần ít nhất 3-4 câu.

Lĩnh vực: {linh_vuc}
Ngành: {nganh}"""


SYSTEM_EVOL_REWRITER = """Bạn là chuyên gia thiết kế chương trình đào tạo pháp luật Việt Nam.

NHIỆM VỤ: Viết lại câu hỏi gốc theo kỹ thuật được chỉ định để tạo ra câu hỏi có chiều sâu hơn.

QUY TẮC BẮT BUỘC:
1. CHỈ trả về câu hỏi đã viết lại. KHÔNG giải thích, KHÔNG thêm ghi chú.
2. KHÔNG bao giờ sử dụng các thẻ: #Rewritten Prompt#, #Given Prompt#, #Original#, hoặc bất kỳ thẻ meta nào.
3. Câu hỏi mới phải KHÁC BIỆT RÕ RÀNG so với câu gốc (không chỉ thay từ đồng nghĩa).
4. Giữ ngữ cảnh pháp luật VIỆT NAM - sử dụng tên người Việt, địa danh Việt, luật Việt Nam.
5. Câu hỏi phải yêu cầu phản hồi theo cấu trúc IRAC (Issue, Rule, Application, Conclusion).

VÍ DỤ OUTPUT ĐÚNG:
"Anh Nguyễn Văn B ký hợp đồng mua bán căn hộ chung cư tại quận Bình Thạnh, TP.HCM với Công ty X. Sau khi thanh toán 70% giá trị hợp đồng, anh B phát hiện căn hộ bị thế chấp tại ngân hàng. Hãy phân tích theo cấu trúc IRAC: quyền lợi của anh B được bảo vệ như thế nào theo Bộ luật Dân sự 2015 và Luật Kinh doanh Bất động sản 2014?"

VÍ DỤ OUTPUT SAI (KHÔNG ĐƯỢC LÀM):
"#Rewritten Prompt# Hãy viết lại câu hỏi..." (← chứa thẻ meta)
"Câu hỏi đã được viết lại như sau:..." (← thêm giải thích)
"Luật Dân sự quy định gì?" (← quá đơn giản, không có tình huống)"""


SYSTEM_IRAC_RESPONDER = """Bạn là Thẩm phán Tòa án Nhân dân Tối cao Việt Nam với chuyên môn sâu về pháp luật dân sự, hình sự, hành chính và thương mại.

NHIỆM VỤ: Trả lời câu hỏi pháp lý NGHIÊM NGẶT theo cấu trúc IRAC.

FORMAT BẮT BUỘC (phải dùng chính xác các tiêu đề sau):

**Vấn đề (Issue):**
[Xác định vấn đề pháp lý trọng tâm dưới dạng CÂU HỎI. Ví dụ: "Liệu hành vi X của A có cấu thành tội Y hay không?"]

**Quy tắc (Rule):**
[Trích dẫn nguyên tắc pháp luật CHUNG. Phần này:
- PHẢI trích dẫn số hiệu điều luật cụ thể (Điều X, Khoản Y, Điểm Z).
- PHẢI nêu tên văn bản quy phạm (Bộ luật Dân sự 2015, Luật Hình sự 2015...).
- KHÔNG được chứa tên riêng của đương sự hay tình tiết vụ việc cụ thể.
- Nếu có nhiều luật liên quan, trình bày theo thứ tự ưu tiên áp dụng.]

**Áp dụng (Application):**
[Phân tích tình tiết CỤ THỂ dựa trên Rule:
- Đối chiếu TỪNG yếu tố cấu thành với tình tiết thực tế.
- Nêu rõ yếu tố nào THỎA MÃN, yếu tố nào KHÔNG thỏa mãn.
- Nếu có tình tiết tăng nặng/giảm nhẹ, phải phân tích riêng.]

**Kết luận (Conclusion):**
[Kết luận ngắn gọn, trả lời trực tiếp câu hỏi ở phần Issue.
- Phải khẳng định rõ ràng: có/không cấu thành, được/không được bảo vệ.
- Nêu hệ quả pháp lý cụ thể (mức phạt, quyền khiếu nại, bồi thường...).]

QUY TẮC BỔ SUNG:
- KHÔNG bịa đặt số hiệu điều luật. Nếu không chắc chắn, ghi "theo quy định của pháp luật hiện hành".
- Ưu tiên luật mới nhất (BLDS 2015 thay vì 2005, BLHS 2015 sửa đổi 2017 thay vì 1999).
- Phải phân biệt rõ trách nhiệm dân sự, hành chính và hình sự khi cần."""


# ══════════════════════════════════════════════════════════════════
# EVOL-INSTRUCT TECHNIQUE PROMPTS (6 kỹ thuật)
# ══════════════════════════════════════════════════════════════════

EVOL_TECHNIQUES = {
    # ── In-Depth Evolving (5 kỹ thuật) ───────────────────────────

    "constraint_addition": {
        "name": "Constraint Addition (Thêm ràng buộc IRAC)",
        "prompt": """Viết lại câu hỏi gốc sao cho phản hồi BẮT BUỘC phải tuân thủ cấu trúc IRAC:
- Issue: Xác định vấn đề pháp lý dưới dạng câu hỏi có/không.
- Rule: Trích dẫn Điều, Khoản cụ thể từ văn bản QPPL Việt Nam (KHÔNG dùng tên đương sự).
- Application: Phân tích đối chiếu từng yếu tố cấu thành với tình tiết vụ việc.
- Conclusion: Kết luận trực tiếp, nêu hệ quả pháp lý.

Bổ sung thêm ÍT NHẤT 1 ràng buộc:
- Yếu tố thời hiệu (thời hạn khởi kiện, thời hiệu truy cứu).
- Yếu tố chủ thể đặc biệt (người chưa thành niên, pháp nhân, cơ quan nhà nước).
- Yếu tố lỗi (lỗi cố ý, vô ý, lỗi hỗn hợp).

Câu hỏi gốc: {seed_instruction}

Câu hỏi viết lại:"""
    },

    "deepening": {
        "name": "Deepening (Đi sâu vào ngoại lệ)",
        "prompt": """Viết lại câu hỏi để yêu cầu phân tích CẢ quy tắc chung LẪN ngoại lệ:

1. Nêu quy định chung của điều luật áp dụng.
2. Phân tích ÍT NHẤT 2 trường hợp NGOẠI LỆ hoặc miễn trừ trách nhiệm.
   Ví dụ ngoại lệ phổ biến trong pháp luật VN:
   - Phòng vệ chính đáng (Điều 22 BLHS 2015)
   - Tình thế cấp thiết (Điều 23 BLHS 2015)
   - Sự kiện bất khả kháng (Điều 156 BLDS 2015)
   - Lỗi hoàn toàn của bên bị thiệt hại
3. So sánh hệ quả khi áp dụng quy tắc chung vs ngoại lệ.

Câu hỏi gốc: {seed_instruction}

Câu hỏi viết lại:"""
    },

    "concretizing": {
        "name": "Concretizing (Cụ thể hóa - Case Study)",
        "prompt": """Chuyển câu hỏi lý thuyết sau thành TÌNH HUỐNG PHÁP LÝ CỤ THỂ tại Việt Nam:

Yêu cầu tình huống phải có:
- Tên nhân vật giả định Việt Nam (ví dụ: Ông Trần Văn C, Bà Lê Thị D, Công ty TNHH E).
- Địa điểm cụ thể tại Việt Nam (quận/huyện, tỉnh/thành phố).
- Thời gian xảy ra sự kiện (ngày/tháng/năm).
- Ít nhất 2 bên có lợi ích mâu thuẫn.
- Tình tiết đủ phức tạp để cần phân tích nhiều điều luật.

Kết thúc bằng câu hỏi yêu cầu phân tích theo IRAC.

Câu hỏi gốc: {seed_instruction}

Tình huống pháp lý:"""
    },

    "increased_reasoning": {
        "name": "Increased Reasoning (Tăng bước lập luận)",
        "prompt": """Viết lại câu hỏi để yêu cầu phân tích NHIỀU LỚP lập luận pháp lý:

Câu hỏi mới phải yêu cầu:
1. Xác định TẤT CẢ các sự kiện pháp lý trong tình huống.
2. Liệt kê TỪNG điều luật liên quan và mối quan hệ giữa chúng (bổ trợ hay mâu thuẫn).
3. Khi có mâu thuẫn giữa các văn bản: phân tích nguyên tắc ưu tiên áp dụng
   (luật chuyên ngành vs luật chung, luật mới vs luật cũ, văn bản cấp trên vs cấp dưới).
4. Kết luận với lập luận chặt chẽ, dẫn chiếu chuỗi logic: Sự kiện → Điều luật → Đánh giá → Kết quả.

Câu hỏi gốc: {seed_instruction}

Câu hỏi viết lại:"""
    },

    "complicating_input": {
        "name": "Complicating Input (Phức tạp hóa bằng dữ liệu cấu trúc)",
        "prompt": """Viết lại câu hỏi bằng cách BỔ SUNG dữ liệu tình huống vào thẻ <facts>:

Tạo phần <facts> chứa:
- Mô tả diễn biến sự việc theo trình tự thời gian.
- Ít nhất 3 tình tiết quan trọng ảnh hưởng đến kết quả pháp lý.
- Có ít nhất 1 tình tiết gây TRANH CÃI (có thể giải thích theo 2 hướng khác nhau).
- Bằng chứng/chứng cứ mà các bên đưa ra.

Kết thúc bằng yêu cầu phân tích theo IRAC xem tình tiết có cấu thành vi phạm không.

Câu hỏi gốc: {seed_instruction}

Câu hỏi viết lại (bắt buộc có thẻ <facts>):"""
    },

    # ── In-Breadth Evolving (1 kỹ thuật) ─────────────────────────

    "mutation": {
        "name": "Mutation (Đột biến chủ đề ngách)",
        "prompt": """Dựa trên lĩnh vực pháp luật của câu hỏi sau, tạo câu hỏi HOÀN TOÀN MỚI về một khía cạnh HIẾM GẶP nhưng thực tiễn:

Ví dụ chủ đề ngách trong pháp luật Việt Nam:
- Tranh chấp quyền sở hữu trí tuệ đối với giống cây trồng
- Trách nhiệm pháp lý khi AI/robot gây thiệt hại
- Quyền của người chuyển giới trong hôn nhân gia đình
- Tranh chấp tên miền Internet
- Bảo vệ dữ liệu cá nhân trong thương mại điện tử
- Trách nhiệm của nền tảng trung gian (marketplace) đối với hàng giả

Yêu cầu:
- Câu hỏi mới KHÔNG được trùng nội dung câu gốc.
- Phải có tình huống cụ thể, không hỏi lý thuyết suông.
- Yêu cầu trả lời theo cấu trúc IRAC.

Câu hỏi tham khảo (chỉ để xác định lĩnh vực): {seed_instruction}

Câu hỏi mới:"""
    }
}


# ══════════════════════════════════════════════════════════════════
# SEED GENERATION TEMPLATES
# ══════════════════════════════════════════════════════════════════

SEED_TEMPLATES = [
    # ── Dạng thẩm quyền/quy định ─────────────────────────────────
    "Dựa trên {so_hieu_luat}, hãy cho biết thẩm quyền của {co_quan_ban_hanh} trong việc {noi_dung}.",
    "Theo {so_hieu_luat}, {noi_dung} được quy định như thế nào?",
    "{co_quan_ban_hanh} quy định gì trong {so_hieu_luat} liên quan đến {noi_dung}?",

    # ── Dạng phân tích/giải thích ─────────────────────────────────
    "Phân tích nội dung {noi_dung} theo quy định tại {so_hieu_luat}.",
    "Hãy giải thích quy định của {so_hieu_luat} về {noi_dung} do {co_quan_ban_hanh} ban hành.",

    # ── Dạng tình huống áp dụng ───────────────────────────────────
    "Trong trường hợp vi phạm {noi_dung}, {so_hieu_luat} quy định chế tài xử lý như thế nào?",
    "Nếu một cá nhân/tổ chức không tuân thủ {noi_dung} theo {so_hieu_luat}, hậu quả pháp lý là gì?",
    "Khi phát sinh tranh chấp liên quan đến {noi_dung}, các bên cần căn cứ vào quy định nào của {so_hieu_luat}?",

    # ── Dạng so sánh/đối chiếu ────────────────────────────────────
    "So sánh quy định về {noi_dung} trong {so_hieu_luat} với các văn bản liên quan do {co_quan_ban_hanh} ban hành.",
    "Quy định tại {so_hieu_luat} về {noi_dung} đã thay đổi như thế nào so với văn bản trước đó?",
]


# ══════════════════════════════════════════════════════════════════
# FEW-SHOT EXAMPLES (chống Instruction Drift cho model 8B)
# ══════════════════════════════════════════════════════════════════

FEW_SHOT_IRAC_EXAMPLE = """
Dưới đây là ví dụ mẫu về câu trả lời ĐÚNG cấu trúc IRAC. Hãy tuân thủ chính xác format này:

---

Câu hỏi: Anh Nguyễn Văn A điều khiển xe ô tô với nồng độ cồn 0.8mg/lít khí thở, gây tai nạn làm anh B bị gãy chân (tỷ lệ tổn thương cơ thể 35%). Hành vi của anh A bị xử lý như thế nào?

**Vấn đề (Issue):** Liệu hành vi điều khiển xe ô tô khi có nồng độ cồn vượt mức cho phép và gây thương tích cho người khác có đồng thời cấu thành vi phạm hành chính và tội phạm hình sự hay không?

**Quy tắc (Rule):** Theo Điều 260 Bộ luật Hình sự 2015 (sửa đổi, bổ sung 2017), người nào tham gia giao thông đường bộ mà vi phạm quy định về an toàn giao thông, gây thương tích hoặc gây tổn hại cho sức khỏe của người khác mà tỷ lệ tổn thương cơ thể từ 31% đến 60% thì bị phạt tiền từ 30.000.000 đồng đến 100.000.000 đồng, phạt cải tạo không giam giữ đến 3 năm hoặc phạt tù từ 1 năm đến 5 năm. Ngoài ra, Điều 65 Luật Giao thông đường bộ 2008 cấm người điều khiển xe cơ giới có nồng độ cồn trong máu hoặc hơi thở vượt quá mức quy định. Nghị định 100/2019/NĐ-CP (sửa đổi bởi Nghị định 123/2021/NĐ-CP) quy định mức xử phạt hành chính theo từng ngưỡng nồng độ cồn.

**Áp dụng (Application):** Trong vụ việc này, anh A có nồng độ cồn 0.8mg/lít khí thở, vượt xa ngưỡng cao nhất theo Nghị định 100/2019/NĐ-CP (trên 0.4mg/lít). Đồng thời, hành vi vi phạm giao thông của anh A đã gây hậu quả: anh B bị gãy chân với tỷ lệ tổn thương 35%, thuộc khoản 1 Điều 260 BLHS 2015 (tỷ lệ từ 31-60%). Như vậy, hành vi của anh A thỏa mãn đầy đủ cấu thành tội "Vi phạm quy định về tham gia giao thông đường bộ": (1) có hành vi vi phạm - lái xe khi say, (2) có hậu quả - gây thương tích 35%, (3) có mối quan hệ nhân quả giữa vi phạm và hậu quả.

**Kết luận (Conclusion):** Anh A bị truy cứu trách nhiệm hình sự theo khoản 1 Điều 260 BLHS 2015 với khung hình phạt tù từ 1-5 năm. Ngoài ra, anh A còn phải bồi thường thiệt hại dân sự cho anh B theo Điều 584-585 BLDS 2015 và có thể bị tước quyền sử dụng giấy phép lái xe.

---

LƯU Ý QUAN TRỌNG:
- Phần Rule: CHỈ nêu nguyên tắc chung, KHÔNG nhắc tên anh A, anh B.
- Phần Application: PHẢI đối chiếu cụ thể tình tiết (0.8mg, 35%) với quy định.
- Phần Conclusion: PHẢI nêu hệ quả pháp lý cụ thể (khung hình phạt, bồi thường)."""
