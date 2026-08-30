import re
from loguru import logger


def chunk_document(doc: dict) -> list[dict]:
    """
    Cắt một văn bản pháp luật thành các chunks dựa trên Điều (Article) và Khoản (Clause).
    Bảo toàn metadata của văn bản gốc trong mỗi chunk.
    """
    content = doc.get("content", "")
    metadata = doc.get("metadata", {})
    doc_id = doc.get("doc_id", "unknown")

    if not content:
        return []

    # Regex để tìm các "Điều X." hoặc "Điều X " (X là số)
    dieu_pattern = re.compile(r"(?:\n|^)(Điều\s+\d+[\.:\s])", re.IGNORECASE)
    
    chunks = []
    
    parts = dieu_pattern.split(content)
    
    if len(parts) == 1:
        chunks.append({
            "chunk_id": f"{doc_id}_full",
            "doc_id": doc_id,
            "dieu": None,
            "khoan": None,
            "content": content.strip(),
            "metadata": metadata
        })
        return chunks

    preamble = parts[0].strip()
    if preamble:
        chunks.append({
            "chunk_id": f"{doc_id}_preamble",
            "doc_id": doc_id,
            "dieu": "Mở đầu",
            "khoan": None,
            "content": preamble,
            "metadata": metadata
        })

    for i in range(1, len(parts), 2):
        if i + 1 < len(parts):
            dieu_title = parts[i].strip()
            dieu_content = parts[i+1].strip()
            
            dieu_match = re.search(r"Điều\s+(\d+)", dieu_title, re.IGNORECASE)
            dieu_so = dieu_match.group(1) if dieu_match else None
            
            full_content = f"{dieu_title} {dieu_content}".strip()
            
            chunks.append({
                "chunk_id": f"{doc_id}_dieu_{dieu_so}" if dieu_so else f"{doc_id}_dieu_{i}",
                "doc_id": doc_id,
                "dieu": dieu_so,
                "khoan": None,
                "content": full_content,
                "metadata": metadata
            })

    return chunks
