"""
Cấu hình hệ thống - Load biến môi trường và validation.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# ── LLM API Configuration ──────────────────────────────────────────
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "meta-llama-3.1-8b-instruct")

# ── Temperature Strategy ───────────────────────────────────────────
EVOL_TEMPERATURE = float(os.getenv("EVOL_TEMPERATURE", "0.85"))
ANSWER_TEMPERATURE = float(os.getenv("ANSWER_TEMPERATURE", "0.1"))

# ── Generation Parameters ─────────────────────────────────────────
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2048"))
TOP_P = float(os.getenv("TOP_P", "0.9"))
CONTEXT_LENGTH = int(os.getenv("CONTEXT_LENGTH", "8192"))

# ── HuggingFace Dataset ───────────────────────────────────────────
HF_DATASET_NAME = os.getenv("HF_DATASET_NAME", "th1nhng0/vietnamese-legal-documents")
HF_DATASET_CONFIG = os.getenv("HF_DATASET_CONFIG", "content")

# ── Pipeline Settings ─────────────────────────────────────────────
MAX_SEEDS = int(os.getenv("MAX_SEEDS", "0"))  # 0 = xử lý tất cả
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.95"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))

# ── Output Paths ──────────────────────────────────────────────────
OUTPUT_DIR = BASE_DIR / os.getenv("OUTPUT_DIR", "data/output")
SEEDS_DIR = BASE_DIR / os.getenv("SEEDS_DIR", "data/seeds")
RAW_DATA_DIR = BASE_DIR / os.getenv("RAW_DATA_DIR", "data/raw")
LOG_DIR = BASE_DIR / "logs"

# ── Logging ───────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/pipeline.log")

# ── LLM Stop Tokens ──────────────────────────────────────────────
STOP_TOKENS = ["<|eot_id|>"]


def ensure_directories():
    """Tạo tất cả thư mục cần thiết nếu chưa tồn tại."""
    for directory in [OUTPUT_DIR, SEEDS_DIR, RAW_DATA_DIR, LOG_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def validate_config():
    """Kiểm tra tính hợp lệ của cấu hình."""
    errors = []

    if not LLM_BASE_URL:
        errors.append("LLM_BASE_URL không được để trống")

    if EVOL_TEMPERATURE < 0 or EVOL_TEMPERATURE > 2:
        errors.append(f"EVOL_TEMPERATURE ({EVOL_TEMPERATURE}) phải trong khoảng [0, 2]")

    if ANSWER_TEMPERATURE < 0 or ANSWER_TEMPERATURE > 2:
        errors.append(f"ANSWER_TEMPERATURE ({ANSWER_TEMPERATURE}) phải trong khoảng [0, 2]")

    if MAX_TOKENS < 256:
        errors.append(f"MAX_TOKENS ({MAX_TOKENS}) quá nhỏ, khuyến nghị >= 256")

    if SIMILARITY_THRESHOLD < 0 or SIMILARITY_THRESHOLD > 1:
        errors.append(f"SIMILARITY_THRESHOLD ({SIMILARITY_THRESHOLD}) phải trong khoảng [0, 1]")

    if errors:
        raise ValueError("Lỗi cấu hình:\n" + "\n".join(f"  - {e}" for e in errors))

    return True
