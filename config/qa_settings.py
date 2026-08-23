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


# ── Nguồn dữ liệu ─────────────────────────────────────────────────
# Dataset có 5 config. Metadata (nganh/linh_vuc/loai_van_ban) và nội dung nằm
# ở HAI config khác nhau, join với nhau qua trường `id`:
#   - config "metadata": id, title, so_ky_hieu, loai_van_ban, nganh, linh_vuc, ...
#   - config "content" : id, content_html   ← CHỈ có 2 cột, KHÔNG có metadata
# `config/settings.py` của Vinh đặt HF_DATASET_CONFIG=content, nên
# `data_loader.load_and_preprocess()` trả về metadata RỖNG TOÀN BỘ. Phần 3 phải
# tự join hai config, xem `src/qa_specificity/corpus_filter.py`.
HF_DATASET_NAME = os.getenv("HF_DATASET_NAME", "th1nhng0/vietnamese-legal-documents")
HF_CONFIG_METADATA = os.getenv("QA_HF_CONFIG_METADATA", "metadata")
HF_CONFIG_CONTENT = os.getenv("QA_HF_CONFIG_CONTENT", "content")


# ── Phạm vi corpus: lao động + dân sự ─────────────────────────────
# So khớp không phân biệt hoa/thường trên metadata `nganh` + `linh_vuc`.
# Từ khoá dưới đây đã đối chiếu với giá trị THẬT trong dataset, không phải đoán.
SCOPE_KEYWORDS = {
    # khớp: "Lao động - Thương binh và Xã hội", "Lao động, tiền lương, tiền công",
    #       "An toàn lao động", "Lao động ngoài nước", "Việc làm", "Bảo hiểm xã hội"
    "lao_dong": ["lao động", "việc làm", "tiền lương", "tiền công",
                 "bảo hiểm xã hội", "công đoàn"],
    # khớp: "Thi hành án dân sự", "Dân sự - Kinh tế", "Tố tụng dân sự", "Sở hữu trí tuệ"
    "dan_su": ["dân sự", "hợp đồng", "sở hữu", "thừa kế", "hôn nhân"],
}

# "Phòng thủ dân sự" (civil defence) khớp nhầm từ khoá "dân sự" nhưng không
# liên quan gì tới luật dân sự.
SCOPE_ANTI_KEYWORDS = ["phòng thủ dân sự"]

# Chỉ giữ văn bản QUY PHẠM. Dataset có 91k "Quyết định" và 28k "Nghị quyết",
# phần lớn là quyết định hành chính cá biệt (bổ nhiệm, phê duyệt dự án...) —
# không chứa quy phạm để hỏi đáp pháp lý. Whitelist thay vì blacklist vì
# blacklist sẽ phải liệt kê 31 loại để loại đúng vài loại cần giữ.
INCLUDED_DOC_TYPES = [
    "bộ luật", "luật", "pháp lệnh", "nghị định",
    "thông tư", "thông tư liên tịch", "văn bản hợp nhất",
]

MIN_CONTENT_LENGTH = int(os.getenv("QA_MIN_CONTENT_LENGTH", "500"))
MAX_DOC_CHARS = int(os.getenv("QA_MAX_DOC_CHARS", "2000"))  # cắt context như seed_generator


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
    """Tạo toàn bộ thư mục output của Phần 3 nếu chưa tồn tại."""
    for directory in (QA_RAW_DIR, QA_LABELED_DIR, QA_FINAL_DIR, LOG_DIR):
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

    # Cảnh báo, không phải lỗi — spec §3.1 cho phép phương án dự phòng
    if (JUDGE_MODEL_NAME == GEN_MODEL_NAME
            and JUDGE_LLM_BASE_URL == GEN_LLM_BASE_URL):
        warnings.append(
            "Judge model TRÙNG model sinh → self-preference bias, tầng kiểm chứng suy yếu. "
            "Set JUDGE_MODEL_NAME / JUDGE_LLM_BASE_URL / JUDGE_LLM_API_KEY trong .env "
            "(khuyến nghị gpt-4o-mini hoặc gemini-flash). Nếu buộc dùng phương án dự phòng, "
            "phải nêu rõ hạn chế này trong phần Limitations của báo cáo."
        )

    if JUDGE_TEMPERATURE > 0.3:
        warnings.append(
            f"JUDGE_TEMPERATURE={JUDGE_TEMPERATURE} khá cao; judge nên gần tất định (0.0-0.2)."
        )

    if errors:
        raise ValueError("Lỗi cấu hình QA pipeline:\n" + "\n".join(f"  - {e}" for e in errors))

    return warnings
