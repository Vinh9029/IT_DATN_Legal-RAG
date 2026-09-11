"""
Cấu hình riêng cho QA Specificity Pipeline (Phần 3).

CỐ Ý KHÔNG import biến nội bộ từ `config/settings.py`:
`settings.py` là file trung tâm còn được sửa thường xuyên; tách riêng đổi lấy
vài dòng boilerplate lặp lại để chi phí merge conflict bằng 0.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ── Base ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# `.env` chung của repo; `config/qa.env` (nếu có) ghi đè cho riêng Phần 3.
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "config" / "qa.env", override=True)


# ── Generator LLM (LM Studio local) ───────────────────────────────
# Đọc lại từ env thay vì import từ settings.py — xem docstring đầu file.
GEN_LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
GEN_LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")
GEN_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "meta-llama-3.1-8b-instruct")
GEN_TEMPERATURE = float(os.getenv("QA_GEN_TEMPERATURE", "0.8"))
GEN_MAX_TOKENS = int(os.getenv("QA_GEN_MAX_TOKENS", "512"))


# ── Judge LLM (BẮT BUỘC khác model sinh — xem spec §3.1) ──────────
# Nếu không set, fallback về generator: pipeline vẫn chạy nhưng
# validate_qa_config() sẽ cảnh báo self-preference bias.
JUDGE_LLM_BASE_URL = os.getenv("JUDGE_LLM_BASE_URL", GEN_LLM_BASE_URL)
JUDGE_LLM_API_KEY = os.getenv("JUDGE_LLM_API_KEY", GEN_LLM_API_KEY)
JUDGE_MODEL_NAME = os.getenv("JUDGE_MODEL_NAME", GEN_MODEL_NAME)
JUDGE_TEMPERATURE = float(os.getenv("JUDGE_TEMPERATURE", "0.0"))
JUDGE_MAX_TOKENS = int(os.getenv("JUDGE_MAX_TOKENS", "1024"))

# Với REASONING MODEL (Gemma-4, Qwen3, DeepSeek-R1...), model tiêu token cho
# kênh suy luận TRƯỚC rồi mới ghi JSON vào `content`. Đo thực tế Gemma-4-12b
# trên prompt judge: 966 / 1022 / 2276 / >3069 token suy luận cho 4 câu khác
# nhau — đuôi dài không chặn được bằng cách nâng max_tokens, câu nào lỡ vượt
# ngưỡng thì `content` về RỖNG và mất nhãn.
#
# `reasoning_effort="none"` đưa số token suy luận về 0 và JSON ra ngay. Việc
# chấm nhãn ở đây là áp một rubric 3 trục đã viết sẵn, không phải bài toán cần
# suy luận nhiều bước — nên tắt suy luận gần như không mất chất lượng, đổi lại
# nhanh hơn nhiều lần và không còn mất nhãn.
#
# Để rỗng nếu judge KHÔNG phải reasoning model, hoặc server không nhận tham số
# này (`JudgeClient` cũng tự phát hiện và bỏ qua khi server từ chối).
JUDGE_REASONING_EFFORT = os.getenv("JUDGE_REASONING_EFFORT", "none")


# ── Preset: chạy judge trên Gemini (tuỳ chọn, KHÔNG bật mặc định) ─
# Gemini có lớp OpenAI-compatible, mà `JudgeClient` vốn đã dựng trên `openai`
# SDK — nên đổi judge sang Gemini là việc CỦA CẤU HÌNH, không phải của code.
# Đặt 3 dòng sau vào `config/qa.env` là xong:
#
#   JUDGE_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
#   JUDGE_LLM_API_KEY=<GEMINI_API_KEY>
#   JUDGE_MODEL_NAME=gemini-2.5-flash
#
# Vì sao đáng đổi: generator là Llama-3.1-8B chạy local, judge là Gemini —
# hai model khác hẳn nhà cung cấp, nên lập luận "không có self-preference
# bias" ở spec §3.1 vững hơn hẳn so với gemma local.
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


# ── Tham số cho `11_verify_labels.py --estimate-cost` ─────────────
# Đơn giá USD / 1 triệu token. Mặc định theo bảng giá công bố của
# gemini-2.5-flash; GIÁ CÓ THỂ ĐỔI — tra lại tại thời điểm chạy và override
# bằng env nếu cần, đừng trích thẳng con số này vào báo cáo.
JUDGE_PRICE_INPUT_PER_M = float(os.getenv("QA_JUDGE_PRICE_INPUT_PER_M", "0.30"))
JUDGE_PRICE_OUTPUT_PER_M = float(os.getenv("QA_JUDGE_PRICE_OUTPUT_PER_M", "2.50"))

# Output judge là một object JSON ngắn (label + reason cắt 200 ký tự + 3 trục).
JUDGE_EST_OUTPUT_TOKENS = int(os.getenv("QA_JUDGE_EST_OUTPUT_TOKENS", "80"))

# Tiếng Việt tốn token hơn tiếng Anh nhiều: ~2,5 ký tự/token chứ không phải 4
# (spec §3.2). Ước lượng theo ký tự là CỐ Ý — đếm token chính xác cần gọi API,
# mà mục đích của `--estimate-cost` chính là biết trước khi gọi.
CHARS_PER_TOKEN_VI = float(os.getenv("QA_CHARS_PER_TOKEN_VI", "2.5"))


def judge_is_remote() -> bool:
    """True khi judge trỏ ra API trả phí bên ngoài (không phải server local)."""
    url = (JUDGE_LLM_BASE_URL or "").lower()
    return not any(host in url for host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"))


# ══════════════════════════════════════════════════════════════════
# NGUỒN DỮ LIỆU
# ══════════════════════════════════════════════════════════════════
# Corpus vào Phần 3 qua MỘT trong hai đường, theo thứ tự ưu tiên:
#
#   1. THƯ MỤC CỤC BỘ `QA_CORPUS_SOURCE` — đường CHÍNH kể từ khi nhóm chốt
#      đổi sang nguồn luật dân sự riêng. Thả file vào thư mục là chạy; định
#      dạng nào cũng đọc được (xem `src/qa_specificity/corpus_loader.py`).
#   2. HuggingFace dataset — đường CŨ, giữ lại làm dự phòng để pipeline vẫn
#      chạy được trong lúc chưa có nguồn mới.
#
# Thư mục không tồn tại hoặc không có file nào đọc được ⇒ tự động rơi về (2).
CORPUS_SOURCE = BASE_DIR / os.getenv("QA_CORPUS_SOURCE", "data/corpus_civil")

# Mặc định hai nguồn LOẠI TRỪ nhau: có file cục bộ thì HuggingFace không được
# đụng tới. Bật cờ này để GỘP cả hai — corpus cục bộ (file tự tải: .pdf, .doc,
# .docx...) đứng trước, dataset HF bù thêm phần còn thiếu.
#
# Vì sao không bật mặc định: corpus cục bộ là nguồn đã chọn tay nên sạch, còn
# HF là nguồn cũ rộng hơn phạm vi. Gộp vào là đổi lấy SỐ LƯỢNG bằng ĐỘ THUẦN,
# và đó phải là quyết định có ý thức, ghi được vào báo cáo — không phải thứ tự
# xảy ra vì thư mục tình cờ rỗng.
CORPUS_MERGE_HF = os.getenv("QA_CORPUS_MERGE_HF", "0").strip().lower() in (
    "1", "true", "yes", "on"
)

# Định dạng `corpus_loader` đọc được. Phải khớp với `_READERS` trong file đó
# (có assert kiểm tra), nằm ở đây để thông báo lỗi có chỗ mà tra.
SUPPORTED_SUFFIXES = [
    ".jsonl", ".ndjson", ".json", ".csv", ".tsv",
    ".xlsx", ".xlsm",
    ".docx", ".doc", ".rtf", ".pdf",
    ".txt", ".md", ".html", ".htm", ".parquet",
]

# Bí danh tên cột. Nguồn mới gần như chắc chắn đặt tên cột khác nguồn cũ, nên
# thay vì sửa code thì khai thêm bí danh ở đây. So khớp sau khi đã BỎ DẤU và
# thường hoá (`corpus_loader._slug`), nên "Nội dung" khớp `noi_dung`, "Số ký
# hiệu" khớp `so_ky_hieu` — không cần khai bản có dấu.
FIELD_ALIASES = {
    "id": ["id", "doc_id", "document_id", "ma_van_ban", "ma_so", "stt"],
    "content": ["content", "content_html", "noi_dung", "text", "full_text",
                "body", "van_ban", "noi_dung_van_ban", "plain_text"],
    "title": ["title", "tieu_de", "ten_van_ban", "trich_yeu", "ten", "name"],
    "so_hieu": ["so_ky_hieu", "so_hieu", "so_van_ban", "ky_hieu", "so", "number"],
    "loai_van_ban": ["loai_van_ban", "loai", "the_loai", "doc_type", "type"],
    "nganh": ["nganh", "linh_vuc_nganh", "sector"],
    "linh_vuc": ["linh_vuc", "chu_de", "topic", "domain", "category", "field"],
    "co_quan_ban_hanh": ["co_quan_ban_hanh", "co_quan", "noi_ban_hanh", "issuer"],
    "ngay_ban_hanh": ["ngay_ban_hanh", "ngay_ky", "ngay", "date"],
    "tinh_trang_hieu_luc": ["tinh_trang_hieu_luc", "tinh_trang", "hieu_luc", "status"],
}

# Đường dự phòng: dataset HuggingFace có 5 config. Metadata
# (nganh/linh_vuc/loai_van_ban) và nội dung nằm ở HAI config khác nhau, join
# với nhau qua trường `id`:
#   - config "metadata": id, title, so_ky_hieu, loai_van_ban, nganh, linh_vuc, ...
#   - config "content" : id, content_html   ← CHỈ có 2 cột, KHÔNG có metadata
# `config/settings.py` đặt HF_DATASET_CONFIG=content, nên
# `data_loader.load_and_preprocess()` trả về metadata RỖNG TOÀN BỘ. Phần 3 phải
# tự join hai config, xem `src/qa_specificity/corpus_filter.py`.
HF_DATASET_NAME = os.getenv("HF_DATASET_NAME", "th1nhng0/vietnamese-legal-documents")
HF_CONFIG_METADATA = os.getenv("QA_HF_CONFIG_METADATA", "metadata")
HF_CONFIG_CONTENT = os.getenv("QA_HF_CONFIG_CONTENT", "content")


# ══════════════════════════════════════════════════════════════════
# PHẠM VI: LUẬT DÂN SỰ VÀ CÁC CHẾ ĐỊNH LÂN CẬN
# ══════════════════════════════════════════════════════════════════
# Nhóm đã chốt đi theo CHIỀU SÂU một lĩnh vực thay vì chiều rộng (bỏ lao động,
# thương mại...). Lập luận cho báo cáo: giữ chủ đề hẹp làm giảm biến nhiễu, nên
# thứ classifier học được chắc chắn là ĐỘ CỤ THỂ chứ không phải chủ đề.
#
# Cách nhận diện đi theo hai đường, vì nguồn nào cũng có thể thiếu metadata:
#   - `CIVIL_ANCHOR_TITLES` : khớp trên TIÊU ĐỀ văn bản. Đường chính — tiêu đề
#     luôn có, còn `nganh`/`linh_vuc` thì nguồn mới có thể không có.
#   - `CIVIL_METADATA_KEYWORDS` : khớp trên `nganh` + `linh_vuc` nếu nguồn có.
# Khớp bất kỳ đường nào là lọt. Nhánh con dùng để thống kê cân bằng, KHÔNG
# phải nhãn của bài toán — nhãn vẫn chỉ là broad/narrow.
#
# ⚠️ THỨ TỰ TRONG DICT LÀ CÓ Ý NGHĨA: `scope_of` trả về nhánh khớp ĐẦU TIÊN,
# nên nhánh chung nhất (`dan_su_chung`, từ khoá "dân sự") phải đứng CUỐI. Đặt
# nó lên đầu thì "Thi hành án dân sự" khớp "dân sự" trước và mọi nhánh cụ thể
# hơn đều bị nuốt — thống kê cân bằng khi đó chỉ còn một cột.
CIVIL_ANCHOR_TITLES = {
    "to_tung_thi_hanh_an": ["tố tụng dân sự", "thi hành án dân sự"],
    "hon_nhan_gia_dinh": ["hôn nhân và gia đình", "hôn nhân gia đình",
                          "luật con nuôi", "nuôi con nuôi",
                          "luật hộ tịch", "luật quốc tịch"],
    "thua_ke": ["thừa kế", "di chúc"],
    "dat_dai_nha_o": ["luật đất đai", "luật nhà ở", "kinh doanh bất động sản",
                      "quyền sử dụng đất", "bồi thường, hỗ trợ, tái định cư"],
    "so_huu_tri_tue": ["sở hữu trí tuệ", "quyền tác giả", "sở hữu công nghiệp"],
    "hop_dong_bao_dam": ["giao dịch bảo đảm", "biện pháp bảo đảm", "luật công chứng"],
    "giai_quyet_tranh_chap": ["trọng tài thương mại", "hoà giải ở cơ sở",
                              "hòa giải ở cơ sở", "hoà giải thương mại",
                              "hòa giải thương mại"],
    "boi_thuong": ["bồi thường nhà nước", "trách nhiệm bồi thường"],
    # Nhánh chung nhất — phải đứng CUỐI, xem chú thích trên
    "dan_su_chung": ["bộ luật dân sự", "luật dân sự"],
}

# Cùng quy tắc thứ tự: nhánh chung nhất đứng cuối.
CIVIL_METADATA_KEYWORDS = {
    "to_tung_thi_hanh_an": ["thi hành án dân sự", "tố tụng dân sự"],
    "hon_nhan_gia_dinh": ["hôn nhân", "hộ tịch", "quốc tịch", "con nuôi"],
    "thua_ke": ["thừa kế"],
    "dat_dai_nha_o": ["đất đai", "nhà ở", "bất động sản"],
    "so_huu_tri_tue": ["sở hữu trí tuệ"],
    "hop_dong_bao_dam": ["giao dịch bảo đảm", "công chứng", "chứng thực"],
    "giai_quyet_tranh_chap": ["trọng tài", "hoà giải", "hòa giải"],
    "boi_thuong": ["bồi thường nhà nước"],
    # Nhánh chung nhất — phải đứng CUỐI
    "dan_su_chung": ["dân sự"],
}

# Từ khoá loại trừ — mỗi dòng là một cú khớp nhầm ĐÃ ĐO ĐƯỢC trên dữ liệu
# thật, không phải đề phòng suông. Xét TRƯỚC khi so khớp phạm vi.
SCOPE_ANTI_KEYWORDS = [
    "phòng thủ dân sự",          # civil defence, không liên quan luật dân sự
    "hình sự",                   # BLTTHS lọt qua từ khoá "tố tụng"
    "tố tụng hành chính",
    "tài sản công",              # công sản/kế toán, không phải sở hữu dân sự
    "tài sản cố định",
    "tài sản kết cấu hạ tầng",
    "bạo lực gia đình",          # phòng chống bạo lực, không phải chế định HNGĐ
]

# Chỉ giữ văn bản QUY PHẠM. Dataset HF có 91k "Quyết định" và 28k "Nghị quyết",
# phần lớn là quyết định hành chính cá biệt (bổ nhiệm, phê duyệt dự án...) —
# không chứa quy phạm để hỏi đáp pháp lý. Whitelist thay vì blacklist vì
# blacklist sẽ phải liệt kê 31 loại để loại đúng vài loại cần giữ.
#
# Bộ lọc này TỰ TẮT khi nguồn không có trường `loai_van_ban` — nguồn tải tay
# thường không có, và loại sạch corpus vì thiếu một cột metadata là cách hỏng
# tệ nhất: không có thông báo lỗi nào cả.
INCLUDED_DOC_TYPES = [
    "bộ luật", "luật", "pháp lệnh", "nghị định",
    "thông tư", "thông tư liên tịch", "văn bản hợp nhất",
]

# Cách áp bộ lọc phạm vi:
#   "auto"   — lọc bình thường, NHƯNG nếu tỉ lệ lọt < SCOPE_AUTO_MIN_RATIO thì
#              coi như nguồn đã thuần dân sự sẵn (hoặc từ khoá không hợp với
#              nguồn này), cảnh báo rồi giữ nguyên cả corpus. Đây là mặc định,
#              và là lý do thả một dataset dân sự lạ vào cũng không ra 0 doc.
#   "strict" — lọc thẳng tay, lọt bao nhiêu lấy bấy nhiêu (kể cả 0).
#   "off"    — không lọc, chỉ gán nhánh con để thống kê. Dùng khi đã tự tay
#              chuẩn bị corpus và chắc chắn nó thuần dân sự.
SCOPE_FILTER_MODE = os.getenv("QA_SCOPE_FILTER_MODE", "auto").strip().lower()
SCOPE_AUTO_MIN_RATIO = float(os.getenv("QA_SCOPE_AUTO_MIN_RATIO", "0.20"))

# ══════════════════════════════════════════════════════════════════
# HẠN NGẠCH THEO NHÁNH — giữ dân sự làm trọng tâm
# ══════════════════════════════════════════════════════════════════
# Đo được khi bật QA_CORPUS_MERGE_HF=1: corpus ra 16.400 Điều, nhưng đất
# đai/nhà ở chiếm 4.554 và tố tụng 3.984, còn thừa kế chỉ 126. Hai nhánh luật
# chuyên ngành lấn át đúng cái lõi mà đề tài nhắm tới.
#
# Cách hỏng ở đây KHÔNG lộ ra ở pass rate — pass rate vẫn đẹp. Nó lộ ra ở chỗ
# classifier được gọi là học "độ cụ thể" nhưng thực chất học trên một phân bố
# chủ đề lệch hẳn so với phạm vi đã tuyên bố ở báo cáo. Nên phải chặn ở tầng
# corpus, không phải ở tầng nhãn.
#
# Trần dưới đây CHỈ áp cho phần BỔ SUNG (nguồn HuggingFace). Corpus cục bộ —
# BLDS + BLTTDS tự tải, là nguồn neo của đề tài — luôn giữ nguyên vẹn và không
# đếm vào trần.
#
# Con số cần ghi vào báo cáo là TỈ LỆ ba tầng, không phải trần tuyệt đối:
#   lõi dân sự (BLDS và các chế định trực thuộc)   ~74%
#   tố tụng / thi hành án (thủ tục thực thi quyền)  ~17%
#   luật chuyên ngành lân cận (phụ, để có độ phủ)    ~9%
SCOPE_QUOTAS = {
    # ── Lõi dân sự ────────────────────────────────────────────────
    "dan_su_chung": 1400,
    "hop_dong_bao_dam": 700,
    "hon_nhan_gia_dinh": 600,
    "boi_thuong": 400,
    "thua_ke": 126,              # nguồn chỉ có đúng 126 Điều — lấy hết
    # ── Thủ tục ───────────────────────────────────────────────────
    "to_tung_thi_hanh_an": 400,
    # ── Phụ / extra ───────────────────────────────────────────────
    # Có mặt để corpus không hụt hẳn các chế định lân cận, nhưng không được
    # lấn lõi. Đất đai bị siết mạnh nhất (4.554 → 200) vì đo ra nó chính là
    # nhánh lan man nhất.
    "dat_dai_nha_o": 200,
    "so_huu_tri_tue": 130,
    "giai_quyet_tranh_chap": 100,
}

# Nhánh không có tên trong `SCOPE_QUOTAS` (kể cả "unknown") dùng trần này. Đặt
# thấp là CỐ Ý: nhánh lạ xuất hiện nghĩa là từ khoá phạm vi chưa phủ hết nguồn
# — lúc đó nó nên vào đủ ít để còn nhìn thấy trong log, chứ không vào ồ ạt.
SCOPE_QUOTA_DEFAULT = int(os.getenv("QA_SCOPE_QUOTA_DEFAULT", "100"))

# Đổi quy mô không cần sửa code: QA_SCOPE_QUOTAS="dan_su_chung=2000,dat_dai_nha_o=0"
_quota_override = os.getenv("QA_SCOPE_QUOTAS", "").strip()
if _quota_override:
    for _entry in _quota_override.split(","):
        if "=" not in _entry:
            continue
        _key, _value = _entry.split("=", 1)
        SCOPE_QUOTAS[_key.strip()] = int(_value.strip())

# Tắt để lấy TRỌN phần bổ sung. Chỉ nên tắt khi cố ý muốn corpus rộng và chấp
# nhận tự giải trình phân bố lệch ở phần Limitations.
SCOPE_QUOTA_ENABLED = os.getenv("QA_SCOPE_QUOTA_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on"
)

# Nhánh nào được tính là "lõi dân sự" khi log tỉ lệ ba tầng. Chỉ dùng để BÁO
# CÁO, không tham gia lọc — nên sửa ở đây không đổi corpus, chỉ đổi con số in ra.
SCOPE_CORE_BRANCHES = [
    "dan_su_chung", "hop_dong_bao_dam", "hon_nhan_gia_dinh",
    "boi_thuong", "thua_ke",
]

MIN_CONTENT_LENGTH = int(os.getenv("QA_MIN_CONTENT_LENGTH", "500"))
MAX_DOC_CHARS = int(os.getenv("QA_MAX_DOC_CHARS", "2000"))  # cắt context như seed_generator


# ── Cắt theo Điều ─────────────────────────────────────────────────
# Phạm vi sâu = ít văn bản nhưng rất dài (Bộ luật Dân sự 2015: 689 Điều). Bật
# cờ này để mỗi Điều thành một nguồn sinh cặp riêng, thay vì mỗi văn bản chỉ
# ra đúng 1 cặp từ 2.000 ký tự đầu (mà 2.000 ký tự đầu của một bộ luật thì
# toàn phần "Căn cứ...").
#
# Mặc định TẮT: chưa biết nguồn mới có đánh số theo Điều hay không. Chạy
# `scripts/10_generate_qa_pairs.py --dry-run` để xem cắt được bao nhiêu rồi
# hãy bật. Bật xong nhớ xoá cache corpus (`--rebuild-corpus`).
SPLIT_BY_ARTICLE = os.getenv("QA_SPLIT_BY_ARTICLE", "0").strip().lower() in (
    "1", "true", "yes", "on"
)
# Điều quá ngắn ("Điều 3. Giải thích từ ngữ" chỉ có một dòng dẫn) không đủ nội
# dung để sinh nổi một cặp broad/narrow.
ARTICLE_MIN_LENGTH = int(os.getenv("QA_ARTICLE_MIN_LENGTH", "300"))


# ── Ép kiểu câu narrow cho một lần chạy ───────────────────────────
# Mặc định rỗng: `pick_narrow_mode()` bốc theo hash doc_id, luân phiên ~50/50.
# Đặt "situation" hoặc "citation" để ép cả mẻ về MỘT kiểu.
#
# Vì sao cần: sinh 50/50 nhưng khâu kiểm chứng loại citation 23,6% còn situation
# 71,1%, nên tập verified ra 68,5/31,5 — lệch hẳn về phía citation. Mà đo trên
# tập test thì một regex "có số Điều ⇒ narrow" đã đạt 99,5% trên nhánh citation
# và chỉ 49,5% trên nhánh situation: phần dữ liệu thực sự bắt model học ngữ
# nghĩa nằm ở situation, và pipeline đang vứt đi đúng phần đó.
#
# Bù lại bằng cách sinh riêng một mẻ situation rồi gộp vào — không sinh lại
# citation (nhánh đó pass 76%, đang thừa). Cờ này là cách nói "mẻ này chỉ
# situation" mà không phải sờ vào `pick_narrow_mode`.
FORCE_NARROW_MODE = os.getenv("QA_FORCE_NARROW_MODE", "").strip().lower()


# ── Đọc PDF ───────────────────────────────────────────────────────
# PDF không lưu "văn bản", nó lưu VỊ TRÍ CỦA TỪNG KÝ TỰ. Nên trích ra được thứ
# gì phụ thuộc hoàn toàn vào cách file được tạo, và có hai kiểu hỏng khác nhau:
#
#   1. PDF SCAN (ảnh chụp) — trích ra gần như 0 ký tự. Không phải lỗi code,
#      cần OCR. Ngưỡng dưới đây là để PHÁT HIỆN và báo, thay vì im lặng nạp
#      một văn bản rỗng rồi để nó bị loại vì "content quá ngắn".
#   2. PDF text nhưng bố cục theo trang — mỗi trang kéo theo header/footer,
#      số trang, và câu bị cắt giữa chừng ở cuối dòng.
PDF_MIN_CHARS_PER_PAGE = int(os.getenv("QA_PDF_MIN_CHARS_PER_PAGE", "50"))

# Nối lại các dòng bị PDF cắt giữa câu. Tắt nếu thấy nối nhầm trên nguồn lạ.
PDF_REFLOW = os.getenv("QA_PDF_REFLOW", "1").strip().lower() in ("1", "true", "yes", "on")

# Dòng lặp lại trên >= tỉ lệ này số trang thì coi là header/footer chạy suốt
# văn bản và bị bỏ. Chỉ áp dụng khi file có >= 3 trang.
PDF_HEADER_REPEAT_RATIO = float(os.getenv("QA_PDF_HEADER_REPEAT_RATIO", "0.6"))


# ── Heuristic weak labeler (guideline §6) ─────────────────────────
# ≥ NARROW_SIGNAL_THRESHOLD tín hiệu narrow ⇒ narrow
# 0 tín hiệu narrow                        ⇒ broad
# đúng 1 tín hiệu                          ⇒ ambiguous (nhường quyết định cho tầng khác)
NARROW_SIGNAL_THRESHOLD = int(os.getenv("QA_NARROW_SIGNAL_THRESHOLD", "2"))
SHORT_QUESTION_WORDS = int(os.getenv("QA_SHORT_QUESTION_WORDS", "15"))


# ── Split (spec §4 bước 4) ────────────────────────────────────────
TRAIN_RATIO = float(os.getenv("QA_TRAIN_RATIO", "0.70"))
VAL_RATIO = float(os.getenv("QA_VAL_RATIO", "0.15"))
TEST_RATIO = float(os.getenv("QA_TEST_RATIO", "0.15"))
RANDOM_SEED = int(os.getenv("QA_RANDOM_SEED", "42"))

# Số câu lấy mẫu cho vòng gán tay tính Cohen's kappa (spec bước 3)
MANUAL_SAMPLE_SIZE = int(os.getenv("QA_MANUAL_SAMPLE_SIZE", "100"))


# ── Output paths ──────────────────────────────────────────────────
QA_DATA_DIR = BASE_DIR / os.getenv("QA_DATA_DIR", "data/qa_pairs")
QA_RAW_DIR = QA_DATA_DIR / "raw"

# .doc (Word nhị phân đời cũ) phải convert sang .docx mới đọc được. Bản convert
# nằm NGOÀI thư mục corpus — để trong đó thì `rglob` quét lại chính nó và mỗi
# văn bản vào corpus hai lần.
CONVERTED_DOC_DIR = QA_RAW_DIR / "converted_doc"
QA_LABELED_DIR = QA_DATA_DIR / "labeled"
QA_FINAL_DIR = QA_DATA_DIR / "final"
LOG_DIR = BASE_DIR / "logs"

SCOPED_CORPUS_CACHE = QA_RAW_DIR / "scoped_corpus.jsonl"
PAIRS_FILE = QA_RAW_DIR / "pairs.jsonl"
GENERATION_CHECKPOINT = QA_RAW_DIR / "generation_checkpoint.json"

VERIFIED_FILE = QA_LABELED_DIR / "pairs_verified.jsonl"
REJECTED_FILE = QA_LABELED_DIR / "pairs_rejected.jsonl"
VERIFICATION_STATS_FILE = QA_LABELED_DIR / "verification_stats.json"
JUDGE_CACHE_FILE = QA_LABELED_DIR / "judge_cache.jsonl"
MANUAL_SAMPLE_FILE = QA_LABELED_DIR / "manual_sample_blind.jsonl"

TRAIN_FILE = QA_FINAL_DIR / "train.json"
VAL_FILE = QA_FINAL_DIR / "val.json"
TEST_FILE = QA_FINAL_DIR / "test.json"
STATS_FILE = QA_FINAL_DIR / "stats.json"


# ── Ngưỡng quyết định của spec §4 bước 2 ──────────────────────────
PASS_RATE_GOOD = 0.70   # > 70%  → đi tiếp
PASS_RATE_ABORT = 0.40  # < 40%  → dừng, sửa prompt/tiêu chí


def ensure_qa_directories():
    """Tạo toàn bộ thư mục của Phần 3 nếu chưa tồn tại."""
    # `CORPUS_SOURCE` được tạo sẵn cả khi còn rỗng: có thư mục nhìn thấy được
    # thì người dùng biết thả dataset mới vào đâu.
    for directory in (CORPUS_SOURCE, QA_RAW_DIR, QA_LABELED_DIR, QA_FINAL_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def validate_qa_config() -> list[str]:
    """
    Kiểm tra cấu hình Phần 3.

    Returns:
        Danh sách cảnh báo (không chặn chạy).

    Raises:
        ValueError: khi có lỗi cấu hình thực sự.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not GEN_LLM_BASE_URL:
        errors.append("LLM_BASE_URL không được để trống")
    if not JUDGE_LLM_BASE_URL:
        errors.append("JUDGE_LLM_BASE_URL không được để trống")

    for name, value in (("GEN_TEMPERATURE", GEN_TEMPERATURE),
                        ("JUDGE_TEMPERATURE", JUDGE_TEMPERATURE)):
        if not 0.0 <= value <= 2.0:
            errors.append(f"{name} ({value}) phải trong khoảng [0, 2]")

    ratio_sum = TRAIN_RATIO + VAL_RATIO + TEST_RATIO
    if abs(ratio_sum - 1.0) > 1e-6:
        errors.append(
            f"QA_TRAIN_RATIO + QA_VAL_RATIO + QA_TEST_RATIO = {ratio_sum:.4f}, phải bằng 1.0"
        )
    if min(TRAIN_RATIO, VAL_RATIO, TEST_RATIO) <= 0:
        errors.append("Các tỷ lệ split đều phải > 0")

    if NARROW_SIGNAL_THRESHOLD < 1:
        errors.append(f"QA_NARROW_SIGNAL_THRESHOLD ({NARROW_SIGNAL_THRESHOLD}) phải >= 1")

    if MAX_DOC_CHARS < 500:
        errors.append(f"QA_MAX_DOC_CHARS ({MAX_DOC_CHARS}) quá nhỏ, khuyến nghị >= 500")

    if SCOPE_FILTER_MODE not in ("auto", "strict", "off"):
        errors.append(
            f"QA_SCOPE_FILTER_MODE={SCOPE_FILTER_MODE!r} không hợp lệ, "
            f"phải là 'auto', 'strict' hoặc 'off'"
        )
    if not 0.0 <= SCOPE_AUTO_MIN_RATIO <= 1.0:
        errors.append(
            f"QA_SCOPE_AUTO_MIN_RATIO ({SCOPE_AUTO_MIN_RATIO}) phải trong khoảng [0, 1]"
        )

    negative_quotas = {k: v for k, v in SCOPE_QUOTAS.items() if v < 0}
    if negative_quotas:
        errors.append(f"SCOPE_QUOTAS có trần âm: {negative_quotas} (0 = bỏ hẳn nhánh)")
    if SCOPE_QUOTA_DEFAULT < 0:
        errors.append(f"QA_SCOPE_QUOTA_DEFAULT ({SCOPE_QUOTA_DEFAULT}) phải >= 0")

    # Trần chỉ áp cho phần bổ sung, nên bật trần mà không gộp nguồn là vô hiệu.
    # Cảnh báo để khỏi mất công đi tìm xem trần "không có tác dụng" ở đâu.
    if SCOPE_QUOTA_ENABLED and not CORPUS_MERGE_HF:
        warnings.append(
            "SCOPE_QUOTA_ENABLED=1 nhưng QA_CORPUS_MERGE_HF=0 → không có nguồn bổ sung "
            "nào để áp trần, hạn ngạch theo nhánh sẽ không làm gì cả."
        )

    # Cảnh báo sớm về nguồn dữ liệu: rẻ hơn nhiều so với việc phát hiện ở giữa
    # một mẻ chạy đã gọi vài trăm lượt LLM.
    from evol_instruct.src.qa_specificity.corpus_loader import has_local_corpus

    if not has_local_corpus(CORPUS_SOURCE):
        warnings.append(
            f"Chưa có file corpus nào ở {CORPUS_SOURCE} → rơi về dataset HuggingFace "
            f"({HF_DATASET_NAME}), là nguồn CŨ chứa cả lao động lẫn dân sự. Thả dataset "
            f"dân sự mới vào thư mục đó ({', '.join(SUPPORTED_SUFFIXES)}) rồi chạy lại "
            f"với --rebuild-corpus."
        )

    # Cảnh báo, không phải lỗi — spec §3.1 cho phép phương án dự phòng
    if (JUDGE_MODEL_NAME == GEN_MODEL_NAME
            and JUDGE_LLM_BASE_URL == GEN_LLM_BASE_URL):
        warnings.append(
            "Judge model TRÙNG model sinh → self-preference bias, tầng kiểm chứng suy yếu. "
            "Set JUDGE_MODEL_NAME / JUDGE_LLM_BASE_URL / JUDGE_LLM_API_KEY trong .env "
            "(khuyến nghị gpt-4o-mini hoặc gemini-flash). Nếu buộc dùng phương án dự phòng, "
            "phải nêu rõ hạn chế này trong phần Limitations của báo cáo."
        )

    if judge_is_remote():
        warnings.append(
            f"Judge đang trỏ ra API ngoài ({JUDGE_LLM_BASE_URL}) → mỗi câu hỏi là một "
            f"lượt gọi TRẢ PHÍ. Chạy "
            f"`python scripts/11_verify_labels.py --estimate-cost` để xem chi phí trước."
        )

    if JUDGE_TEMPERATURE > 0.3:
        warnings.append(
            f"JUDGE_TEMPERATURE={JUDGE_TEMPERATURE} khá cao; judge nên gần tất định (0.0-0.2)."
        )

    if errors:
        raise ValueError("Lỗi cấu hình QA pipeline:\n" + "\n".join(f"  - {e}" for e in errors))

    return warnings
