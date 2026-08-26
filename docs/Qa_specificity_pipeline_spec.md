# Phần 3 — Xây dựng bộ dữ liệu QA gán nhãn độ cụ thể (Broad / Narrow)

**Đồ án:** Trợ lý ảo Tra cứu và Suy luận Pháp lý Việt Nam dựa trên RAG có Kiểm chứng Trích dẫn
**Repo:** `IT_DATN`
**Người phụ trách:** Vũ
**Phục vụ:** Research Gap #2 — Adaptive retrieval strategy based on query specificity

---

## 0. Mục tiêu và phạm vi

### 0.1 Phần 3 tạo ra cái gì

Một bộ dữ liệu gồm các **cặp câu hỏi pháp lý đối chứng** (contrastive pairs): mỗi cặp gồm 1 câu hỏi **broad** (rộng) và 1 câu hỏi **narrow** (hẹp) được sinh ra từ **cùng một văn bản luật gốc**, kèm nhãn độ cụ thể đã qua kiểm chứng nhiều tầng.

### 0.2 Vì sao cần bộ dữ liệu này

Hệ thống cần tự động phân biệt câu hỏi rộng (cần retrieve nhiều, bao quát) với câu hỏi hẹp (cần retrieve chính xác, ít nhiễu) để chọn `IRetrievalStrategy` phù hợp. Muốn chứng minh cơ chế routing này hoạt động — và muốn làm ablation study so sánh có/không có routing — bắt buộc phải có một **test set có nhãn ground truth**. Không có bộ dữ liệu này thì Research Gap #2 không có bằng chứng thực nghiệm, chỉ là mô tả tính năng.

---

## 1. Mục đích từng file

### 1.1 Tài liệu

| File | Mục đích | Ghi chú |
|---|---|---|
| `docs/specificity-guideline.md` | Định nghĩa vận hành (operational definition) phân biệt broad/narrow. Là **nguồn chân lý duy nhất** cho mọi bước gán nhãn phía sau | Phải hoàn thành TRƯỚC khi viết prompt. Xem file riêng |
| `docs/doc-id-contract.md` | Giao ước định danh văn bản với Phần 1–2: hai bên phải gọi cùng một văn bản bằng cùng một id|

### 1.2 Config

| File | Mục đích | Nội dung chính |
|---|---|---|
| `config/qa_settings.py` | Load `.env`, expose hằng số, tạo thư mục output, validate config | Tự tính `BASE_DIR = Path(__file__).resolve().parent.parent` và tự `load_dotenv()` — **không import biến nội bộ từ `config/settings.py`** để tránh coupling ngược |
| `config/qa_prompts.py` | Tập trung toàn bộ prompt template của Phần 3 | 3 nhóm: (a) `SYSTEM_PAIR_GENERATOR` + user template sinh cặp, (b) `SYSTEM_SPECIFICITY_JUDGE` + user template cho judge, (c) few-shot examples cho cả hai |

### 1.3 Source modules (`src/qa_specificity/`)

| File | Mục đích | Hàm/class chính (dự kiến) |
|---|---|---|
| `__init__.py` | Đánh dấu package, 1 dòng docstring mô tả | — |
| `schema.py` | Định nghĩa "hợp đồng dữ liệu" xuyên suốt pipeline: `Specificity` (Enum) và `QAItem` (dataclass). Mọi module khác đọc/ghi đều dùng chung schema này | `Specificity`, `QAItem`, `QAItem.to_dict()`, `QAItem.from_dict()` |
| `corpus_loader.py` | **Đọc** nguồn dữ liệu cục bộ, định dạng nào cũng được (`.jsonl/.json/.csv/.tsv/.xlsx/.docx/.txt/.md/.html/.parquet`), chuẩn hoá về doc dict chung. Tuỳ chọn cắt văn bản theo Điều | `load_local_corpus(source)`, `has_local_corpus(source)`, `expand_documents_by_article(docs)` |
| `corpus_filter.py` | **Lọc** corpus về đúng phạm vi luật dân sự trên doc dict đã chuẩn hoá, gán `source_doc_id` ổn định và nhánh con `scope`. Tự chọn nguồn: thư mục cục bộ trước, HuggingFace dự phòng | `load_scoped_corpus(max_items, source, rebuild)`, `scope_of(doc)`, `derive_doc_id(doc)` |
| `pair_generator.py` | Với mỗi document, gọi LLM **một lần** sinh ra đồng thời 1 câu broad + 1 câu narrow, parse kết quả thành 2 `QAItem` cùng `pair_id` | `generate_pair(doc, llm_client)`, `parse_pair_response(text)` |
| `weak_labeler.py` | Gán nhãn heuristic (rule-based) độc lập, dựa trên đặc trưng bề mặt của câu hỏi theo đúng tiêu chí trong guideline | `heuristic_label(question)`, các hàm chấm điểm từng trục |
| `llm_judge.py` | Gọi model **khác** model sinh, đưa câu hỏi vào mà **không tiết lộ nguồn gốc**, yêu cầu tự phân loại broad/narrow | `JudgeClient`, `judge_batch(items)` |
| `dataset_builder.py` | Hợp nhất kết quả 3 tầng nhãn, lọc mẫu đồng thuận, chia train/val/test theo group, tính thống kê, export | `filter_consensus(items)`, `group_split(items)`, `build_stats(splits)`, `export(splits)` |

### 1.4 Scripts (CLI entrypoint)

| File | Mục đích |
|---|---|
| `scripts/10_generate_qa_pairs.py` | Orchestrate: `corpus_filter` → `pair_generator` → lưu raw pairs. Có checkpoint để resume |
| `scripts/11_verify_labels.py` | Orchestrate: `weak_labeler` + `llm_judge` → lọc đồng thuận → lưu verified + rejected |
| `scripts/12_export_dataset.py` | Orchestrate: `dataset_builder` → xuất train/val/test + `stats.json` |

**Convention bắt buộc phải theo (giống script 01–05):**
```python
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.qa_settings import ensure_qa_directories, validate_qa_config
from src.utils import setup_logging
from src.qa_specificity.corpus_filter import load_scoped_corpus
```
Repo không dùng `pip install -e .`, mọi script đều chèn thủ công root vào `sys.path` rồi import tuyệt đối. Giữ đúng pattern này.

### 1.5 Tests

| File | Mục đích |
|---|---|
| `tests/test_qa_specificity.py` | **144 test** cho phần logic thuần (không gọi LLM). Mock `LLMClient` bằng `MagicMock` giống `tests/test_evol_engine.py`. Toàn bộ suite của repo: **183 passed**  |

