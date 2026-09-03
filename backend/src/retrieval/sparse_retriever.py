import pickle
from rank_bm25 import BM25Okapi
from pathlib import Path
from loguru import logger
import json
from src.indexing.bm25_builder import tokenize_vietnamese

class SparseRetriever:
    def __init__(self, index_dir: Path, chunks_path: Path):
        self.index_path = index_dir / "bm25_index.pkl"
        self.ids_path = index_dir / "bm25_corpus_ids.json"
        self.chunks_path = chunks_path
        self.bm25 = None
        self.chunk_ids = []
        self.chunks_cache = {}
        self._load()

    def _load(self):
        if not self.index_path.exists() or not self.ids_path.exists():
            logger.warning(f"BM25 index không tồn tại ở {self.index_path}")
            return
            
        logger.info("Loading BM25 index...")
        with open(self.index_path, "rb") as f:
            self.bm25 = pickle.load(f)
            
        with open(self.ids_path, "r", encoding="utf-8") as f:
            self.chunk_ids = json.load(f)
            
        # Load chunks for quick lookup
        logger.info("Loading chunks cache...")
        with open(self.chunks_path, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                self.chunks_cache[data["chunk_id"]] = data

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if not self.bm25:
            return []
            
        tokenized_query = tokenize_vietnamese(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        # Get top_k indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        
        results = []
        for idx in top_indices:
            score = scores[idx]
            if score > 0:
                chunk_id = self.chunk_ids[idx]
                chunk_data = self.chunks_cache.get(chunk_id)
                if chunk_data:
                    chunk_data["score"] = score
                    results.append(chunk_data)
                    
        return results
