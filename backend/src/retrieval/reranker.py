"""
Stage 4: Cross-Encoder Re-ranking.

Sau khi RRF fusion, dùng Cross-Encoder để tính độ liên quan sâu
giữa query và từng chunk → chọn Top 5-10 điều khoản chất lượng nhất.

Model: BAAI/bge-reranker-large (đa ngôn ngữ, hỗ trợ tiếng Việt tốt)
Fallback: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 (nhẹ hơn, nhanh hơn)
"""

from loguru import logger
from typing import List, Dict, Any

class CrossEncoderReranker:
    """
    Sử dụng FlagEmbedding (BAAI/bge-reranker) để re-rank kết quả sau RRF.
    Giải quyết vấn đề 'lost in the middle' khi context window lớn.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-large"):
        logger.info(f"Loading Cross-Encoder: {model_name}")
        try:
            from FlagEmbedding import FlagReranker
            self.reranker = FlagReranker(model_name, use_fp16=True)
            self.model_name = model_name
            logger.info("Cross-Encoder loaded.")
        except ImportError:
            logger.warning("FlagEmbedding chưa cài. Dùng: pip install FlagEmbedding")
            self.reranker = None
            # Fallback: sentence_transformers CrossEncoder
            try:
                from sentence_transformers import CrossEncoder
                fallback_model = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
                self.reranker = CrossEncoder(fallback_model)
                self.model_name = fallback_model
                self._use_flag = False
                logger.info(f"Dùng fallback CrossEncoder: {fallback_model}")
            except Exception as e:
                logger.error(f"Không load được bất kỳ reranker nào: {e}")
                
        self._use_flag = hasattr(self.reranker, 'compute_score')

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Re-rank danh sách chunks theo relevance với query.
        Trả về top_k chunks được sắp xếp lại.
        """
        if not self.reranker or not chunks:
            logger.warning("Reranker không khả dụng, giữ nguyên thứ tự RRF.")
            return chunks[:top_k]

        pairs = [[query, chunk.get("content", "")] for chunk in chunks]

        try:
            if self._use_flag:
                # FlagEmbedding API
                scores = self.reranker.compute_score(pairs, normalize=True)
            else:
                # sentence_transformers CrossEncoder API
                scores = self.reranker.predict(pairs).tolist()

            # Gán score và sort
            for i, chunk in enumerate(chunks):
                chunk["rerank_score"] = float(scores[i])

            reranked = sorted(chunks, key=lambda x: x.get("rerank_score", 0), reverse=True)
            logger.debug(f"Re-ranked {len(reranked)} → top {top_k}")
            return reranked[:top_k]

        except Exception as e:
            logger.error(f"Re-ranking lỗi: {e}. Fallback về RRF order.")
            return chunks[:top_k]
