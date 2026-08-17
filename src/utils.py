"""
Tiện ích chung cho Evol-Instruct Pipeline.
- Structured logging (loguru)
- File I/O helpers (JSONL)
- Progress tracking & checkpoint/resume
"""

import json
import sys
from pathlib import Path
from datetime import datetime

from loguru import logger

from config.settings import LOG_LEVEL, LOG_DIR, BASE_DIR


# ── Logging Setup ────────────────────────────────────────────────

def setup_logging(log_file: str = "pipeline.log"):
    """Cấu hình loguru với cả console và file output."""
    # Xóa handler mặc định
    logger.remove()

    # Console handler - có màu, format ngắn gọn
    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler - chi tiết, rotation theo kích thước
    log_path = LOG_DIR / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_path),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )

    logger.info(f"Logging initialized → {log_path}")
    return logger


# ── JSONL I/O ─────────────────────────────────────────────────────

def save_jsonl(records: list[dict], filepath: str | Path, mode: str = "a"):
    """
    Ghi danh sách records vào file JSONL.

    Args:
        records: Danh sách dict cần ghi.
        filepath: Đường dẫn file JSONL.
        mode: 'a' (append) hoặc 'w' (overwrite).
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, mode, encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.debug(f"Đã ghi {len(records)} records → {filepath}")


def load_jsonl(filepath: str | Path) -> list[dict]:
    """
    Đọc file JSONL, trả về danh sách dict.

    Args:
        filepath: Đường dẫn file JSONL.

    Returns:
        Danh sách records.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        logger.warning(f"File không tồn tại: {filepath}")
        return []

    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning(f"Lỗi parse JSONL dòng {line_num}: {e}")

    logger.debug(f"Đã đọc {len(records)} records ← {filepath}")
    return records


def append_jsonl(record: dict, filepath: str | Path):
    """Ghi thêm 1 record vào file JSONL."""
    save_jsonl([record], filepath, mode="a")


# ── Checkpoint / Resume ──────────────────────────────────────────

class Checkpoint:
    """
    Quản lý checkpoint để resume pipeline khi bị gián đoạn.

    Lưu trạng thái processed_ids vào file JSON.
    """

    def __init__(self, checkpoint_file: str | Path):
        self.filepath = Path(checkpoint_file)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if self.filepath.exists():
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Checkpoint loaded: {len(data.get('processed_ids', []))} items đã xử lý")
            return data
        return {"processed_ids": [], "last_updated": None, "stats": {}}

    def save(self):
        self.data["last_updated"] = datetime.now().isoformat()
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def is_processed(self, item_id: str) -> bool:
        return item_id in self.data["processed_ids"]

    def mark_processed(self, item_id: str):
        if item_id not in self.data["processed_ids"]:
            self.data["processed_ids"].append(item_id)

    def update_stats(self, key: str, value):
        self.data["stats"][key] = value

    @property
    def processed_count(self) -> int:
        return len(self.data["processed_ids"])


# ── Text Utilities ────────────────────────────────────────────────

def truncate_text(text: str, max_length: int = 500) -> str:
    """Cắt ngắn text cho logging, giữ nguyên ý nghĩa."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"... [{len(text) - max_length} chars truncated]"


def generate_item_id(text: str) -> str:
    """Tạo ID duy nhất cho một item dựa trên nội dung."""
    import hashlib
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