Nhóm test và thứ nó bảo vệ:

| Nhóm | Bảo vệ điều gì |
|---|---|
| `TestSchema` | Round-trip `to_dict`/`from_dict` không mất dữ liệu; `blinded_dict` **không lộ bất kỳ nhãn máy nào** |
| `TestCorpusFilter` / `TestApplyScopeFilter` | `derive_doc_id` ổn định; whitelist loại văn bản (và việc nó tự tắt khi thiếu `loai_van_ban`); 5 cú khớp nhầm bị `SCOPE_ANTI_KEYWORDS` chặn; ba chế độ `SCOPE_FILTER_MODE` |
| `TestSlugTenCot` / `TestNormalizeRecord` / `TestLoadLocalCorpus` | Header tiếng Việt có dấu khớp đúng bí danh; BOM của Excel; loại trùng `source_doc_id`; một file hỏng không làm hỏng cả mẻ nạp |
| `TestSplitByArticle` | Cắt đúng số Điều; không bắt "điều" viết thường giữa câu; `source_doc_id` thành khoá group mới |
| `TestParsePairResponse` | Parser chịu được 6 biến thể định dạng méo + 4 dạng output rác mà không raise |
| `TestHeuristicLabel` | Khớp đúng từng ví dụ trong guideline §5; không bắt nhầm "anh ấy" thành tên riêng; không tính "2019" thành con số tình huống |
| `TestParseJudgeResponse` | Không parse được thì trả `None`, **không đoán bừa** thành broad/narrow |
| `TestResolveItem` / `TestFilterConsensus` | Ngữ nghĩa abstain vs kết luận của `ambiguous`; loại cặp khuyết vế |
| `TestGroupSplit` / `TestAssertNoLeakage` | **Không rò rỉ giữa các tập** |
| `TestComputeKappa` | κ và confusion matrix |

**Nguyên tắc test cho pipeline LLM:** không unit-test được output của LLM (nó không tất định). Test được là: parser có chịu được output méo mó không, heuristic có đúng tiêu chí không, group split có rò rỉ giữa các tập không. Riêng cái cuối là test quan trọng nhất — `test_khong_ro_ri_giua_train_va_test` khẳng định `set(train_doc_ids) & set(test_doc_ids) == set()`, và `assert_no_leakage()` còn được gọi ngay trong `group_split()` nên bất biến này được kiểm ở cả runtime lẫn test.

---

## 2. Tái sử dụng code — API contract chính xác

**Nguyên tắc: chỉ `import`, không `edit`.** Không sửa `config/settings.py`, `src/data_loader.py`, `src/llm_client.py`, `src/utils.py` — đây là file trung tâm  còn sửa thường xuyên, mỗi lần cả hai cùng sửa là một merge conflict.

Nhóm file Evol-Instruct (`config/prompts.py`, `src/seed_generator.py`, `src/evol_engine.py`, `src/filters.py`, `src/gemini_client.py`, `scripts/01–06`) từ 2026-08-26 đã chuyển sang Vũ theo `pipeline.png`, nhưng **Phần 3 vẫn không đụng vào** — đó là phần việc riêng, xử lý sau.

### 2.1 `src.data_loader.load_and_preprocess` — 🛑 KHÔNG DÙNG ĐƯỢC CHO PHẦN 3

```python
load_and_preprocess(max_items: int = 0, min_content_length: int = 200, cache: bool = True) -> list[dict]
```

Bản v1.0 của tài liệu này giả định hàm trên trả về metadata dùng được, và `corpus_filter.py` chỉ là wrapper mỏng quanh nó. **Giả định đó SAI.** Đã kiểm chứng trên dataset thật:

| Kiểm chứng | Kết quả |
|---|---|
| Dataset có mấy config? | **5**: `metadata`, `relationships`, `content`, `legacy_metadata`, `legacy_content` |
| Config `content` (mà `settings.py` đang trỏ tới) có cột gì? | **Chỉ 2 cột: `id`, `content_html`** — không có `nganh`/`linh_vuc`/`loai_van_ban` |
| `extract_metadata()` chạy trên config đó trả về gì? | Chuỗi **rỗng toàn bộ**, cho cả 154.380 document |
| Lọc phạm vi theo metadata qua đường này được bao nhiêu doc? | **0** |

Metadata thật nằm ở config **`metadata`** (171.556 bản ghi), join với content qua trường **`id`**. Cột thật: `id, title, so_ky_hieu, ngay_ban_hanh, loai_van_ban, ngay_co_hieu_luc, ngay_het_hieu_luc, nguon_thu_thap, ngay_dang_cong_bao, nganh, linh_vuc, co_quan_ban_hanh, chuc_danh, nguoi_ky, pham_vi, thong_tin_ap_dung, tinh_trang_hieu_luc`.

⚠️ Lưu ý thêm: trường thật tên là **`so_ky_hieu`**, không phải `so_hieu`. `extract_metadata()` đọc `so_hieu` nên trường này rỗng ngay cả khi chạy trên config `metadata`.

**Quyết định:** `corpus_filter.py` tự load và join hai config, chỉ dùng lại `clean_html`. Vẫn giữ nguyên tắc "chỉ import, không edit".

Đổi lại được hai thứ, cả hai đều tốt hơn thiết kế cũ:

| | Thiết kế cũ (v1.0) | Thiết kế mới |
|---|---|---|
| `source_doc_id` | Băm `so_hieu`, fallback băm `content[:500]` — phải chấp nhận đánh đổi | Lấy thẳng **`id` của dataset** — định danh thật, không phụ thuộc nội dung, không bao giờ đổi khi `clean_html` đổi |
| Chi phí | `clean_html` cho cả 170.824 doc rồi mới lọc → **~20 phút** | Lọc metadata trước, chỉ `clean_html` cho ~2.400 doc trong phạm vi → **dưới 1 phút** |

`derive_doc_id()` vẫn giữ hai tầng fallback (`so_ky_hieu` → băm `content[:500]`) phòng khi thiếu `id`. `generate_item_id` là hàm sẵn có trong `src.utils` (md5 lấy 12 ký tự đầu) — dùng lại, không tự viết.

### 2.1b Phạm vi: luật dân sự theo chiều sâu

**Quyết định (2026-08-26):** bỏ nhánh lao động, đi theo **chiều sâu** vào luật dân sự và các chế định lân cận. Đồng thời nhóm chuyển sang **nguồn dữ liệu mới**, nên `corpus_filter` không còn buộc chặt vào dataset HuggingFace.

