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
| `.doc` | Một file = một văn bản. Tự nhận ruột thật (xem dưới) | tuỳ ruột |
| `.rtf` | Một file = một văn bản | — (`striprtf` nếu có thì tốt hơn) |
| `.pdf` | Một file = một văn bản, tự bỏ header/footer + số trang | `pymupdf` |
| `.txt` `.md` | Một file = một văn bản, tên file làm tiêu đề | — |
| `.html` `.htm` | Như trên, tự làm sạch tag | — |
| `.parquet` | | `pyarrow` (đã có theo `datasets`) |

Quét **đệ quy**, nên xếp thư mục con thoải mái. File khoá tạm của Word/Excel
(`~$...`) tự bị bỏ qua.

### `.doc` — bốn định dạng dưới cùng một cái đuôi

Các trang tra cứu luật Việt Nam hay xuất "bản Word" bằng cách đổi đuôi. Loader
đọc mấy byte đầu để biết ruột thật, không tin cái đuôi:

| Ruột thật | Xử lý | Cần gì thêm |
|---|---|---|
| Zip (`.docx` đổi tên) | đọc thẳng như `.docx` | `python-docx` |
| RTF | bóc text như `.rtf` | — |
| HTML | làm sạch tag như `.html` | — |
| OLE2 (Word 97-2003 thật) | **convert sang `.docx` rồi mới đọc** | LibreOffice **hoặc** `pywin32` |

Chỉ ruột OLE2 mới cần cài thêm — vì không có thư viện Python thuần nào đọc được
định dạng đó mà ra tiếng Việt đúng dấu. Chọn một trong:

- **LibreOffice** (khuyến nghị): cài xong là xong, loader tự gọi `soffice`,
  convert được hàng loạt, không phải thao tác tay.
- **`pip install pywin32`**: dùng lại Microsoft Word đã cài sẵn trên máy.
- Không có cả hai: mở file bằng Word rồi *Save As → .docx*. Chỉ những file
  `.doc` OLE2 đó bị bỏ, phần còn lại của mẻ nạp vẫn chạy bình thường.

Bản convert được cache ở `data/qa_pairs/raw/converted_doc/` theo
(đường dẫn, kích thước, mtime) — chạy `--rebuild-corpus` lần hai không convert lại.

### `.pdf` — hai chỗ hay hỏng

**1. PDF scan.** PDF chụp ảnh trang giấy thì không có chữ nào để trích. Loader
đo số ký tự trên mỗi trang và **cảnh báo thẳng** khi nghi là bản scan, thay vì
để văn bản rỗng lặng lẽ bị loại ở bước "content quá ngắn". Gặp cảnh báo đó thì
OCR trước rồi thả bản đã OCR vào:

```bash
ocrmypdf -l vie van_ban_scan.pdf van_ban_ocr.pdf
```

**2. Bố cục theo trang.** Header/footer lặp lại, số trang, và câu bị cắt ngang ở
cuối dòng — loader tự dọn cả ba (`QA_PDF_REFLOW=0` để tắt phần nối dòng nếu thấy
nối nhầm trên một nguồn lạ).

Kèm theo đó là chuyện **trích dẫn chéo rơi vào đầu dòng**. Văn bản luật trích
dẫn nhau liên tục ("...quy định tại **Điều 53 của Bộ luật này**..."), và PDF
xuống dòng theo chiều ngang trang nên trích dẫn hay nằm đúng đầu dòng — khớp y
hệt một tiêu đề Điều. Hỏng kép: sinh một "Điều" ma bắt đầu từ giữa câu, đồng
thời cắt cụt Điều thật đang chứa nó. Loader phân biệt bằng dấu ngắt sau số
("Điều 53." là tiêu đề) và chữ hoa kế tiếp ("Điều 53 **N**gười giám hộ" là tiêu
đề, "Điều 53 **c**ủa Bộ luật này" là trích dẫn). Đo trên bản Công báo:

| | Trước khi sửa | Sau khi sửa | Thực tế |
|---|---|---|---|
| Bộ luật Dân sự 2015 | 699 Điều (10 ma) | **689** | 689 |
| Bộ luật Tố tụng Dân sự 2015 | 538 Điều (21 ma) | **517** | 517 |

## Cách để một file NGOÀI corpus mà vẫn giữ lại

Thư mục bắt đầu bằng dấu chấm bị **bỏ qua khi quét**. Dùng nó để cất bản trùng
mà không phải xoá:

```
data/corpus_civil/
├── pdf/                    ← được nạp
└── .doc_ole_backup/        ← bỏ qua, chỉ để dự phòng
```

Cùng một bộ luật ở hai định dạng thì **chỉ được để một bản trong corpus**. Hai
bản có `source_doc_id` khác nhau nên dedup không bắt được, mà cùng một Điều rơi
vào hai split khác nhau chính là data leakage giữa train và test.

### Đặt tên file cho đúng — quan trọng với `.pdf` / `.doc`

Ba định dạng "một file = một văn bản" không mang theo metadata nào, nên
**`title` chính là tên file**, và bộ lọc phạm vi khớp trên `title`. Đặt tên file
theo đúng tên văn bản thì mọi thứ khớp:

- ✅ `Bộ luật Dân sự 2015.pdf` → khớp nhánh `dan_su_chung`
- ✅ `Luật Hôn nhân và gia đình 2014.doc` → khớp `hon_nhan_gia_dinh`
- ❌ `bo_luat_dan_su_2015.pdf` → **không** khớp từ khoá nào (gạch dưới)
- ❌ `VBHN 91-2015.pdf` → không khớp

