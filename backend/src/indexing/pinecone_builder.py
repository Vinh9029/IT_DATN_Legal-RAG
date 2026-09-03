import json
from pathlib import Path
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
from loguru import logger
from tqdm import tqdm
import math

def build_pinecone_index(chunks_path: Path, api_key: str, env: str, index_name: str, model_name: str, dim: int):
    """Đọc chunks.jsonl, encode text và upsert vào Pinecone."""
    if not api_key:
        logger.error("PINECONE_API_KEY chưa được cấu hình!")
        return

    logger.info(f"Khởi tạo Pinecone client với environment: {env}")
    pc = Pinecone(api_key=api_key)

    if index_name not in pc.list_indexes().names():
        logger.info(f"Tạo index mới: {index_name} (dim={dim})")
        pc.create_index(
            name=index_name,
            dimension=dim,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=env)
        )
    else:
        logger.info(f"Index {index_name} đã tồn tại.")

    index = pc.Index(index_name)

    logger.info(f"Load embedding model: {model_name}")
    model = SentenceTransformer(model_name)

    # Đọc chunks
    chunks = []
    logger.info(f"Đọc dữ liệu từ {chunks_path}")
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))

    # Xử lý theo batch
    batch_size = 100
    total_batches = math.ceil(len(chunks) / batch_size)

    logger.info(f"Bắt đầu upsert {len(chunks)} vectors (batch_size={batch_size})")
    
    for i in tqdm(range(0, len(chunks), batch_size), total=total_batches, desc="Upserting to Pinecone"):
        batch = chunks[i:i + batch_size]
        
        # Prepare vectors
        texts = [item.get("content", "") for item in batch]
        ids = [item.get("chunk_id") for item in batch]
        metadatas = []
        
        for item in batch:
            meta = item.get("metadata", {})
            # Pinecone metadata values must be string, number, boolean or list of strings
            safe_meta = {
                "doc_id": item.get("doc_id", ""),
                "dieu": str(item.get("dieu") or ""),
                "so_hieu": meta.get("so_hieu", ""),
                "loai_van_ban": meta.get("loai_van_ban", ""),
                "tinh_trang": meta.get("tinh_trang", ""),
                "ngay_ban_hanh": meta.get("ngay_ban_hanh", "")
            }
            metadatas.append(safe_meta)

        # Generate embeddings
        embeddings = model.encode(texts, show_progress_bar=False)
        
        # Upsert format: [(id, vector, metadata), ...]
        records = [
            (ids[j], embeddings[j].tolist(), metadatas[j]) 
            for j in range(len(batch))
        ]
        
        index.upsert(vectors=records)

    logger.info("Pinecone Upsert Hoàn tất!")