#### Vì sao đổi

Phạm vi cũ (lao động + dân sự) đo trên dataset HF cho ra phân bố lệch nặng:

| Chỉ số | Giá trị |
|---|---|
| Bản ghi metadata | 171.556 |
| Lọt phạm vi cũ (lao động + dân sự) | 2.333 |
| Phân bố | `lao_dong` 2.188 (**94%**) · `dan_su` 145 (**6%**) |

Nguyên nhân: `linh_vuc` là `"Chưa phân loại"` cho 113.772/171.556 bản ghi (66%). Nhánh lao động thoát được nhờ `nganh = "Lao động - Thương binh và Xã hội"`, còn luật dân sự **không có ngành tương ứng** — nó rải trên `Tư pháp`, `Tài nguyên và Môi trường`, `Xây dựng`, và phần lớn là ô trống.

Giữ phạm vi rộng thì phần Limitations phải đi thanh minh cho con số 94/6. Đi theo chiều sâu thì lập luận sạch hơn: **chủ đề hẹp lại làm giảm biến nhiễu, nên thứ classifier học được chắc chắn là độ cụ thể chứ không phải chủ đề.**

#### Cách nhận diện phạm vi

Hai đường, khớp đường nào cũng lọt (`corpus_filter.scope_of`):

1. **Tiêu đề** khớp `CIVIL_ANCHOR_TITLES` — đường chính. Tiêu đề thì nguồn nào cũng có; `nganh`/`linh_vuc` thì nguồn mới có thể không có.
2. **`nganh` + `linh_vuc`** khớp `CIVIL_METADATA_KEYWORDS` — đường bổ sung.

Chín nhánh con (chỉ để thống kê cân bằng, **không phải nhãn**): `dan_su_chung`, `to_tung_thi_hanh_an`, `hon_nhan_gia_dinh`, `thua_ke`, `dat_dai_nha_o`, `so_huu_tri_tue`, `hop_dong_bao_dam`, `giai_quyet_tranh_chap`, `boi_thuong`.

`SCOPE_ANTI_KEYWORDS` loại các cú khớp nhầm **đã đo được trên dữ liệu thật**, không phải đề phòng suông: `phòng thủ dân sự` (civil defence), `hình sự` (BLTTHS lọt qua từ khoá "tố tụng"), `tài sản công`/`tài sản cố định`/`tài sản kết cấu hạ tầng` (công sản & kế toán), `bạo lực gia đình`, `tố tụng hành chính`.

#### Đo thử trên dataset HF cũ

Để biết phạm vi mới có đủ dữ liệu không, đã đo lại toàn bộ 171.556 bản ghi metadata:

| Cách lọc | Số doc | Văn bản gốc (Bộ luật/Luật/Pháp lệnh) |
|---|---|---|
| Nhánh `dan_su` của phạm vi cũ | 145 | rất ít |
| Từ khoá dân sự trên `nganh`+`linh_vuc` | 502 | — |
| Từ khoá rộng trên `title` | 2.143 | *bẩn* — kéo cả "tài sản công", "hợp đồng xây dựng" |
| **Anchor chặt trên `title`** | **522** | **57 (10,9%)** |
| **Anchor + mở rộng 1-hop qua `relationships`** | **1.109** | **155 (14,0%)** |

Mở rộng 1-hop chỉ dùng nhóm quan hệ *hướng dẫn / quy định chi tiết / sửa đổi bổ sung / hợp nhất*. **Không được dùng quan hệ `Căn cứ`** (668.173/1.03M dòng) — gần như mọi văn bản đều "căn cứ" vào một luật nào đó, đi 1-hop qua nó kéo về 13.185 doc, tức cả kho.

Kết luận: phạm vi sâu **không thiếu dữ liệu**, và mật độ văn bản gốc cao gấp khoảng 7 lần corpus cũ. Con số này đo trên nguồn HF; nguồn mới thay thế nó nhưng cách lọc giữ nguyên.

#### Whitelist loại văn bản

`INCLUDED_DOC_TYPES`: Bộ luật, Luật, Pháp lệnh, Nghị định, Thông tư, Thông tư liên tịch, Văn bản hợp nhất. Whitelist chứ không blacklist vì dataset HF có 91.183 "Quyết định" và 28.337 "Nghị quyết" — phần lớn là quyết định hành chính cá biệt, không chứa quy phạm.

⚠️ Bộ lọc này **tự tắt khi nguồn không khai `loai_van_ban`**. Loại sạch corpus vì thiếu một cột metadata là kiểu hỏng tệ nhất: không có thông báo lỗi nào, chỉ có "0 document" ở cuối.

### 2.1c Nguồn dữ liệu: thả file vào là chạy

`corpus_loader.py` tách riêng phần ĐỌC khỏi phần LỌC. Đổi nguồn dữ liệu không phải sửa logic phạm vi; đổi phạm vi không phải sửa code đọc file.

**Quy trình thêm dataset mới:**

1. Thả file vào `data/corpus_civil/` (đổi được qua `QA_CORPUS_SOURCE`). Quét đệ quy, nhiều file cũng được.
2. `python scripts/10_generate_qa_pairs.py --dry-run --rebuild-corpus` — in số document, phân bố nhánh, nguồn file, và 10 tiêu đề đầu để soát mắt.
3. Nếu tên cột lạ: khai thêm bí danh vào `FIELD_ALIASES` (`config/qa_settings.py`). So khớp sau khi **bỏ dấu** nên `"Nội dung"` tự khớp `noi_dung`, không cần khai bản có dấu.
4. Chạy thật.

| Định dạng | Ghi chú |
|---|---|
| `.jsonl` `.ndjson` `.json` | JSON bọc `{"data": [...]}` cũng nhận |
| `.csv` `.tsv` | Tự dò dấu phân cách; đọc được BOM của Excel; nới giới hạn độ dài ô |
| `.xlsx` `.xlsm` | Cần `openpyxl`. Đọc mọi sheet, dòng đầu là header |
| `.docx` | Cần `python-docx`. **Một file = một văn bản.** Lấy cả text trong bảng |
| `.txt` `.md` `.html` `.htm` | Một file = một văn bản; tên file làm tiêu đề. HTML tự làm sạch |
| `.parquet` | Cần `pyarrow` (đã có sẵn theo `datasets`) |

**Ba cơ chế chừa hao**, để nguồn lạ không làm pipeline im lặng trả về rỗng:

