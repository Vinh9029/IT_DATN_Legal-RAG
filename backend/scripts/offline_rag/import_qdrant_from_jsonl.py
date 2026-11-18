"""
Import qdrant_vectors.jsonl vào Qdrant Cloud hoặc Qdrant Local.

Tối ưu hóa:
- Streaming từng dòng: Không ngốn 10GB RAM, khởi động upsert ngay lập tức (không chờ đọc file 12 phút).
- Tự động resume: Nhận diện điểm dừng trước đó (19,795 points...) và tiếp tục ngay lập tức.
- Auto-retry: Xử lý rớt mạng tạm thời [WinError 10054] hoặc [Errno 11001] với exponential backoff.
"""
import sys
import json
import math
import time
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from config.settings import (
    PROCESSED_DATA_DIR,
    QDRANT_HOST, QDRANT_PORT,
    QDRANT_COLLECTION_NAME,
    EMBEDDING_DIM,
    ensure_directories,
)
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from loguru import logger
from tqdm import tqdm


def stream_batches(filepath: Path, skip_count: int, batch_size: int):
    """Đọc file jsonl theo dòng (streaming) và gom thành từng batch."""
    batch = []
    line_idx = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line_idx += 1
            if line_idx <= skip_count:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                batch.append(
                    PointStruct(
                        id=rec["id"],
                        vector=rec["vector"],
                        payload=rec["payload"],
                    )
                )
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
            except Exception:
                continue
        if batch:
            yield batch


def main():
    ensure_directories()

    vectors_path = PROCESSED_DATA_DIR / "qdrant_vectors.jsonl"
    if not vectors_path.exists():
        logger.error(
            f"File {vectors_path} không tồn tại!\n"
            f"Hãy đặt file qdrant_vectors.jsonl vào: {vectors_path}"
        )
        sys.exit(1)

    # ── Kết nối Qdrant Cloud hoặc Qdrant Local ───────────────────────
    qdrant_url = os.getenv("QDRANT_URL", "").strip().strip('"').strip("'")
    qdrant_api_key = os.getenv("QDRANT_API_KEY", "").strip().strip('"').strip("'")
    if qdrant_api_key.startswith("teyJ"):
        qdrant_api_key = qdrant_api_key[1:]

    if qdrant_url:
        logger.info(f"Kết nối Qdrant Cloud (gRPC/HTTP2) tại {qdrant_url}...")
        client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key if qdrant_api_key else None,
            prefer_grpc=True,
            timeout=120,
        )
    else:
        logger.info(f"Kết nối Qdrant Local tại {QDRANT_HOST}:{QDRANT_PORT}...")
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=120)

    # ── Đảm bảo Collection tồn tại (có retry) ──────────────────────────
    existing = []
    for _ in range(5):
        try:
            existing = [c.name for c in client.get_collections().collections]
            break
        except Exception as e:
            logger.warning(f"Đang thử kết nối lại Qdrant... ({e})")
            time.sleep(3)

    existing_points = 0
    if QDRANT_COLLECTION_NAME not in existing:
        logger.info(f"Tạo collection mới: {QDRANT_COLLECTION_NAME} (dim={EMBEDDING_DIM}, cosine)")
        client.create_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
    else:
        for _ in range(3):
            try:
                info = client.get_collection(QDRANT_COLLECTION_NAME)
                existing_points = info.points_count
                break
            except Exception:
                time.sleep(2)
        logger.info(f"Collection '{QDRANT_COLLECTION_NAME}' đã có sẵn {existing_points:,} points.")

    TOTAL_RECORDS = 551020
    BATCH_SIZE = 128  # Batch 128 gửi qua Cloud rất ổn định, không bị nghẽn socket

    # Resume chính xác
    skip_records = existing_points
    if skip_records > 0:
        logger.success(f"Resume tự động: Đã có {skip_records:,} points, bỏ qua và nạp tiếp từ point {skip_records+1:,}...")

    remaining = max(0, TOTAL_RECORDS - skip_records)
    total_batches = math.ceil(remaining / BATCH_SIZE)

    logger.info(f"Bắt đầu stream và upsert {remaining:,} points còn lại ({total_batches:,} batches)...")

    pbar = tqdm(total=total_batches, desc="Upserting Cloud", unit="batch")

    for batch in stream_batches(vectors_path, skip_count=skip_records, batch_size=BATCH_SIZE):
        max_retries = 5
        for attempt in range(max_retries):
            try:
                client.upsert(collection_name=QDRANT_COLLECTION_NAME, points=batch)
                pbar.update(1)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 3 * (attempt + 1)
                    logger.warning(
                        f"Mạng chập chờn ({e.__class__.__name__}). Thử lại lần {attempt+2}/{max_retries} sau {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    pbar.close()
                    raise

    pbar.close()
    final = client.get_collection(QDRANT_COLLECTION_NAME)
    dashboard_url = f"{qdrant_url}/dashboard" if qdrant_url else f"http://{QDRANT_HOST}:{QDRANT_PORT}/dashboard"
    logger.success(
        f"✅ Import hoàn tất 100%! Tổng {final.points_count:,} points trong collection '{QDRANT_COLLECTION_NAME}'.\n"
        f"   Kiểm tra Dashboard: {dashboard_url}"
    )


if __name__ == "__main__":
    main()
