from typing import List, Dict, Any

def reciprocal_rank_fusion(dense_results: List[Dict[str, Any]], 
                         sparse_results: List[Dict[str, Any]], 
                         k: int = 60,
                         top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Kết hợp kết quả từ Dense Retrieval và Sparse Retrieval sử dụng Reciprocal Rank Fusion (RRF).
    RRF Score = 1 / (k + rank)
    """
    
    rrf_scores = {}
    combined_docs = {}
    
    # Process Dense Results
    for rank, doc in enumerate(dense_results):
        chunk_id = doc["chunk_id"]
        if chunk_id not in rrf_scores:
            rrf_scores[chunk_id] = 0
            combined_docs[chunk_id] = doc
        rrf_scores[chunk_id] += 1 / (k + rank + 1)
        
    # Process Sparse Results
    for rank, doc in enumerate(sparse_results):
        chunk_id = doc["chunk_id"]
        if chunk_id not in rrf_scores:
            rrf_scores[chunk_id] = 0
            combined_docs[chunk_id] = doc
        rrf_scores[chunk_id] += 1 / (k + rank + 1)
        
    # Sort by RRF score
    sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    
    # Get top_k results
    final_results = []
    for chunk_id in sorted_chunk_ids[:top_k]:
        doc = combined_docs[chunk_id]
        doc["rrf_score"] = rrf_scores[chunk_id]
        final_results.append(doc)
        
    return final_results