- `QA_SCOPE_FILTER_MODE=auto` (mặc định): nếu tỉ lệ lọt phạm vi < 20% thì **giữ nguyên cả corpus** kèm cảnh báo. Hai tình huống khác hẳn nhau — (a) nguồn đã thuần dân sự nên chẳng cần lọc, (b) từ khoá không khớp cách đặt tên của nguồn — cho ra cùng một triệu chứng, và cả hai đều không phải lý do để vứt dữ liệu. Đặt `strict` để lọc thẳng tay, `off` để bỏ lọc.
- Whitelist loại văn bản tự tắt khi nguồn không có `loai_van_ban` (nói ở §2.1b).
- Một file hỏng chỉ bị bỏ qua kèm log lỗi, không làm hỏng cả mẻ nạp.

### 2.1d Cắt theo Điều (`QA_SPLIT_BY_ARTICLE`)

Phạm vi sâu là **ít văn bản nhưng rất dài**: riêng Bộ luật Dân sự 2015 có 689 Điều. Lấy 1 cặp trên mỗi văn bản thì bộ luật lớn nhất cũng chỉ đóng góp đúng 1 cặp, mà `MAX_DOC_CHARS=2000` ký tự đầu của nó thì toàn phần "Căn cứ…" — nội dung đáng hỏi nằm ở giữa và không bao giờ tới lượt.

Bật cờ này thì mỗi Điều thành một document con. Văn bản không đánh số theo Điều (Thông tư đánh `I.`/`1.`, văn bản sửa đổi) thì giữ nguyên cả văn bản.

⚠️ **Hệ quả lên group split — phải ghi vào Limitations.** `source_doc_id` thành `<doc>#dieu-<n>` và đó mới là khoá group. Cách đọc: hai câu của **cùng một Điều** không bao giờ tách sang hai split khác nhau (đây là leakage thật cần chặn); các Điều **khác nhau** trong cùng một bộ luật thì được phép nằm khác split. Nếu group theo văn bản thì cả bộ luật rơi trọn vào một split và không chia nổi train/val/test.

Mặc định **TẮT** vì chưa biết nguồn mới có đánh số theo Điều hay không. Chạy `--dry-run` xem cắt được bao nhiêu rồi hãy bật, và bật xong phải `--rebuild-corpus`.

### 2.2 `src.llm_client.LLMClient`

```python
LLMClient(base_url: str = None, api_key: str = None, model_name: str = None)
client.chat(messages, temperature=0.7, max_tokens=None, top_p=None, stop=None) -> str
client.health_check() -> bool
```

Constructor cho phép override cả 3 tham số ⇒ **dùng được luôn cho judge model** mà không cần viết client mới:
```python
judge = LLMClient(base_url=JUDGE_LLM_BASE_URL, api_key=JUDGE_LLM_API_KEY, model_name=JUDGE_MODEL_NAME)
```

⚠️ **Quirk cần biết:** trong `chat()`, tham số stop được xử lý là `stop or STOP_TOKENS`, mà `STOP_TOKENS = ["<|eot_id|>"]` (token đặc thù của Llama 3.1). Truyền `stop=[]` sẽ **không** vô hiệu hoá được vì list rỗng là falsy. Với judge chạy trên OpenAI/Gemini thì chuỗi này vô hại (nó sẽ không bao giờ xuất hiện trong output), nên **không cần sửa gì** — chỉ cần biết để không hoang mang khi debug.

### 2.3 `src.utils`

| Hàm | Chữ ký | Dùng cho |
|---|---|---|
| `setup_logging` | `(log_file: str = "pipeline.log")` | Gọi đầu mỗi script, đặt tên log riêng (`10_qa_pairs.log`...) |
| `save_jsonl` | `(records: list[dict], filepath, mode: str = "a")` | Ghi hàng loạt. Nhớ `mode="w"` khi ghi đè |
| `load_jsonl` | `(filepath) -> list[dict]` | Đọc lại file giữa các script |
| `append_jsonl` | `(record: dict, filepath)` | Ghi từng record (an toàn khi crash giữa chừng) |
| `generate_item_id` | `(text: str) -> str` | Sinh id md5 12 ký tự |
| `truncate_text` | `(text, max_length=500)` | Cắt text khi logging |
| `Checkpoint` | `Checkpoint(file)` với `.is_processed(id)`, `.mark_processed(id)`, `.save()`, `.update_stats(k,v)`, `.processed_count` | Resume khi pipeline đứt giữa chừng |

**Khuyến nghị mạnh:** dùng `Checkpoint` ngay từ script 10. Sinh cặp câu hỏi cho vài trăm document mất hàng giờ trên model local; mất điện hoặc lỡ tay Ctrl+C mà không có checkpoint là phải chạy lại từ đầu.

---

## 3. External data / nguồn ngoài

| Nguồn | Trạng thái trong repo | Bạn cần làm gì |
|---|---|---|
| Nguồn chính: thư mục `data/corpus_civil/` | Người dùng tự thả dataset luật dân sự vào (mọi định dạng ở §2.1c). `corpus_filter.load_scoped_corpus()` đọc thẳng, cache corpus đã lọc vào `data/qa_pairs/raw/scoped_corpus.jsonl` (đã gitignore) | Không phải tải gì. Đổi nguồn thì phải chạy lại với `--rebuild-corpus` |
| Dự phòng: `th1nhng0/vietnamese-legal-documents` (HuggingFace) | Chỉ dùng khi thư mục trên chưa có file nào. Tải runtime | Lần đầu tải **~6 GB** vào HF cache. Xem mục 3.3 về chỗ đặt cache |
| LM Studio + `Meta-Llama-3.1-8B-Instruct-GGUF-Q4_K_M` | Không có trong repo (file `.gguf` đã gitignore) | Cài LM Studio, tải model, bật Local Server port 1234 — dùng cho bước **sinh cặp** |
| **Judge model (API ngoài)** | **Không có** — `.env.example` hiện tại chỉ cấu hình LM Studio local | **Bạn phải tự chuẩn bị.** Khuyến nghị `gpt-4o-mini` hoặc `gemini-flash`. Cần API key |
| `.agents/workflows/*.md` | **Có sẵn** — ghi chú kiến trúc RAG + Evol-Instruct | Chỉ đọc tham khảo, không phải data input |

### 3.1 Vì sao judge model bắt buộc phải khác model sinh

**Self-preference bias:** một LLM có xu hướng đánh giá cao output do chính nó sinh ra. Nếu dùng Llama 8B vừa sinh cặp vừa chấm nhãn, tầng kiểm chứng gần như vô nghĩa — nó sẽ đồng ý với chính mình ở tỷ lệ cao bất thường, cho ra một con số "độ đồng thuận" đẹp nhưng sai.

