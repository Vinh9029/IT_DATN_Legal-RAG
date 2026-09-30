"""
Import qdrant_vectors.jsonl (generated từ Kaggle) vào Qdrant Docker local.

Chạy sau khi download qdrant_vectors.jsonl từ Kaggle về:
  backend/data/rag/processed/qdrant_vectors.jsonl

Usage:
    python scripts/offline_rag/import_qdrant_from_jsonl.py
"""
import sys
import json
import math
import time
import uuid
from pathlib import Path

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


def main():
    ensure_directories()

    vectors_path = PROCESSED_DATA_DIR / "qdrant_vectors.jsonl"
    if not vectors_path.exists():
        logger.error(
            f"File {vectors_path} không tồn tại!\n"
            "Hãy download qdrant_vectors.jsonl từ Kaggle Notebook 2 và đặt vào:\n"
            f"  {vectors_path}"
        )
        sys.exit(1)

    logger.info(f"Kết nối Qdrant tại {QDRANT_HOST}:{QDRANT_PORT}...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=300)

    # Tạo hoặc tái sử dụng collection
    existing = [c.name for c in client.get_collections().collections]
    existing_points = 0
    if QDRANT_COLLECTION_NAME not in existing:
        logger.info(f"Tạo collection mới: {QDRANT_COLLECTION_NAME} (dim={EMBEDDING_DIM}, cosine)")
        client.create_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
    else:
        info = client.get_collection(QDRANT_COLLECTION_NAME)
        existing_points = info.points_count
        logger.info(f"Collection '{QDRANT_COLLECTION_NAME}' đã có {existing_points} points.")

    # Đọc toàn bộ records
    logger.info(f"Đọc {vectors_path} ...")
    records = []
    with open(vectors_path, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="Đọc vectors"):
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line, strict=False))
                except json.JSONDecodeError:
                    pass
    total = len(records)
    logger.info(f"Tổng số records: {total:,}")

    # Resume
    BATCH_SIZE = 256
    start_idx = (existing_points // BATCH_SIZE) * BATCH_SIZE
    if start_idx > 0:
        logger.info(f"Resume từ index {start_idx} (bỏ qua {start_idx} records đã có)...")

    total_batches = math.ceil((total - start_idx) / BATCH_SIZE)

    for i in tqdm(range(start_idx, total, BATCH_SIZE), total=total_batches, desc="Upserting"):
        batch = records[i : i + BATCH_SIZE]
        points = [
            PointStruct(
                id=rec["id"],
                vector=rec["vector"],
                payload=rec["payload"],
            )
            for rec in batch
        ]
        for attempt in range(3):
            try:
                client.upsert(collection_name=QDRANT_COLLECTION_NAME, points=points)
                break
            except Exception as e:
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Upsert lỗi (lần {attempt+1}/3): {e}. Thử lại sau {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    final = client.get_collection(QDRANT_COLLECTION_NAME)
    logger.success(
        f"✅ Import xong! Tổng {final.points_count:,} points trong collection '{QDRANT_COLLECTION_NAME}'.\n"
        "   Kiểm tra: http://localhost:6333/dashboard"
    )


if __name__ == "__main__":
    main()
