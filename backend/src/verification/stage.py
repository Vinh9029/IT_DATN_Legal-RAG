"""
Stage 6 trong query router: kiểm chứng trích dẫn (+ sửa một lần nếu có lỗi).

Thiết kế để KHÔNG BAO GIỜ làm hỏng request: thiếu chỉ mục, thiếu model, LLM lỗi...
đều chỉ ghi log và trả về None — câu trả lời của Stage 5 giữ nguyên.

Bật/tắt bằng env (không đụng config/settings.py):
    CITATION_VERIFY=1        bật Stage 6 (mặc định 1)
    CITATION_REPAIR=1        cho phép sửa một lần khi có trích dẫn không hợp lệ (mặc định 1)
    CITATION_INDEX_PATH=...  mặc định data/rag/indexes/citation_index.sqlite
    CITATION_CE_HIGH / CITATION_CE_LOW / CITATION_QUOTE_HIGH / CITATION_QUOTE_LOW  ngưỡng
"""

import os
import threading
import time
from pathlib import Path
from typing import Any, Optional, Sequence

from loguru import logger

from src.verification.verifier import REASON_TEXT, CitationVerifier, CrossEncoderScorer

_lock = threading.Lock()
_verifier: Optional[CitationVerifier] = None
_init_failed = False


def _flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "false", "no", "off", "")


def _index_path() -> Path:
    env = os.getenv("CITATION_INDEX_PATH")
    if env:
        p = Path(env)
        if not p.is_absolute():
            from config.settings import BASE_DIR
            p = BASE_DIR / p
        return p
    from config.settings import INDEXES_DIR
    return INDEXES_DIR / "citation_index.sqlite"


def get_verifier(reranker: Any = None) -> Optional[CitationVerifier]:
    """Khởi tạo một lần; dùng lại cross-encoder của Stage 4 nếu có."""
    global _verifier, _init_failed
    if _verifier is not None or _init_failed:
        return _verifier
    with _lock:
        if _verifier is not None or _init_failed:
            return _verifier
        try:
            from src.verification.citation_index import CitationIndex
            index = CitationIndex(_index_path())
            scorer = CrossEncoderScorer.from_reranker(reranker) if reranker is not None else None
            if scorer is None:
                logger.warning("Stage 6: không có cross-encoder → chỉ kiểm tồn tại + hiệu lực.")
            _verifier = CitationVerifier(index, scorer=scorer)
            info = index.build_info()
            logger.info(f"Stage 6 sẵn sàng | index built_at={info.get('built_at')} | "
                        f"articles={info.get('articles')} | scorer={'on' if scorer else 'off'}")
        except Exception as e:
            _init_failed = True
            logger.warning(f"Stage 6 tắt: không khởi tạo được verifier ({e})")
    return _verifier


def _sync_history(generator: Any, original: str, final: str) -> None:
    """Lượt hội thoại vừa lưu là bản gốc; thay bằng bản đã sửa để lượt sau không học lại lỗi."""
    hist = getattr(generator, "_history", None)
    if hist and hist[-1].get("role") == "assistant" and hist[-1].get("content") == original:
        hist[-1]["content"] = final


def run_citation_stage(query: str, answer: Optional[str], chunks: Sequence[dict],
                       generator: Any = None, reranker: Any = None) -> Optional[dict]:
    """
    Trả về dict:
        {"final_answer", "original_answer" (None nếu không sửa), "report": {...}}
    hoặc None nếu Stage 6 tắt / lỗi.
    """
    if not answer or not _flag("CITATION_VERIFY"):
        return None
    verifier = get_verifier(reranker)
    if verifier is None:
        return None

    t0 = time.time()
    try:
        report = verifier.verify(answer, chunks)
        final, original, repair = answer, None, None
        if _flag("CITATION_REPAIR") and report.n_invalid > 0 and generator is not None:
            from src.verification.repair import repair_answer
            final, report, outcome = repair_answer(verifier, generator, query, answer, chunks, report)
            repair = outcome.__dict__
            if outcome.accepted:
                original = answer
                _sync_history(generator, answer, final)
        payload = report.to_dict()
        for c in payload["citations"]:
            c["reason_texts"] = [REASON_TEXT.get(r, r) for r in c["reasons"]]
        payload["repair"] = repair
        payload["elapsed_ms"] = int((time.time() - t0) * 1000)
        logger.info(
            f"Stage 6 (Citation) done | n={payload['n_citations']} | {payload['counts']} | "
            f"repair={repair and {k: repair[k] for k in ('attempted', 'accepted')}} | "
            f"{payload['elapsed_ms']}ms")
        return {"final_answer": final, "original_answer": original, "report": payload}
    except Exception as e:
        logger.warning(f"Stage 6 lỗi, giữ nguyên câu trả lời: {e}")
        return None