Nếu tuyệt đối không có ngân sách API, phương án dự phòng: dùng cùng model nhưng (a) prompt hoàn toàn khác, (b) không tiết lộ provenance, (c) **bắt buộc** phải có tầng gán tay thủ công và báo cáo rõ hạn chế này trong phần Limitations của báo cáo. Đây là phương án kém hơn, không phải phương án tương đương.

### 3.1b Ba lựa chọn judge và lựa chọn đang dùng

| Phương án | Khác model sinh? | Chi phí | Trạng thái |
|---|---|---|---|
| `google/gemma-4-12b-qat` trên LM Studio local | Có — khác họ model hoàn toàn với Llama-3.1 | \$0 | ✅ **đang dùng (mặc định)** |
| `gemini-2.5-flash` qua lớp OpenAI-compatible | Có — khác luôn nhà cung cấp, lập luận vững nhất | tỷ lệ thuận số câu, xem §3.2 | 🔧 đã nối sẵn, bật bằng 3 dòng env |
| Dùng lại chính Llama-3.1-8B | **Không** — self-preference bias | \$0 | ❌ chỉ là phương án dự phòng, phải ghi vào Limitations |

**Đổi sang Gemini là việc của cấu hình, không phải của code.** Gemini có endpoint OpenAI-compatible, mà `JudgeClient` vốn dựng trên `openai` SDK. Bỏ comment 3 dòng trong `config/qa.env`:

```
JUDGE_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
JUDGE_LLM_API_KEY=<GEMINI_API_KEY>
JUDGE_MODEL_NAME=gemini-2.5-flash
```

Hai lưu ý khi bật:
- Gemini chỉ nhận `reasoning_effort` ∈ {low, medium, high}; giá trị `none` (đang đặt cho Gemma-4) nhiều khả năng bị từ chối. **Không hỏng**: `JudgeClient._chat_raw()` bắt `BadRequestError`, bỏ tham số rồi gọi lại — chỉ thấy một dòng WARNING. Muốn log sạch thì để trống `JUDGE_REASONING_EFFORT`.
- `validate_qa_config()` sẽ tự cảnh báo khi phát hiện judge trỏ ra API ngoài (`judge_is_remote()`), nhắc chạy `--estimate-cost` trước.

**Vì sao mặc định vẫn là gemma local:** judge tốn đúng **1 lượt gọi cho mỗi câu hỏi**, nên chi phí tỷ lệ thuận với kích thước dataset — mà dataset còn chưa chốt sẽ to cỡ nào. Quan trọng hơn: quota Gemini dùng chung với pipeline Evol-Instruct. Gemma local cho kết quả dùng được ngay với chi phí \$0; đổi sang Gemini là nâng cấp chất lượng lập luận trong báo cáo, không phải điều kiện cần để chạy.

### 3.2 Ước lượng chi phí judge

⚠️ Con số "~200 token input" ở bản v1.0 là **sai**. Nó bỏ quên phần khối tiêu chí 3 trục và few-shot nhét trong system prompt. Đo lại trên prompt thật đang dùng:

| Prompt | Ký tự | Ước lượng token |
|---|---|---|
| Judge, có few-shot (mặc định) | 3.948 | ~1.300–1.600 |
| Judge, `use_fewshot=False` | 2.218 | ~740–900 |
| Sinh cặp (doc 2.000 ký tự) | 5.217 | ~1.700–2.100 |

*(Tiếng Việt tốn token hơn tiếng Anh đáng kể — khoảng 2–2,5 ký tự/token với tokenizer của GPT, không phải 4.)*

Với 1000 câu hỏi: **~1,4M token input + ~40K token output**. Trên `gpt-4o-mini` (\$0.15/1M input, \$0.60/1M output) là khoảng **\$0.25**. Kết luận của v1.0 vẫn đúng — chi phí không phải rào cản — nhưng con số thì phải sửa, và nếu đổi sang model đắt hơn thì phải nhân lại từ đây chứ không phải từ 220K.

Hai cách giảm nếu cần:
- `build_judge_messages(q, use_fewshot=False)` cắt gần một nửa input, đổi lại model bám định dạng JSON kém hơn.
- `judge_cache.jsonl` khiến chạy lại script 11 **không tốn thêm đồng nào** cho câu đã chấm — cache bật mặc định.

**Đo trên dataset thật thay vì ước lượng bằng tay:**

```bash
python scripts/11_verify_labels.py --estimate-cost
```

Lệnh này **không gọi API lần nào**. Nó đọc `pairs.jsonl`, trừ đi những câu đã có trong `judge_cache.jsonl`, dựng prompt judge thật cho phần còn lại rồi quy ra token và tiền theo đơn giá trong `config/qa_settings.py` (`QA_JUDGE_PRICE_INPUT_PER_M` / `QA_JUDGE_PRICE_OUTPUT_PER_M` — override được bằng env vì **giá công bố có thể đã đổi**, đừng trích thẳng con số mặc định vào báo cáo). Judge đang chạy local thì nó in \$0 kèm dòng "nếu đổi sang API ngoài thì sẽ là bao nhiêu".

Nên gọi judge **một câu một lần**, đừng gộp batch nhiều câu vào một prompt: gộp lại làm model bị ảnh hưởng bởi ngữ cảnh các câu lân cận (contamination), phá vỡ tính độc lập của phép đánh giá. Hàm tên là `judge_batch()` nhưng "batch" chỉ nghĩa là duyệt qua một danh sách — mỗi câu vẫn là một lượt gọi riêng.

### 3.3 Hai cái bẫy môi trường (đã gặp thật, không phải giả định)

**1. HF cache mặc định nằm trên ổ C:.** Dataset chiếm ~6 GB. Nếu C: gần đầy sẽ chết giữa chừng với `RuntimeError: ... IO Error: There is not enough space on the disk. (os error 112)` — thông báo này nằm sâu trong stack trace của `huggingface_hub`, rất dễ tưởng nhầm là lỗi mạng. Chuyển cache sang ổ còn chỗ:

```
setx HF_HOME "G:\hf_cache"
```

Phải set ở **cấp OS**, không đặt trong `.env` được: `data_loader.py` import `datasets` *trước* khi `config.settings` gọi `load_dotenv()`, nên biến trong `.env` đến quá muộn.

```
setx PYTHONIOENCODING utf-8
```

---

## 4. Quy trình thực hiện chi tiết

---

### BƯỚC 1 — Sinh cặp câu hỏi

