import uuid
from typing import List, Dict, Any
from loguru import logger
from sentence_transformers import SentenceTransformer

class DenseRetriever:
    """
    Dense Vector Retriever hỗ trợ linh hoạt 2 backend:
    - Qdrant (Local Docker - mặc định, hiệu năng cao, không tốn quota)
    - Pinecone (Cloud Serverless)
    """

    def __init__(
        self,
        db_type: str = "qdrant",
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        qdrant_collection: str = "legal-rag-vi",
        pinecone_api_key: str = "",
        pinecone_env: str = "us-east-1-aws",
        pinecone_index: str = "legal-rag-vi",
        model_name: str = "bkai-foundation-models/vietnamese-bi-encoder",
    ):
        self.db_type = db_type.lower()
        self.model_name = model_name

        logger.info(f"Khởi tạo Dense Retriever (Backend: {self.db_type.upper()})...")

        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(model_name, device=device)

        if self.db_type == "qdrant":
            from qdrant_client import QdrantClient
            self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
            self.collection_name = qdrant_collection
            self.pinecone_index = None
        else:
            from pinecone import Pinecone
            self.pc = Pinecone(api_key=pinecone_api_key)
            self.pinecone_index = self.pc.Index(pinecone_index)
            self.qdrant_client = None

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        # Encode query
        query_embedding = self.model.encode(query, show_progress_bar=False).tolist()

        if self.db_type == "qdrant":
            # Search trên Qdrant
            search_result = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k,
                with_payload=True,
            )

            results = []
            for hit in search_result:
                payload = hit.payload or {}
                chunk_data = {
                    "chunk_id": payload.get("chunk_id", str(hit.id)),
                    "score": hit.score,
                    "doc_id": payload.get("doc_id"),
                    "dieu": payload.get("dieu"),
                    "content": payload.get("content", ""),
                    "metadata": payload.get("metadata", {}),
                }
                results.append(chunk_data)
            return results

        else:
            # Fallback sang Pinecone
            if not self.pinecone_index:
                return []

            response = self.pinecone_index.query(
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True
            )

            results = []
            for match in response.matches:
                chunk_data = {
                    "chunk_id": match.id,
                    "score": match.score,
                    "doc_id": match.metadata.get("doc_id"),
                    "dieu": match.metadata.get("dieu"),
                    "content": "",
                    "metadata": {
                        "so_hieu": match.metadata.get("so_hieu"),
                        "loai_van_ban": match.metadata.get("loai_van_ban"),
                        "tinh_trang": match.metadata.get("tinh_trang"),
                        "ngay_ban_hanh": match.metadata.get("ngay_ban_hanh"),
                    },
                }
                results.append(chunk_data)
            return results
