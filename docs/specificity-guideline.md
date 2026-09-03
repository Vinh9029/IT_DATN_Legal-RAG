# Guideline gán nhãn độ cụ thể câu hỏi pháp lý (Query Specificity)

**Phiên bản:** 1.2 — *đã thu hẹp phạm vi về luật dân sự*
**Vị trí trong repo:** `docs/specificity-guideline.md`
**Phạm vi áp dụng:** câu hỏi pháp lý tiếng Việt thuộc lĩnh vực **luật dân sự** và các chế định lân cận
(thừa kế, hợp đồng & giao dịch bảo đảm, sở hữu/tài sản, hôn nhân & gia đình, đất đai & nhà ở,
sở hữu trí tuệ, tố tụng & thi hành án dân sự, bồi thường ngoài hợp đồng)

---

## 1. Mục đích của tài liệu này

Tài liệu định nghĩa **operational definition** (định nghĩa vận hành) để phân biệt câu hỏi **broad** (rộng) với câu hỏi **narrow** (hẹp).

"Định nghĩa vận hành" nghĩa là: định nghĩa được diễn đạt bằng những tiêu chí **quan sát được và kiểm tra được** trên chính câu hỏi, chứ không phải bằng cảm nhận chủ quan. Phân biệt này quan trọng vì:

- Một định nghĩa kiểu *"câu hỏi rộng là câu hỏi mang tính tổng quát"* nghe thì hợp lý nhưng hai người đọc sẽ gán nhãn khác nhau — không dùng được để đo lường.
- Một định nghĩa kiểu *"câu hỏi rộng là câu hỏi cần từ 3 điều luật trở lên để trả lời đầy đủ"* thì hai người có thể kiểm tra và đi tới cùng kết luận.

Tài liệu này là **nguồn chân lý duy nhất** cho: prompt sinh cặp câu hỏi, prompt của LLM judge, hàm heuristic rule-based, và quá trình gán nhãn tay. Khi bốn thứ đó mâu thuẫn nhau, tài liệu này thắng.

---

## 2. Định nghĩa

### 2.1 Trực giác nền

Nhãn độ cụ thể phản ánh **lượng và kiểu thông tin mà hệ thống cần truy xuất** để trả lời được câu hỏi:

- **Narrow** — câu hỏi khoá chặt vào một quy định xác định. Truy xuất cần **độ chính xác cao, phạm vi hẹp**; lấy về nhiều văn bản chỉ tổ thêm nhiễu.
- **Broad** — câu hỏi mở, cần nhìn bao quát. Truy xuất cần **độ bao phủ rộng**; chỉ lấy một điều luật sẽ trả lời thiếu.

Nói cách khác, nhãn này không mô tả "câu hỏi khó hay dễ", cũng không mô tả "câu hỏi dài hay ngắn" — nó mô tả **hình dạng của tập tài liệu cần thiết để trả lời**.

### 2.2 Độ mịn của nhãn — CHỐT: phương án A (nhị phân)

| Phương án | Nhãn | Khi nào chọn | Trade-off |
|---|---|---|---|
| **A — ĐANG DÙNG** | `broad` / `narrow` | `IRetrievalStrategy` có **2** strategy | Đơn giản, F1 nhị phân dễ đọc. Câu ở vùng giữa bị ép về một bên → nhiễu nhãn. Khắc phục bằng cách **loại bỏ** câu vùng xám thay vì ép nhãn |
| B | `broad` / `medium` / `narrow` | `IRetrievalStrategy` có **3** strategy | Phản ánh thực tế tốt hơn nhưng cần thêm nhánh retrieval thứ ba; gán nhãn khó hơn, κ thường thấp hơn |

Nhãn `ambiguous` xuất hiện trong code (`Specificity.AMBIGUOUS`) **không phải** lớp thứ ba của phương án B. Nó là trạng thái "chưa quyết được" dùng nội bộ trong quá trình gán nhãn; dataset cuối cùng chỉ chứa `broad` và `narrow`. Xem mục 6.3.

