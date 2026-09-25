import gc
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
    batch_size: int = 64,
    device: str = None
):
    """
    Đọc chunks.jsonl, encode text và nạp vào Qdrant (Docker Local).
    Hỗ trợ resume nếu bị gián đoạn bằng cách kiểm tra số points đã có.
    """
    logger.info(f"Kết nối tới Qdrant tại {host}:{port}...")
    client = QdrantClient(host=host, port=port)

    # 1. Kiểm tra / Tạo collection
    existing_collections = [c.name for c in client.get_collections().collections]
    existing_points = 0
    if collection_name not in existing_collections:
        logger.info(f"Tạo collection mới: {collection_name} (dim={dim}, cosine)")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    else:
        info = client.get_collection(collection_name=collection_name)
        existing_points = info.points_count
        logger.info(f"Collection '{collection_name}' đã tồn tại (hiện có {existing_points} points).")

    # 2. Load Embedding Model
    logger.info(f"Load embedding model: {model_name}")
    if not device:
        from src.utils.device import get_torch_device
        device = get_torch_device()

    if str(device).lower() == "cpu":
        import torch
        torch.set_num_threads(min(8, torch.get_num_threads()))

    logger.info(f"Đang sử dụng device: {device}")
    model = SentenceTransformer(model_name, device=device)

    # 3. Đọc dữ liệu chunks
    logger.info(f"Đang đọc dữ liệu từ {chunks_path}...")
    chunks = []
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line, strict=False))

    total_chunks = len(chunks)
    logger.info(f"Tổng số chunks: {total_chunks}")

    # Resume từ vị trí đã nạp thành công (làm tròn theo batch)
    start_index = (existing_points // batch_size) * batch_size
    if start_index > 0:
        logger.info(f"Tiếp tục upsert từ index {start_index} / {total_chunks} (bỏ qua {start_index} chunks đã có trong DB)...")

    total_batches = math.ceil((total_chunks - start_index) / batch_size)

    for i in tqdm(range(start_index, total_chunks, batch_size), total=total_batches, desc="Upserting to Qdrant"):
        batch = chunks[i : i + batch_size]
        texts = [item.get("content", "") for item in batch]

        # Generate embeddings với fallback an toàn nếu bị VRAM OOM
        try:
            embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=False)
        except RuntimeError as e:
            if "memory" in str(e).lower() or "allocate" in str(e).lower():
                logger.warning(f"VRAM OOM ở batch index {i}, đang fallback sang encode từng phần nhỏ trên CPU...")
                model.to("cpu")
                embeddings = model.encode(texts, batch_size=16, show_progress_bar=False)
                model.to(device)
            else:
                raise e

        # Chuẩn bị points cho Qdrant
        points = []
        for j, item in enumerate(batch):
            chunk_id = item.get("chunk_id") or str(uuid.uuid4())
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

        # Giải phóng bộ nhớ tạm sau mỗi batch
        del embeddings, points
        gc.collect()

    final_info = client.get_collection(collection_name=collection_name)
    logger.info(f"Hoàn thành! Tổng số points trong Qdrant '{collection_name}': {final_info.points_count}")
