from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    enable_graph: bool = True

class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    dieu: Optional[str]
    content: str
    score: float
    metadata: Dict[str, Any]

class QueryResponse(BaseModel):
    query: str
    results: List[RetrievedChunk]
    llm_answer: Optional[str] = None
    time_taken: float
