# Nguồn corpus luật dân sự (Phần 3)

Thả dataset luật dân sự vào **thư mục này**. Không phải sửa dòng code nào.

Nội dung thư mục không lên git (xem `.gitignore`) — chỉ file README này lên.

## Định dạng đọc được

| Định dạng | Ghi chú | Cần cài thêm |
|---|---|---|
| `.jsonl` `.ndjson` | Mỗi dòng một document | — |
| `.json` | List, hoặc bọc `{"data": [...]}` | — |
| `.csv` `.tsv` | Tự dò dấu phân cách, đọc được BOM của Excel | — |
| `.xlsx` `.xlsm` | Đọc mọi sheet, dòng đầu là header | `openpyxl` |
| `.docx` | **Một file = một văn bản**, lấy cả text trong bảng | `python-docx` |
| `.txt` `.md` | Một file = một văn bản, tên file làm tiêu đề | — |
| `.html` `.htm` | Như trên, tự làm sạch tag | — |
| `.parquet` | | `pyarrow` (đã có theo `datasets`) |

Quét **đệ quy**, nên xếp thư mục con thoải mái. File khoá tạm của Word/Excel
(`~$...`) tự bị bỏ qua.

## Cột nào được đọc

Tên cột được **bỏ dấu và thường hoá** trước khi so khớp, nên `"Nội dung"` tự
khớp `noi_dung`, `"Số ký hiệu"` tự khớp `so_ky_hieu`. Bí danh khai ở
`FIELD_ALIASES` trong `config/qa_settings.py`.

| Trường | Bí danh đang nhận |
|---|---|
| **content** (bắt buộc) | `content`, `content_html`, `noi_dung`, `text`, `full_text`, `body`, `van_ban`, `plain_text` |
| id | `id`, `doc_id`, `document_id`, `ma_van_ban`, `ma_so`, `stt` |
| title | `title`, `tieu_de`, `ten_van_ban`, `trich_yeu`, `ten`, `name` |
| so_hieu | `so_ky_hieu`, `so_hieu`, `so_van_ban`, `ky_hieu`, `so`, `number` |
| loai_van_ban | `loai_van_ban`, `loai`, `the_loai`, `doc_type`, `type` |
| nganh / linh_vuc | `nganh` · `linh_vuc`, `chu_de`, `topic`, `domain`, `category`, `field` |

Chỉ **content là bắt buộc**. Thiếu `id` thì id được sinh ổn định từ nội dung;
thiếu `loai_van_ban` thì whitelist văn bản quy phạm tự tắt (không lọc).

Tên cột lạ thì **khai thêm bí danh**, đừng đổi tên cột trong file nguồn — giữ
file nguồn nguyên trạng thì còn truy ngược được.

## Quy trình

```bash
# 1. Thả file vào thư mục này

# 2. Xem thử đã nạp đúng chưa — KHÔNG gọi LLM, không tốn gì
python scripts/10_generate_qa_pairs.py --dry-run --rebuild-corpus

# 3. Chạy thật
python scripts/10_generate_qa_pairs.py --rebuild-corpus
python scripts/11_verify_labels.py
python scripts/12_export_dataset.py
```

Bước 2 in ra: số document, phân bố nhánh dân sự, nguồn từng file, và 10 tiêu đề
đầu. **Đọc 10 tiêu đề đó.** Đây là chỗ rẻ nhất để bắt corpus lạc phạm vi, trước
khi tiêu vài trăm lượt gọi LLM lên dữ liệu sai.

## Hai cái bẫy

**1. Cache.** `data/qa_pairs/raw/scoped_corpus.jsonl` được đọc trước mọi thứ.
Đổi nguồn / đổi phạm vi / bật cắt theo Điều mà quên `--rebuild-corpus` thì
corpus cũ vẫn về và mọi thay đổi trông như không có tác dụng.

**2. Bộ lọc phạm vi.** Mặc định `QA_SCOPE_FILTER_MODE=auto`: lọc bình thường,
nhưng nếu tỉ lệ lọt < 20% thì giữ nguyên cả corpus kèm cảnh báo — vì "nguồn đã
thuần dân sự sẵn" và "từ khoá không khớp cách đặt tên của nguồn" cho ra cùng
một triệu chứng, và cả hai đều không phải lý do để vứt dữ liệu.

- Nguồn đã thuần dân sự, khỏi lọc: `QA_SCOPE_FILTER_MODE=off`
- Muốn lọc thẳng tay bất kể tỉ lệ: `QA_SCOPE_FILTER_MODE=strict`

## Biến môi trường liên quan

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `QA_CORPUS_SOURCE` | `data/corpus_civil` | Thư mục/file nguồn |
| `QA_SCOPE_FILTER_MODE` | `auto` | `auto` · `strict` · `off` |
| `QA_SCOPE_AUTO_MIN_RATIO` | `0.20` | Ngưỡng tỉ lệ lọt của chế độ `auto` |
| `QA_MIN_CONTENT_LENGTH` | `500` | Bỏ document ngắn hơn ngưỡng này |
| `QA_SPLIT_BY_ARTICLE` | `0` | Bật để cắt mỗi Điều thành một document con |
| `QA_ARTICLE_MIN_LENGTH` | `300` | Điều ngắn hơn ngưỡng này thì bỏ |
