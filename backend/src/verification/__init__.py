"""
Stage 6: Citation Verification — kiểm chứng trích dẫn trong câu trả lời của LLM.

Mỗi trích dẫn "Điều N [văn bản]" được kiểm ba điều kiện so với đúng corpus mà
retrieval đang dùng: (1) tồn tại, (2) nội dung Điều hỗ trợ nhận định, (3) văn
bản còn hiệu lực. Chỉ mục tra cứu dựng offline bằng
`scripts/offline_rag/06_build_citation_index.py`.
"""
