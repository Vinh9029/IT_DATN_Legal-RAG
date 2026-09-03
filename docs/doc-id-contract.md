
---

## 1. Vì sao phải chốt bây giờ

Phần 3 sinh ra một test set gồm các cặp câu hỏi broad/narrow, mỗi câu gắn với **văn bản luật gốc đã sinh ra nó**. Test set đó chỉ dùng được cho hai việc quan trọng nhất của đồ án nếu hai bên gọi tên cùng một văn bản theo cùng một cách:

| Việc | Cần gì |
|---|---|
| Đánh giá retrieval (recall@k, MRR) | Biết văn bản nào là **gold document** cho mỗi câu hỏi ⇒ phải so khớp id của Phần 3 với id mà retriever trả về |
| Ablation study cho Research Gap #2 (routing theo độ cụ thể) | Như trên, cộng thêm nhãn broad/narrow đã có sẵn |

Nếu hai bên dùng hai hệ id khác nhau thì lúc đánh giá chỉ còn cách so khớp theo nội dung văn bản — vừa chậm, vừa không chính xác, vừa vỡ ngay khi một trong hai bên đổi hàm làm sạch HTML. **Sửa sau khi đã build index nghĩa là phải reindex lại toàn bộ**, nên chốt trước là rẻ nhất.

---

## 2. Hình dạng `source_doc_id` của Phần 3

Sinh bởi `corpus_filter.derive_doc_id()` / `corpus_loader.normalize_record()`. Có **ba dạng**, tuỳ nguồn dữ liệu và cấu hình:

| # | Dạng | Khi nào | Ví dụ |
|---|---|---|---|
| A | `doc_<id gốc của nguồn>` | Nguồn có cột id (`id`, `doc_id`, `ma_van_ban`, `stt`…) | `doc_10174` |
| B | `doc_<md5 12 ký tự>` | Nguồn **không có** cột id — băm theo `so_hieu` → `title` → `content[:500]` | `doc_02a42ca7fb55` |
| C | `<A hoặc B>#dieu-<số điều>` | Bật `QA_SPLIT_BY_ARTICLE=1` | `doc_91-2015#dieu-623` |

### 2.1 Dạng A là dạng mong muốn — và nó phụ thuộc vào nguồn dữ liệu mới

Trước đây Phần 3 lấy corpus từ `th1nhng0/vietnamese-legal-documents`, dataset đó có sẵn trường `id` ở cả hai config `metadata` và `content` (chính nó là khoá join), nên dạng A là mặc định.

Nay Phần 3 đọc từ **thư mục cục bộ** `backend/data/corpus_civil/` (dataset mới của nhóm; dataset HuggingFace tụt xuống làm đường dự phòng). Dạng A chỉ giữ được nếu nguồn mới có một cột định danh ổn định.
>
> Nếu hai bên dùng hai nguồn khác nhau mà không có id chung, việc nối test set với retriever phải quay về so khớp theo `so_hieu` văn bản — kém hơn nhưng vẫn làm được, và cần chốt sớm.

### 2.2 Dạng C — hệ quả của việc cắt theo Điều

Phạm vi dân sự là ít văn bản nhưng rất dài (Bộ luật Dân sự 2015 có 689 Điều), nên Phần 3 có tuỳ chọn cắt mỗi Điều thành một document con (`QA_SPLIT_BY_ARTICLE`, mặc định TẮT — xem spec §2.1d). Khi bật, `source_doc_id` mang thêm hậu tố `#dieu-<n>`.

**Quy tắc so khớp cho Phần 1–2:** cắt từ ký tự `#` trở đi để lấy id ở **mức văn bản**.

```python
doc_id = source_doc_id.split("#")[0].removeprefix("doc_")
```

### 2.3 Đề nghị với Phần 1–2

Khi build index (vector store / BM25 / bất kể backend nào), mỗi chunk lưu kèm trường `doc_id` = **id gốc của văn bản, không có tiền tố `doc_` và không có hậu tố `#dieu-`**, và retriever trả trường đó ra trong kết quả.