**Quy tắc vùng xám (áp dụng cho phương án A):** câu hỏi không đạt ngưỡng rõ ràng của cả hai lớp thì **loại bỏ**, không ép nhãn. Ở quy mô đồ án, một dataset 600 câu nhãn sạch có giá trị hơn 1000 câu lẫn nhãn nhiễu — vì nhãn nhiễu làm sai lệch mọi metric phía sau và không có cách nào phát hiện ra sau khi đã trộn vào.

---

## 3. Ba trục tiêu chí

Mỗi câu hỏi được chấm độc lập trên 3 trục. Mỗi trục cho 1 điểm về phía `narrow` hoặc `broad`.

### Trục 1 — Mức chỉ định văn bản/điều khoản

*Câu hỏi có nêu đích danh văn bản, điều, khoản nào không?*

| Điểm | Biểu hiện |
|---|---|
| **→ narrow** | Nêu rõ số điều/khoản/điểm (*"Điều 623 Bộ luật Dân sự 2015"*, *"khoản 2 Điều 468 BLDS"*), hoặc nêu đích danh tên văn bản kèm chế định cụ thể |
| **→ broad** | Không nêu văn bản nào, hoặc chỉ nêu tên lĩnh vực (*"theo pháp luật dân sự"*, *"luật dân sự quy định thế nào"*) |

### Trục 2 — Số lượng điều luật cần để trả lời đầy đủ

*Để trả lời trọn vẹn, cần dẫn bao nhiêu điều luật?*

| Điểm | Biểu hiện |
|---|---|
| **→ narrow** | 1–2 điều luật là đủ. Câu trả lời có dạng "theo Điều X thì…" |
| **→ broad** | Từ 3 điều trở lên, hoặc phải tổng hợp từ nhiều văn bản khác nhau (luật + nghị định + thông tư), hoặc phải liệt kê nhiều trường hợp/điều kiện |

Đây là trục **khó chấm nhất** vì đòi hỏi hiểu biết về nội dung luật. Khi không chắc, dùng phép thử thay thế: *"câu trả lời đúng có phải là một danh sách nhiều mục không?"* — nếu có, nghiêng về broad.

### Trục 3 — Mức chi tiết của tình huống

*Câu hỏi có mô tả một tình huống cụ thể với đủ dữ kiện không?*

| Điểm | Biểu hiện |
|---|---|
| **→ narrow** | Có tình huống với chủ thể, hành vi, mốc thời gian, con số cụ thể (*"Anh A làm việc 3 năm, bị cho nghỉ không báo trước 45 ngày…"*) — đủ dữ kiện để áp dụng luật vào ngay |
| **→ broad** | Câu hỏi khái niệm, định nghĩa, tổng quan, hoặc tình huống nêu chung chung không đủ dữ kiện (*"Người thừa kế có những quyền gì?"*) |

---

## 4. Quy tắc tổng hợp nhãn

| Số trục nghiêng narrow | Nhãn |
|---|---|
| 3/3 | `narrow` |
| 2/3 | `narrow` |
| 1/3 | `broad` |
| 0/3 | `broad` |

**Ngoại lệ có quyền phủ quyết (override) — xét TRƯỚC quy tắc đếm ở trên:**

| Thứ tự | Ngoại lệ | Kết quả |
|---|---|---|
| **1** | **Trục 1 đạt narrow tuyệt đối** — nêu đích danh **cả điều VÀ khoản** cụ thể (*"khoản 1 Điều 35"*) | luôn `narrow` |
| **2** | **Câu hỏi có từ 2 vấn đề pháp lý độc lập trở lên** (*"…và trong trường hợp đó thì thủ tục khởi kiện thế nào?"*) | luôn `broad` |

Lý do ngoại lệ 1: khi người dùng đã chỉ đích danh điều khoản, chiến lược truy xuất đúng luôn là truy xuất chính xác — bất kể câu hỏi có tình huống hay không.
Lý do ngoại lệ 2: cần truy xuất bao phủ nhiều chế định.

**Khi cả hai ngoại lệ cùng đúng thì ngoại lệ 1 thắng** (*"Theo khoản 2 Điều 468 BLDS lãi suất tối đa là bao nhiêu, và trong trường hợp đó thì thủ tục khởi kiện thế nào?"* ⇒ `narrow`).