```bash
# Lần đầu, hoặc bất cứ khi nào đổi nguồn / đổi phạm vi / bật cắt theo Điều:
python scripts/10_generate_qa_pairs.py --dry-run --rebuild-corpus   # soát trước, không gọi LLM
python scripts/10_generate_qa_pairs.py --max-docs 500 --rebuild-corpus

# Các lần sau (nguồn không đổi) — dùng cache, nhanh hơn nhiều:
python scripts/10_generate_qa_pairs.py --max-docs 500
```

⚠️ **Bẫy cache.** `data/qa_pairs/raw/scoped_corpus.jsonl` được đọc TRƯỚC mọi thứ khác.
Đổi nguồn / đổi từ khoá phạm vi / bật `QA_SPLIT_BY_ARTICLE` mà quên `--rebuild-corpus`
thì corpus cũ vẫn về nguyên và mọi thay đổi trông như không có tác dụng — không có
thông báo lỗi nào cả.

**Input:**
- Corpus qua `load_scoped_corpus()` (đã lọc phạm vi luật dân sự; nguồn cục bộ trước,
  HuggingFace dự phòng — xem §2.1c)
- `LLMClient` trỏ tới LM Studio local

**Xử lý — với mỗi document:**
1. Cắt `doc["content"]` xuống ~2000 ký tự (`QA_MAX_DOC_CHARS`, giống cách `seed_generator.py`)

   *Cửa sổ 2.000 ký tự có đủ nội dung thật không?* Văn bản pháp luật mở đầu bằng boilerplate ("CHÍNH PHỦ… Căn cứ Luật…") nên cắt từ đầu có nguy cơ chỉ lấy được phần vỏ.

   > 📌 **Số đo dưới đây lấy trên corpus CŨ** (2.333 doc lao động + dân sự từ dataset HuggingFace), giữ lại làm tham chiếu. Nguồn mới phải đo lại — corpus dân sự có tỉ lệ bộ luật/luật dài cao hơn hẳn nên phân bố này gần như chắc chắn dịch đi.
   >
   > `Điều 1` bắt đầu ở vị trí median **963** ký tự, p75 = 1.255, và **chỉ 4%** doc có `Điều 1` nằm sau ký tự 2.000. Vậy cửa sổ 2.000 ký tự bắt được cả phần đầu lẫn một vài điều đầu tiên. (37% doc không có chuỗi `Điều 1` nào: chủ yếu là Thông tư đánh số theo `I.`/`1.` hoặc văn bản sửa đổi.)

   Với phạm vi dân sự, cửa sổ đầu văn bản là **cách xử lý kém**: Bộ luật Dân sự 2015 có 689 Điều mà 2.000 ký tự đầu chỉ chứa phần "Căn cứ…". Cách đúng là bật `QA_SPLIT_BY_ARTICLE` (§2.1d) để mỗi Điều thành một nguồn sinh cặp riêng. Nếu không bật thì ít nhất tăng `QA_MAX_DOC_CHARS` lên 3000–4000 — vẫn an toàn với `CONTEXT_LENGTH=8192`.
2. Gọi LLM **một lần duy nhất** với prompt yêu cầu sinh đồng thời cả 2 câu hỏi, trả về format cố định để dễ parse
3. Parse thành 2 `QAItem`, cùng `pair_id`, cùng `source_doc_id`, khác `specificity`
4. `append_jsonl` từng cặp, `checkpoint.mark_processed(doc_id)`

**Vì sao sinh theo cặp trong MỘT lần gọi, không phải hai lần gọi riêng:**

Đây là điểm thiết kế quan trọng nhất của Bước 1. Nếu sinh câu broad và câu narrow độc lập nhau, phân bố chủ đề của hai lớp có thể lệch nhau (ví dụ broad nghiêng về thừa kế, narrow nghiêng về đất đai). Classifier khi đó học **chủ đề** thay vì học **độ cụ thể** — hiện tượng gọi là **shortcut learning** (model bám vào đặc trưng ăn theo dễ học hơn thay vì đặc trưng ta muốn nó học). Nó cho accuracy cao giả tạo trên test set rồi sập khi gặp dữ liệu thật.

Sinh cùng lúc từ cùng một văn bản ⇒ hai câu hỏi có cùng chủ đề, cùng lĩnh vực, cùng nguồn — biến duy nhất khác nhau là độ cụ thể. Đây là thiết kế **contrastive pair**, và trong báo cáo có thể diễn đạt là "thiết kế cặp đối chứng nhằm loại bỏ confound về chủ đề".

**Output:** `data/qa_pairs/raw/pairs.jsonl` + `data/qa_pairs/raw/generation_checkpoint.json`
(kèm `data/qa_pairs/raw/scoped_corpus.jsonl` — cache corpus đã lọc phạm vi, sinh ở lần chạy đầu)

**Kiểm tra trước khi đốt hàng giờ GPU:** `python scripts/10_generate_qa_pairs.py --dry-run` chỉ lọc corpus và in thống kê, không gọi LLM.

**Xử lý tiếp:** chưa dùng được. Nhãn hiện tại mới chỉ là **provenance label** (câu sinh ở nhánh nào thì mang nhãn đó) — chưa qua kiểm chứng nào. Chuyển thẳng sang Bước 2.

---

### BƯỚC 2 — Gán nhãn và kiểm chứng 3 tầng

```bash
python scripts/11_verify_labels.py --input data/qa_pairs/raw/pairs.jsonl
```

**Input:** `pairs.jsonl` từ Bước 1

**Xử lý:**

| Tầng | Nguồn nhãn | Cơ chế | Chi phí |
|---|---|---|---|
| 1. Provenance | Đã có từ Bước 1 | Câu sinh ở nhánh broad → nhãn broad | 0 |
| 2. Heuristic | `weak_labeler.heuristic_label()` | Rule-based theo tiêu chí trong guideline (có nêu điều/khoản không, độ dài, có tình huống cụ thể không) | 0 |
| 3. LLM Judge | `llm_judge.judge_batch()` | Model khác đọc câu hỏi, **không biết** provenance, tự phân loại | 1 API call/câu |

**Quy tắc giữ/loại** (bản v1.0 ghi gọn là "chỉ giữ item có cả 3 tầng cùng nhãn"; dưới đây là bản chính xác, đã tính tới ngữ nghĩa của `ambiguous`):