Nếu một văn bản bị chia thành nhiều chunk thì mỗi chunk cứ có `chunk_id` riêng, nhưng **phải giữ thêm `doc_id` của văn bản mẹ** — đánh giá recall ở mức văn bản, không phải mức chunk.

---

## 3. Vướng mắc hiện tại ở phía Phần 1–2 (chỉ để biết, không phải yêu cầu sửa gấp)

**3.1. `load_and_preprocess()` làm rơi mất `id`.** `backend/evol_instruct/src/data_loader.py` trả về record chỉ gồm `content`, `metadata`, `content_length` — không có `id`. Kiểm chứng trên `data/raw/preprocessed_cache.jsonl` (154.380 dòng): key của mỗi dòng đúng là `['content', 'metadata', 'content_length']`.

**3.2. `metadata` đang rỗng toàn bộ.** `backend/config/settings.py` đặt `HF_DATASET_CONFIG=content`, mà config `content` chỉ có 2 cột `id` + `content_html` — không có `nganh`, `linh_vuc`, `so_hieu`… Nên `extract_metadata()` trả về chuỗi rỗng ở mọi trường (đã kiểm chứng trên cache ở trên). Muốn có metadata thật thì phải load thêm config `metadata` rồi join theo `id`.

**3.3. Tên trường số hiệu là `so_ky_hieu`, không phải `so_hieu`.** `extract_metadata()` đọc `item.get("so_hieu")`, nhưng trong config `metadata` của dataset trường này tên là `so_ky_hieu`. Kể cả khi sửa được 3.2 thì trường số hiệu vẫn sẽ rỗng nếu không đổi tên khoá.

Ba điểm này liên quan nhau: xử lý 3.1 gần như chắc chắn sẽ phải đụng tới 3.2, và 3.2 kéo theo 3.3.

---

## 4. Phần 3 cam kết gì

Dataset cuối của Phần 3 (`backend/data/qa_pairs/final/{train,val,test}.json`, đã mở ngoại lệ gitignore nên `git pull` là có) đảm bảo:

| Trường | Nội dung | Dùng để |
|---|---|---|
| `source_doc_id` | Một trong ba dạng ở §2, ổn định giữa các lần chạy | Gold document cho đánh giá retrieval |
| `final_label` | `broad` hoặc `narrow` (nhị phân, đã qua 3 tầng kiểm chứng) | Nhãn ground truth cho routing |
| `pair_id` | Nối 2 câu cùng một cặp đối chứng | So sánh có kiểm soát: cùng văn bản gốc, chỉ khác độ cụ thể |
| `metadata.title` | Tiêu đề văn bản | Đối chiếu dự phòng khi id hai bên không khớp |
| `metadata.so_hieu` / `.loai_van_ban` / `.nganh` / `.linh_vuc` | **Chỉ khi nguồn có** — nguồn tải tay thường thiếu | Lọc theo lĩnh vực, báo cáo phân bố |
| `metadata.scope` | Nhánh dân sự (`thua_ke`, `dat_dai_nha_o`…) | Báo cáo phân bố chủ đề |

`metadata.title` **luôn có** với nguồn cục bộ (thiếu thì lấy tên file), nên khi id hai bên không khớp thì đây là đường đối chiếu dự phòng — kém chính xác hơn id nhưng còn hơn so khớp theo nội dung.

Ngoài ra: `train/val/test` được chia **theo group `source_doc_id`**, và `assert_no_leakage()` bảo đảm không group nào xuất hiện ở hai split.

⚠️ **Cách đọc bất biến này khi bật cắt theo Điều:** group là **Điều**, không phải văn bản. Nghĩa là hai câu của cùng một Điều không bao giờ tách sang hai split (đây là leakage thật cần chặn), nhưng các Điều khác nhau của cùng một bộ luật thì được phép nằm khác split. Không nới ra như vậy thì cả Bộ luật Dân sự rơi trọn vào một split và không chia nổi train/val/test. Điều này **phải ghi vào phần Limitations của báo cáo**.
