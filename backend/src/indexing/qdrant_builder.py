import json
import math
import uuid
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from loguru import logger
from tqdm import tqdm

def build_qdrant_index(
    chunks_path: Path,
    host: str,
    port: int,
    collection_name: str,
    model_name: str,
    dim: int = 768,
    batch_size: int = 128
):
    """
    Đọc chunks.jsonl, encode text và nạp vào Qdrant (Docker Local).
    Hỗ trợ resume nếu bị gián đoạn bằng cách kiểm tra số points đã có.
    """
    logger.info(f"Kết nối tới Qdrant tại {host}:{port}...")
    client = QdrantClient(host=host, port=port)

    # 1. Kiểm tra / Tạo collection
    existing_collections = [c.name for c in client.get_collections().collections]
    if collection_name not in existing_collections:
        logger.info(f"Tạo collection mới: {collection_name} (dim={dim}, cosine)")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    else:
        info = client.get_collection(collection_name=collection_name)
        logger.info(f"Collection '{collection_name}' đã tồn tại (hiện có {info.points_count} points).")

    # 2. Load Embedding Model
    logger.info(f"Load embedding model: {model_name}")
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Sử dụng thiết bị embedding: {device.upper()}")
    model = SentenceTransformer(model_name, device=device)

    # 3. Đọc dữ liệu chunks
    logger.info(f"Đang đọc dữ liệu từ {chunks_path}...")
    chunks = []
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))

    total_chunks = len(chunks)
    logger.info(f"Tổng số chunks cần upsert: {total_chunks}")

    total_batches = math.ceil(total_chunks / batch_size)

    for i in tqdm(range(0, total_chunks, batch_size), total=total_batches, desc="Upserting to Qdrant"):
        batch = chunks[i : i + batch_size]
        texts = [item.get("content", "") for item in batch]

        # Generate embeddings
        embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False)

        # Chuẩn bị points cho Qdrant
        points = []
        for j, item in enumerate(batch):
            chunk_id = item.get("chunk_id") or str(uuid.uuid4())
            # Qdrant hỗ trợ ID là số nguyên (int) hoặc UUID string
            # Tạo deterministic UUID từ chunk_id để idempotent khi chạy lại
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(chunk_id)))
            
            payload = {
                "chunk_id": str(chunk_id),
                "doc_id": str(item.get("doc_id", "")),
                "dieu": str(item.get("dieu") or ""),
                "content": item.get("content", ""),
                "metadata": item.get("metadata", {})
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=embeddings[j].tolist(),
                    payload=payload
                )
            )

        client.upsert(collection_name=collection_name, points=points)

    final_info = client.get_collection(collection_name=collection_name)
    logger.info(f"Hoàn thành! Tổng số points trong Qdrant '{collection_name}': {final_info.points_count}")
