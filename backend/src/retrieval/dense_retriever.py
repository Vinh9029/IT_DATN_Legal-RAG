from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from loguru import logger
from typing import List, Dict, Any

class DenseRetriever:
    def __init__(self, api_key: str, env: str, index_name: str, model_name: str):
        self.api_key = api_key
        self.env = env
        self.index_name = index_name
        
        logger.info(f"Khởi tạo Pinecone Dense Retriever...")
        self.pc = Pinecone(api_key=self.api_key)
        self.index = self.pc.Index(self.index_name)
        
        logger.info(f"Load embedding model {model_name}...")
        self.model = SentenceTransformer(model_name)

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        if not self.index:
            return []
            
        # Encode query
        query_embedding = self.model.encode(query, show_progress_bar=False).tolist()
        
        # Search
        response = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True
        )
        
        results = []
        for match in response.matches:
            # Reconstruct chunk data format from metadata
            chunk_data = {
                "chunk_id": match.id,
                "score": match.score,
                "doc_id": match.metadata.get("doc_id"),
                "dieu": match.metadata.get("dieu"),
                "metadata": {
                    "so_hieu": match.metadata.get("so_hieu"),
                    "loai_van_ban": match.metadata.get("loai_van_ban"),
                    "tinh_trang": match.metadata.get("tinh_trang"),
                    "ngay_ban_hanh": match.metadata.get("ngay_ban_hanh"),
                },
                # Lưu ý: Pinecone giới hạn dung lượng metadata (40KB). 
                # Nếu text quá dài, ta có thể chỉ chứa trong chunk_cache.
                # Do chưa lưu text trong pinecone metadata, ta cần ánh xạ lại với cache.
            }
            results.append(chunk_data)
            
        return results