| Điều kiện | Kết quả | `reject_reason` |
|---|---|---|
| Judge không trả về nhãn hợp lệ (lỗi API / không parse được) | loại | `judge_missing` |
| Judge trả `ambiguous` | loại | `judge_ambiguous` |
| Provenance ≠ judge | loại | `provenance_vs_judge_mismatch` |
| Heuristic ≠ judge (và heuristic không phải `ambiguous`) | loại | `heuristic_vs_judge_mismatch` |
| Heuristic = `ambiguous`, provenance = judge | **GIỮ** | — |
| Cả 3 tầng cùng nhãn | **GIỮ** | — |
| Cặp mất một vế sau khi lọc | loại nốt vế còn lại | `incomplete_pair` |

**Vì sao `ambiguous` của heuristic được giữ, còn của judge thì loại:** hai tầng nói hai chuyện khác nhau. Heuristic chỉ chấm được 2/3 trục (Trục 2 cần hiểu nội dung luật) nên `ambiguous` của nó nghĩa là *"tầng này không đủ căn cứ"* — guideline §6.3 gọi là **abstain**, "nhường quyết định cho LLM judge và tầng provenance". Judge chấm đủ cả 3 trục nên `ambiguous` của nó là **kết luận**: *"câu này thuộc vùng xám"*, đúng loại câu mà guideline §5.3 bảo phải loại.

Nếu coi abstain của heuristic là bất đồng thì tỷ lệ pass rơi xuống dưới ngưỡng dừng 40% **vì lý do kỹ thuật chứ không phải vì dữ liệu xấu** — rồi ta đi sửa prompt sinh câu trong khi prompt không có lỗi gì.

Script vẫn tính song song con số theo cách đọc chặt và ghi vào `verification_stats.json` khoá `strict_consensus`, để phần Limitations của báo cáo có số mà nói. Cờ `--strict-consensus` chạy hẳn theo cách đọc đó.

**Loại cả cặp khi mất một vế:** nếu vế narrow bị loại nhiều hơn vế broad thì phân bố chủ đề của hai lớp lệch trở lại — đúng cái confound mà thiết kế cặp đối chứng sinh ra để triệt tiêu. Cờ `--allow-incomplete-pairs` tắt hành vi này nếu cần phân tích.

Item bị loại → ghi sang `pairs_rejected.jsonl` (để phân tích, không xoá).

**Vì sao dùng tận 3 tầng thay vì tin thẳng provenance:** provenance chỉ nói lên "ta đã YÊU CẦU model sinh câu broad", không nói lên "model đã sinh ra câu broad thật". Model 8B thường xuyên không tuân thủ yêu cầu — nó có thể sinh ra hai câu gần như giống nhau về độ cụ thể. Ba tầng độc lập hội tụ về cùng một nhãn là bằng chứng mạnh hơn nhiều so với một tầng.

**Output:**
- `data/qa_pairs/labeled/pairs_verified.jsonl`
- `data/qa_pairs/labeled/pairs_rejected.jsonl`
- `data/qa_pairs/labeled/verification_stats.json`
- `data/qa_pairs/labeled/judge_cache.jsonl` — kết quả judge từng câu; chạy lại script không gọi lại API cho câu đã chấm

**Xử lý tiếp — đây là checkpoint quyết định, phải đọc số trước khi đi tiếp:**

| Tỷ lệ pass | Ý nghĩa | Hành động |
|---|---|---|
| > 70% | Prompt tốt, model tuân thủ | Đi tiếp Bước 3 |
| 40–70% | Chấp nhận được nhưng còn lãng phí | Xem `pairs_rejected.jsonl`, tìm pattern lỗi, tinh chỉnh prompt, chạy lại |
| < 40% | Prompt hoặc tiêu chí có vấn đề nghiêm trọng | **Dừng lại.** Quay về Bước 0/1. Chạy tiếp chỉ tổ đốt thời gian |

Nguyên tắc: chất lượng hơn số lượng. Ở quy mô đồ án, phải lọc bỏ phần lớn dữ liệu là **dấu hiệu quy trình sai**, không phải chuyện bình thường phải chấp nhận.

---

### BƯỚC 3 — Gán tay và đo độ tin cậy (thủ công)

**Input:** lấy ngẫu nhiên ~100 câu từ `pairs_verified.jsonl`

Việc lấy mẫu và tính toán đã được tự động hoá trong script 11; phần gán nhãn là việc tay:

```bash
python scripts/11_verify_labels.py --export-manual-sample 100
# → data/qa_pairs/labeled/manual_sample_blind.jsonl (chỉ có item_id + question + manual_label rỗng)
# … điền `manual_label` bằng tay …
python scripts/11_verify_labels.py --compute-kappa data/qa_pairs/labeled/manual_sample_blind.jsonl
# → kappa_report.json
```

**Xử lý:**
1. Tự gán nhãn tay 100 câu này, **không nhìn nhãn máy** (nếu nhìn trước sẽ bị anchoring bias — kết quả vô giá trị). File xuất ra đã ẩn sẵn mọi nhãn máy; việc còn lại là **không mở `pairs_verified.jsonl`** trong lúc gán.
2. Tính **Cohen's kappa** giữa nhãn tay và `judge_label`

Câu gán tay là `ambiguous` bị **loại khỏi phép tính κ** (dataset là nhị phân, thêm lớp thứ ba làm κ không so được với thang đọc chuẩn). Số câu bị bỏ qua được in ra và ghi trong `kappa_report.json` — **phải báo cáo con số này kèm κ**, vì bỏ qua quá nhiều là dấu hiệu tiêu chí còn mơ hồ.

**Cohen's kappa là gì:** hệ số đo mức đồng thuận giữa hai bộ gán nhãn, đã trừ đi phần đồng thuận xảy ra ngẫu nhiên. Cần trừ phần ngẫu nhiên vì với bài toán nhị phân, hai người gán bừa vẫn trùng nhau ~50%. Thang đọc: κ > 0.6 chấp nhận được, κ > 0.8 tốt. Tính bằng `sklearn.metrics.cohen_kappa_score` (scikit-learn đã có trong `requirements.txt`, không cần cài thêm).

**Output:** một con số κ + bảng confusion matrix nhỏ

**Xử lý tiếp:** đưa thẳng vào báo cáo. Đây là **bằng chứng học thuật duy nhất** cho chất lượng dataset. Không có nó, phản biện hoàn toàn có quyền nói dataset không đáng tin và toàn bộ kết quả ablation study phía sau mất giá trị.

Nếu κ < 0.6: nghĩa là tiêu chí trong guideline chưa đủ rõ để hai bộ gán nhãn hiểu giống nhau → quay lại Bước 0 làm rõ tiêu chí, không phải chỉnh code.

---