Đặt tên sai thì không mất dữ liệu (chế độ `auto` giữ nguyên cả corpus kèm cảnh
báo), nhưng **thống kê phân bố nhánh trong báo cáo sẽ rỗng**.

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

## Bổ sung từ HuggingFace — và vì sao phải có trần

`QA_CORPUS_MERGE_HF=1` gộp thêm dataset HF vào corpus cục bộ (dedup theo **số
hiệu văn bản**, không theo id — cùng một bộ luật ở hai nguồn mang hai id khác
nhau nhưng số hiệu thì trùng).

Gộp xong mà không làm gì thêm thì corpus ra 16.400 Điều, và phân bố hỏng theo
đúng hướng ngược với đề tài:

| nhánh | sau khi gộp | sau khi áp trần |
|---|---:|---:|
| dat_dai_nha_o | 4.554 | **200** |
| to_tung_thi_hanh_an | 3.984 | 863 |
| dan_su_chung | 2.542 | **1.898** |
| so_huu_tri_tue | 1.794 | 130 |
| hon_nhan_gia_dinh | 1.523 | 600 |
| hop_dong_bao_dam | 1.010 | 700 |
| boi_thuong | 518 | 400 |
| giai_quyet_tranh_chap | 349 | 100 |
| thua_ke | 126 | 126 |
| **tổng** | **16.400** | **5.017** |

Đất đai + tố tụng chiếm 52% corpus trong khi thừa kế được 0,8%. Cách hỏng này
**không lộ ra ở pass rate** — pass rate vẫn đẹp. Nó lộ ra ở chỗ classifier được
gọi là học "độ cụ thể" nhưng thực chất học trên một phân bố chủ đề lệch hẳn so
với phạm vi đã tuyên bố trong báo cáo.

`SCOPE_QUOTAS` (trong `config/qa_settings.py`) đặt trần cho từng nhánh, đưa về
**lõi dân sự 74,2% · tố tụng 17,2% · luật chuyên ngành lân cận 8,6%**.

Hai điều cần nhớ về cách trần hoạt động:

- **Chỉ áp cho phần bổ sung.** Corpus cục bộ (961 Điều của BLDS + BLTTDS, nguồn
  neo của đề tài) luôn qua nguyên vẹn, không đếm vào trần.
- **Lấy mẫu ngẫu nhiên có seed, không cắt N cái đầu.** Document xếp theo id mà
  id đi theo cơ quan ban hành và năm — cắt đầu danh sách thì trần 200 cho đất
  đai không phải "200 Điều đại diện cho đất đai" mà là "trọn vẹn 2-3 nghị định
  đầu tiên". Mẫu dùng `QA_RANDOM_SEED` nên **tái lập được y hệt** giữa các lần
  chạy (đã kiểm chứng bằng chữ ký SHA của danh sách id).

Đổi quy mô không phải sửa code:

```bash
QA_SCOPE_QUOTAS=dan_su_chung=2000,dat_dai_nha_o=0   # nới lõi, bỏ hẳn đất đai
QA_SCOPE_QUOTA_ENABLED=0                            # bỏ trần, lấy trọn 16.400
```

Trần áp lúc **đọc** cache chứ không lúc ghi, nên cache luôn giữ corpus đầy đủ và
đổi hạn ngạch **không cần `--rebuild-corpus`** — đây là ngoại lệ duy nhất của
cái bẫy cache. (Đổi nguồn / đổi phạm vi / bật cắt theo Điều thì vẫn cần.)

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
| `QA_CORPUS_MERGE_HF` | `0` | Bật để **gộp** thêm dataset HuggingFace vào corpus cục bộ |
| `QA_PDF_REFLOW` | `1` | Nối lại dòng bị PDF cắt giữa câu |
| `QA_PDF_MIN_CHARS_PER_PAGE` | `50` | Dưới ngưỡng này thì cảnh báo "nghi PDF scan" |
| `QA_PDF_HEADER_REPEAT_RATIO` | `0.6` | Dòng lặp trên ≥ tỉ lệ này số trang = header/footer |

## Dùng chung file tự tải với dataset HuggingFace

Mặc định hai nguồn **loại trừ nhau**: có file trong thư mục này thì dataset
HuggingFace không được đụng tới. Muốn dùng **cả hai**:

```bash
QA_CORPUS_MERGE_HF=1 python evol_instruct/scripts/10_generate_qa_pairs.py --dry-run --rebuild-corpus
```

Khi gộp:

- Corpus cục bộ đứng **trước** — trùng thì bản cục bộ thắng.
- Trùng được bắt theo **số hiệu văn bản**, không phải theo nội dung: cùng Bộ
  luật Dân sự 2015 nhưng bản `.pdf` tự tải và bản HTML trên HF không byte nào
  giống nhau, chỉ số hiệu là trùng. Không có số hiệu thì so tiêu đề.
- Mỗi document mang thêm `source_kind` (`local` / `hf`); `--dry-run` in ra tỉ lệ
  hai nguồn để đưa vào báo cáo.
- Bộ lọc phạm vi được áp **riêng cho từng nguồn rồi mới gộp** — gộp trước thì
  phần HF (vốn đã lọc sẵn) kéo tỉ lệ lọt lên gần 100% và lối thoát `auto` của
  corpus cục bộ không bao giờ kích hoạt.

⚠️ Đánh đổi phải ghi vào báo cáo: gộp là đổi **độ thuần** lấy **số lượng**.
Dataset HF là nguồn cũ, rộng hơn phạm vi dân sự đã chốt.
