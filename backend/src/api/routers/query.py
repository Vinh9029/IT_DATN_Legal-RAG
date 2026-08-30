import time
import json
from pathlib import Path
from fastapi import APIRouter
from loguru import logger

from src.api.schemas import QueryRequest, QueryResponse, RetrievedChunk
from src.retrieval.dense_retriever import DenseRetriever
from src.retrieval.sparse_retriever import SparseRetriever
from src.retrieval.graph_expander import GraphExpander
from src.retrieval.rrf_fusion import reciprocal_rank_fusion
from src.retrieval.reranker import CrossEncoderReranker
from src.retrieval.query_evolver import QueryEvolver
from config.settings import (
    PINECONE_API_KEY, PINECONE_ENVIRONMENT, PINECONE_INDEX_NAME, EMBEDDING_MODEL,
    INDEXES_DIR, PROCESSED_DATA_DIR,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME,
)

router = APIRouter()

# Lazy-initialized singletons (tránh load model khi import)
_dense_retriever: DenseRetriever | None = None
_sparse_retriever: SparseRetriever | None = None
_graph_expander: GraphExpander | None = None
_reranker: CrossEncoderReranker | None = None
_query_evolver: QueryEvolver | None = None
_chunks_cache: dict = {}


def _get_retrievers():
    global _dense_retriever, _sparse_retriever, _graph_expander
    global _reranker, _query_evolver, _chunks_cache

    if _dense_retriever is None:
        logger.info("Initializing all RAG components...")
        chunks_path = PROCESSED_DATA_DIR / "chunks" / "chunks.jsonl"

        _dense_retriever = DenseRetriever(
            api_key=PINECONE_API_KEY,
            env=PINECONE_ENVIRONMENT,
            index_name=PINECONE_INDEX_NAME,
            model_name=EMBEDDING_MODEL
        )
        _sparse_retriever = SparseRetriever(
            index_dir=INDEXES_DIR / "bm25",
            chunks_path=chunks_path
        )
        _graph_expander = GraphExpander(
            uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD
        )
        _reranker = CrossEncoderReranker(model_name="BAAI/bge-reranker-large")
        _query_evolver = QueryEvolver(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            model=LLM_MODEL_NAME,
            temperature=0.3
        )

        # Load chunks vào memory để map content cho dense results
        if chunks_path.exists():
            with open(chunks_path, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    _chunks_cache[data["chunk_id"]] = data

    return _dense_retriever, _sparse_retriever, _graph_expander, _reranker, _query_evolver, _chunks_cache


@router.post("/query", response_model=QueryResponse)
async def query_legal_documents(request: QueryRequest):
    start_time = time.time()

    dense_r, sparse_r, graph_r, reranker, evolver, cache = _get_retrievers()

    # ─── Stage 1: Query Evolution ─────────────────────────────
    evolved_query = evolver.evolve(request.query)
    logger.info(f"Stage 1 done | evolved: '{evolved_query[:80]}...'")

    # ─── Stage 2A & 2B: Parallel Retrieval ───────────────────
    sparse_results = sparse_r.search(evolved_query, top_k=request.top_k * 3)
    dense_results = dense_r.search(evolved_query, top_k=request.top_k * 3)

    # Map content vào dense results (Pinecone chỉ trả metadata, không trả content)
    for res in dense_results:
        cached = cache.get(res["chunk_id"])
        if cached:
            res["content"] = cached.get("content", "")
            res.setdefault("metadata", cached.get("metadata", {}))

    logger.info(f"Stage 2 done | dense={len(dense_results)}, sparse={len(sparse_results)}")

    # ─── Stage 2C: RRF Fusion ────────────────────────────────
    fused = reciprocal_rank_fusion(
        dense_results=dense_results,
        sparse_results=sparse_results,
        top_k=request.top_k * 2  # Giữ nhiều để reranker chọn lại
    )
    logger.info(f"Stage 2C (RRF) done | fused={len(fused)}")

    # ─── Stage 3: Legal Graph Expansion ──────────────────────
    if request.enable_graph and fused:
        top_doc_ids = list(set(r["doc_id"] for r in fused if r.get("doc_id")))
        related = graph_r.get_related_documents(doc_ids=top_doc_ids, depth=1)
        logger.info(f"Stage 3 (Graph) done | related_docs={len(related)}")

    # ─── Stage 4: Cross-Encoder Re-ranking ───────────────────
    reranked = reranker.rerank(
        query=evolved_query,
        chunks=fused,
        top_k=request.top_k
    )
    logger.info(f"Stage 4 (Rerank) done | top_k={len(reranked)}")

    # ─── Build Response ───────────────────────────────────────
    results = [
        RetrievedChunk(
            chunk_id=doc.get("chunk_id", ""),
            doc_id=doc.get("doc_id", ""),
            dieu=str(doc.get("dieu") or ""),
            content=doc.get("content", ""),
            score=doc.get("rerank_score", doc.get("rrf_score", 0.0)),
            metadata=doc.get("metadata", {})
        )
        for doc in reranked
    ]

    return QueryResponse(
        query=request.query,
        results=results,
        llm_answer=None,  # Stage 5 (Generator) — sẽ tích hợp sau khi fine-tune
        time_taken=time.time() - start_time
    )