Đây là điểm tài liệu v1.0 bỏ ngỏ, buộc phải chốt vì code không thể "phân vân". Chọn ngoại lệ 1 thắng vì trích dẫn điều khoản đích danh là **tín hiệu quan sát trực tiếp được**, trong khi "2 vấn đề độc lập" là phán đoán về ngữ nghĩa — khi hai tín hiệu mâu thuẫn, tin cái đo được chắc chắn hơn. Ai thấy ngược lại thì sửa ở đây trước, rồi sửa `weak_labeler.heuristic_label()` sau, và ghi vào mục 8.

**Quy tắc vùng xám:** nếu khi chấm thấy có trục không chấm được (không đủ thông tin để quyết), hoặc kết quả 3 trục mâu thuẫn gay gắt với trực giác ở mục 2.1, đánh dấu `ambiguous` và loại khỏi dataset.

---

## 5. Ví dụ minh hoạ

### 5.1 Narrow

> "Theo khoản 1 Điều 623 Bộ luật Dân sự 2015, thời hiệu để người thừa kế yêu cầu chia di sản là bất động sản là bao nhiêu năm?"

Trục 1 → narrow (nêu đích danh khoản + điều + văn bản). Trục 2 → narrow (1 điều là đủ). Trục 3 → broad (không có tình huống). **Kết quả: 2/3 narrow → `narrow`**, và cũng thoả ngoại lệ phủ quyết ở Trục 1.

---

> "Ông A mất năm 2019, không để lại di chúc. Đến năm 2026, người con riêng của ông mới yêu cầu chia căn nhà mà ông đứng tên chung với vợ, hai người con chung phản đối vì cho rằng đã quá hạn. Yêu cầu chia di sản này có được chấp nhận không?"

Trục 1 → broad (không nêu điều luật). Trục 2 → narrow (chỉ cần điều về thời hiệu thừa kế + điều về hàng thừa kế, ~2 điều). Trục 3 → narrow (đủ dữ kiện: mốc mất, mốc yêu cầu, không di chúc, quan hệ các bên). **Kết quả: 2/3 narrow → `narrow`**

Ví dụ này cho thấy điều quan trọng: **narrow không đồng nghĩa với "có trích dẫn điều luật"**. Một tình huống đủ chi tiết để khoá vào một vài điều luật xác định cũng là narrow.

### 5.2 Broad

> "Người thừa kế có những quyền và nghĩa vụ gì theo pháp luật dân sự Việt Nam?"

Trục 1 → broad. Trục 2 → broad (phải tổng hợp nhiều điều). Trục 3 → broad (không có tình huống). **Kết quả: 0/3 narrow → `broad`**

---

> "Khi phát sinh tranh chấp hợp đồng dân sự, các bên có những phương thức giải quyết nào và ưu nhược điểm của từng phương thức ra sao?"

Trục 1 → broad. Trục 2 → broad (thương lượng, hoà giải, trọng tài, toà án — nhiều chế định, nhiều văn bản). Trục 3 → broad. **Kết quả: 0/3 → `broad`**

### 5.3 Vùng xám — loại bỏ

> "Giao dịch dân sự vô hiệu thì xử lý thế nào?"

Trục 1 → broad. Trục 3 → broad. Trục 2 → **không chấm được**: tuỳ vô hiệu toàn bộ (Điều 122) hay từng phần (Điều 130), tuỳ nguyên nhân vô hiệu, mà số điều luật cần dẫn khác nhau rõ rệt; câu hỏi không đủ thông tin để quyết. **Kết quả: `ambiguous` → loại bỏ.**

Đây chính xác là loại câu nên loại chứ không nên ép nhãn. Nếu ép thành broad, ta dạy classifier rằng mọi câu hỏi ngắn không nêu điều luật đều là broad — trong khi thực tế nó có thể là narrow nếu hiểu ngữ cảnh.

---

## 6. Ánh xạ sang heuristic rule-based

Phần này định nghĩa cách `backend/evol_instruct/src/qa_specificity/weak_labeler.py` chấm nhãn tự động. Heuristic **chỉ xấp xỉ được Trục 1 và Trục 3** — Trục 2 đòi hỏi hiểu nội dung luật nên không rule-based được, đó chính là lý do cần thêm tầng LLM judge.