### BƯỚC 4 — Chia tập và export

```bash
python scripts/12_export_dataset.py --input data/qa_pairs/labeled/pairs_verified.jsonl
```

**Input:** `pairs_verified.jsonl`

**Xử lý:**
1. **Group split theo `source_doc_id`** bằng `sklearn.model_selection.GroupShuffleSplit`, tỷ lệ 70/15/15
2. Kiểm tra bất biến: cả cặp broad/narrow phải nằm cùng một split, và `set(train_doc_ids) & set(test_doc_ids)` phải rỗng
3. Kiểm tra cân bằng nhãn từng split
4. Sinh `stats.json`

**Vì sao bắt buộc group split, không được random split:** hai câu trong một cặp cùng sinh từ một văn bản, nội dung chồng lấn nhau rất nhiều. Nếu câu broad rơi vào train còn câu narrow rơi vào test, model đã "thấy" nội dung điều luật đó lúc train và ăn điểm ở test → **data leakage**, metric cao giả tạo. Đây là lỗi phổ biến và nguy hiểm vì nó không báo lỗi gì cả, chỉ âm thầm cho ra con số đẹp không có thật.

**Output:**
```
data/qa_pairs/final/train.json     # ~70%
data/qa_pairs/final/val.json       # ~15%
data/qa_pairs/final/test.json      # ~15%
data/qa_pairs/final/stats.json
```

---

## 5. Deliverables và cách xử lý

### 5.1 Danh sách deliverables

| # | Sản phẩm | Vị trí | Dùng cho |
|---|---|---|---|
| 1 | `train.json` / `val.json` / `test.json` | `data/qa_pairs/final/` | **Chính.** dùng để train/eval query classifier hoặc routing rule |
| 2 | `stats.json` | `data/qa_pairs/final/` | Bảng thống kê trong báo cáo |
| 3 | `kappa_report.json` (κ + confusion matrix + số câu bỏ qua) | `data/qa_pairs/labeled/` | Chứng minh độ tin cậy dataset |
| 4 | `verification_stats.json` (tỷ lệ pass/reject theo tầng) | `data/qa_pairs/labeled/` | Chứng minh quy trình có kiểm chứng, không phải sinh bừa |
| 5 | `pairs_rejected.jsonl` | `data/qa_pairs/labeled/` | Error analysis định tính — phân tích model hay sai kiểu gì |
| 6 | `docs/specificity-guideline.md` | `docs/` | Phụ lục báo cáo, minh chứng tiêu chí gán nhãn có hệ thống |

### 5.2 Lưu trữ — vấn đề `.gitignore`

`.gitignore` hiện tại chặn `*.json` và `*.jsonl` toàn cục (chỉ chừa `config/*.json`). Nghĩa là **mặc định toàn bộ deliverables sẽ không lên git**.

| Phương án | Cách làm | Trade-off |
|---|---|---|
| **A (khuyến nghị)** | Thêm exception cho riêng `data/qa_pairs/final/` | `git pull` là có dataset dùng ngay; kết quả tái lập được; nhược điểm là tăng dung lượng repo (chấp nhận được nếu vài MB) |
| B | Giữ nguyên gitignore, chia sẻ qua Google Drive, chỉ commit `stats.json` | Repo gọn, nhưng phải đồng bộ thủ công |

**Đã chọn A.** Các dòng đã thêm vào cuối `.gitignore` (chỉ **thêm dòng mới**, không xoá dòng nào có sẵn):
```gitignore
# --- QA Specificity Pipeline (Phần 3) ---
!data/qa_pairs/final/
!data/qa_pairs/final/*.json
config/qa.env
```

Đã kiểm chứng bằng `git add -n data/qa_pairs/`: chỉ `final/*.json` được track, `raw/` và `labeled/` vẫn bị chặn.

Không tạo `config/qa.env.example`: `.env` ở root đã đủ. `qa_settings.py` load `.env` trước rồi mới load `config/qa.env` nếu file đó tồn tại, nên chỉ cần thêm các biến `JUDGE_*` vào `.env` là xong. Cơ chế override vẫn còn đó phòng khi muốn tách API key ra file riêng.

---

## 6. Danh sách pitfall cần tránh

| Pitfall | Hậu quả | Cách chặn |
|---|---|---|
| Sinh broad/narrow độc lập | Shortcut learning — classifier học chủ đề thay vì độ cụ thể | Sinh cặp trong 1 lần gọi từ cùng document |
| Random split thay vì group split | Data leakage, metric ảo cao | `GroupShuffleSplit` theo `source_doc_id` + test khẳng định không giao nhau |
| Dùng cùng model sinh và judge | Self-preference bias, tầng kiểm chứng vô nghĩa | Judge bằng model khác |
| Gộp nhiều câu vào 1 prompt judge | Contamination giữa các câu | Judge từng câu một |
| Thiếu `source_doc_id`/`pair_id` từ đầu | Phải chạy lại toàn bộ pipeline | Đưa vào `schema.py` ngay commit đầu tiên |
| Gán tay sau khi đã nhìn nhãn máy | Anchoring bias, κ vô giá trị | Ẩn nhãn máy khi gán tay |
| Đổi nguồn/phạm vi mà quên `--rebuild-corpus` | Cache cũ vẫn về, thay đổi trông như vô tác dụng, **không có thông báo lỗi** | Luôn `--dry-run --rebuild-corpus` trước khi chạy thật |
| Đặt từ khoá phạm vi chung nhất lên đầu dict | `"dân sự"` khớp trước và nuốt hết nhánh cụ thể (`thi hành án dân sự`…), thống kê cân bằng chỉ còn một cột | `dan_su_chung` đứng CUỐI `CIVIL_ANCHOR_TITLES`/`CIVIL_METADATA_KEYWORDS`; đã có test giữ |
| Lọc sạch corpus vì nguồn thiếu một cột metadata | Ra 0 document, dễ tưởng code hỏng | Whitelist loại văn bản tự tắt khi thiếu `loai_van_ban`; `SCOPE_FILTER_MODE=auto` giữ nguyên corpus khi tỉ lệ lọt < 20% |
| Viết prompt trước khi viết guideline | Tiêu chí bị prompt định hình ngược | Bước 0 làm trước, không ngoại lệ |
| Nhãn lệch 80/20 | Accuracy mất ý nghĩa | Kiểm tra cân bằng ở Bước 4, đọc F1 theo từng lớp |
| Chạy tiếp khi pass rate < 40% | Đốt thời gian trên pipeline hỏng | Dừng ở checkpoint Bước 2 |