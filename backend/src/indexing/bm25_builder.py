import json
import pickle
from pathlib import Path
from rank_bm25 import BM25Okapi
from underthesea import word_tokenize
from loguru import logger
from tqdm import tqdm

def tokenize_vietnamese(text: str) -> list[str]:
    """Tokenize tiếng Việt với Underthesea."""
    if not text:
        return []
    # Lowercase & tokenize
    return word_tokenize(text.lower(), format="text").split()

def build_bm25_index(chunks_path: Path, output_dir: Path):
    """Đọc chunks.jsonl, xây dựng BM25 index và lưu dưới dạng pickle."""
    corpus = []
    chunk_ids = []
    
    logger.info(f"Đọc dữ liệu từ {chunks_path}")
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="Đọc chunks"):
            data = json.loads(line)
            content = data.get("content", "")
            chunk_id = data.get("chunk_id")
            
            if content and chunk_id:
                corpus.append(content)
                chunk_ids.append(chunk_id)

    logger.info("Đang tokenize corpus (sẽ mất thời gian)...")
    # Tokenize corpus
    tokenized_corpus = [tokenize_vietnamese(doc) for doc in tqdm(corpus, desc="Tokenize")]
    
    logger.info("Khởi tạo BM25Okapi...")
    bm25 = BM25Okapi(tokenized_corpus)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "bm25_index.pkl"
    ids_path = output_dir / "bm25_corpus_ids.json"
    
    logger.info(f"Đang lưu BM25 index ra file pickle: {index_path}")
    with open(index_path, "wb") as f:
        pickle.dump(bm25, f)
        
    logger.info(f"Đang lưu danh sách chunk_ids: {ids_path}")
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump(chunk_ids, f, ensure_ascii=False)
        
    logger.info("BM25 Index Build Hoàn tất!")