### 6.1 Tín hiệu narrow — CÓ tính vào ngưỡng

Bốn tín hiệu, mỗi tín hiệu đếm **tối đa 1 lần** dù khớp nhiều chỗ trong câu.

| Khoá trong `heuristic_signals` | Trục | Bắt cái gì |
|---|---|---|
| `article_reference` | 1 | `Điều \d+`, `khoản \d+`, `điểm [a-z]` |
| `document_name` | 1 | Tên văn bản kèm năm (*Bộ luật Dân sự 2015*), số hiệu (`\d+/\d{4}/NĐ-CP`, `TT-`, `QĐ-`, `NQ-`, `QH`), hoặc viết tắt (`BLDS`, `BLLĐ`, `BLHS`, `BLTTDS`, `BLTTHS`) |
| `named_actor` | 3 | Danh xưng + tên riêng viết hoa (*Anh A*, *Chị B*, *Ông Nguyễn Văn A*), hoặc tổ chức có tên (*Công ty X*, *Công ty TNHH ABC*) |
| `quantity_with_unit` | 3 | Con số gắn đơn vị: `\d+ ngày/tuần/tháng/giờ/tuổi/%/triệu/tỷ/nghìn/đồng/lần/người` |

Hai điểm tinh chỉnh so với v1.0, cần thiết để tránh dương tính giả:

- `named_actor` khớp trên **text còn nguyên hoa/thường**, nếu không thì *"anh ấy"*, *"chị em"* bị tính nhầm là chủ thể có tên.
- `quantity_with_unit` **không bắt số trần**. *"Điều 623"* và *"Bộ luật Dân sự 2015"* chứa số nhưng không phải dữ kiện tình huống. Riêng đơn vị `năm` chỉ tính khi đi kèm *làm việc / kinh nghiệm / công tác / chung sống / sử dụng* — nếu không thì mọi năm ban hành văn bản, và mọi ngày tháng dạng *"ngày 24 tháng 11 năm 2015"*, đều bị đếm nhầm.

### 6.2 Tín hiệu broad — KHÔNG tính vào ngưỡng, chỉ để audit

| Khoá | Trục | Bắt cái gì |
|---|---|---|
| `enumeration` | 2, 3 | `có/gồm/bao gồm những … nào\|gì`, `liệt kê`, `các loại/hình thức/phương thức … nào` |
| `definition` | 3 | `… là gì`, `thế nào là …`, `khái niệm`, `định nghĩa` |
| `comparison` | 2 | `so sánh`, `khác nhau như thế nào`, `ưu nhược điểm`, `phân biệt` |
| `short_and_unspecific` | 3 | Câu < 15 từ **và** không có tín hiệu narrow nào |

⚠️ **Các tín hiệu broad hiện KHÔNG ảnh hưởng tới nhãn heuristic.** Nhãn chỉ do số tín hiệu narrow và hai ngoại lệ ở mục 4 quyết định. Chúng được ghi vào `heuristic_signals` để về sau còn phân tích được vì sao ra nhãn đó, và để làm cơ sở tinh chỉnh tiêu chí.

Hệ quả đã biết: câu *"Theo Điều 609, người thừa kế có những quyền gì?"* có 1 tín hiệu narrow + 1 tín hiệu broad ⇒ vẫn ra `ambiguous` theo đúng quy tắc mục 6.3, dù trực giác nghiêng broad. Đây là **lựa chọn có ý thức** — bám sát quy tắc đếm thay vì thêm luật ad-hoc — và là ứng viên số một để tinh chỉnh nếu tỷ lệ `ambiguous` thực tế quá cao.

### 6.3 Ngưỡng quyết định

Xét theo đúng thứ tự sau:

1. Ngoại lệ phủ quyết ở mục 4 (điều+khoản đích danh ⇒ `narrow`; ≥2 vấn đề độc lập ⇒ `broad`)
2. ≥ 2 tín hiệu narrow ⇒ `narrow`
3. 0 tín hiệu narrow ⇒ `broad`
4. Đúng 1 tín hiệu narrow ⇒ `ambiguous`

