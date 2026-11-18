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

class CitationCheck(BaseModel):
    """Kết quả kiểm chứng một trích dẫn (Stage 6)."""
    text: str
    dieu: str
    khoan: Optional[str] = None
    diem: Optional[str] = None
    status: str                       # valid | warning | invalid | unverifiable
    reasons: List[str] = []
    reason_texts: List[str] = []
    resolution: str = "unresolved"
    doc_id: Optional[str] = None
    so_hieu: Optional[str] = None
    loai: Optional[str] = None
    title: Optional[str] = None
    tinh_trang: Optional[str] = None
    exists: Optional[bool] = None
    effect: Optional[str] = None
    content: Optional[str] = None
    ce_score: Optional[float] = None
    quote_score: Optional[float] = None
    in_context: bool = False
    chunk_id: Optional[str] = None
    start: int = 0
    end: int = 0

class CitationRepair(BaseModel):
    attempted: bool = False
    accepted: bool = False
    invalid_before: int = 0
    invalid_after: Optional[int] = None
    note: Optional[str] = None

class CitationReport(BaseModel):
    counts: Dict[str, int]
    n_citations: int
    citations: List[CitationCheck]
    repair: Optional[CitationRepair] = None
    elapsed_ms: int = 0

class QueryResponse(BaseModel):
    query: str
    results: List[RetrievedChunk]
    llm_answer: Optional[str] = None
    time_taken: float
    # Stage 6 — thêm sau, đều optional nên client cũ không bị ảnh hưởng
    citation_report: Optional[CitationReport] = None
    llm_answer_original: Optional[str] = None   # bản trước khi sửa (chỉ có khi đã sửa)