**`ambiguous` ở tầng heuristic nghĩa là ABSTAIN — "tầng này không đủ căn cứ để quyết", không phải "tầng này phản đối".** Phân biệt này quyết định trực tiếp quy tắc lọc đồng thuận ở Bước 2 của pipeline: item mà heuristic trả `ambiguous` **vẫn được giữ** nếu provenance và LLM judge đồng thuận với nhau. Xem `Qa_specificity_pipeline_spec.md` §4 Bước 2.

Lý do phải nói rõ: heuristic chỉ chấm được 2/3 trục nên `ambiguous` rất phổ biến. Nếu coi nó là bất đồng, tỷ lệ pass sẽ rơi xuống dưới ngưỡng dừng 40% **vì lý do kỹ thuật chứ không phải vì dữ liệu xấu** — rồi ta đi sửa prompt sinh câu trong khi prompt không có lỗi gì.

Ngược lại, `ambiguous` do **LLM judge** trả về thì **loại**, vì judge chấm đủ cả 3 trục nên đó là kết luận "câu này vùng xám" theo mục 5.3, không phải "tôi không biết".

⚠️ Không được dùng **độ dài câu hỏi** làm tín hiệu chính. Câu narrow có tình huống thường rất dài, câu narrow trích điều luật lại rất ngắn — độ dài không tương quan ổn định với độ cụ thể. Nó chỉ dùng được như tín hiệu phụ khi không còn tín hiệu nào khác (đúng như dòng `short_and_unspecific`).

---

## 7. Quy trình gán nhãn tay (dùng ở Bước 3 để tính Cohen's kappa)

Bước 1 và 5 đã được tự động hoá trong `evol_instruct/scripts/11_verify_labels.py`; bước 2–4 là việc tay.

```bash
# 1. Xuất mẫu ĐÃ ẨN NHÃN (chỉ còn item_id + question + manual_label rỗng)
python evol_instruct/scripts/11_verify_labels.py --export-manual-sample 100

# 2-4. Mở backend/data/qa_pairs/labeled/manual_sample_blind.jsonl, điền `manual_label` bằng tay

# 5. Tính kappa, ghi kappa_report.json cạnh file nhãn tay
python evol_instruct/scripts/11_verify_labels.py --compute-kappa backend/data/qa_pairs/labeled/manual_sample_blind.jsonl
```

1. Lấy ngẫu nhiên ~100 câu từ `pairs_verified.jsonl` *(tự động, seed cố định nên tái lập được)*
2. **Ẩn toàn bộ nhãn máy** (`specificity`, `heuristic_label`, `judge_label`) trước khi đọc — nếu nhìn thấy nhãn máy trước, kết quả bị **anchoring bias** và hệ số κ tính ra sẽ vô giá trị. *File xuất ra đã ẩn sẵn; việc còn lại là **không mở `pairs_verified.jsonl`** trong lúc gán.*
3. Với mỗi câu: chấm lần lượt 3 trục ở mục 3, áp quy tắc tổng hợp ở mục 4, ghi nhãn cuối vào `manual_label` (`broad` \| `narrow` \| `ambiguous`)
4. Chỉ đối chiếu với nhãn máy **sau khi đã gán xong toàn bộ 100 câu**
5. Tính `sklearn.metrics.cohen_kappa_score(nhan_tay, judge_label)` *(tự động)*

Câu gán tay là `ambiguous` bị **loại khỏi phép tính κ**, không phải tính như một lớp thứ ba: dataset là nhị phân, đưa lớp thứ ba vào làm κ không còn so sánh được với thang đọc bên dưới. Số câu bị bỏ qua được in ra và ghi trong `kappa_report.json` — phải báo cáo con số này kèm κ, vì bỏ qua quá nhiều câu là dấu hiệu tiêu chí còn mơ hồ.

**Đọc kết quả:**

| κ | Diễn giải | Hành động |
|---|---|---|
| > 0.8 | Đồng thuận tốt | Dùng dataset, báo cáo con số này |
| 0.6 – 0.8 | Chấp nhận được | Dùng được, nêu rõ trong báo cáo |
| < 0.6 | Tiêu chí chưa đủ rõ | Quay lại sửa **tài liệu này**, không phải sửa code. κ thấp là triệu chứng của định nghĩa mơ hồ, không phải của thuật toán tồi |

---