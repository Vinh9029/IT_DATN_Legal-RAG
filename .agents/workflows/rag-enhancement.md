---
description: Xây dựng RAG nâng cao cho bài toán hỏi đáp Pháp Lý (Legal) ở Việt Nam
---

# Multi-stage Hybrid RAG Pipeline — Pháp luật Việt Nam

Kết hợp **Evol-Instruct (WizardLM)** [6] và khung lập luận **IRAC** [2, 3], chia hai luồng:

```
════════════════════ LUỒNG NGOẠI TUYẾN (OFFLINE) ═══════════════════
171k Văn bản [7]
  ├─ Preprocessing (Underthesea/PyVi) → Chunking theo Điều/Khoản + Metadata
  ├─ Dense Index  : PhoBERT/vi-bi-encoder embeddings → Qdrant / Milvus
  └─ Sparse Index : BM25 keyword index

1.03M Relationships [7]
  └─ Knowledge Graph → Neo4j
     Nodes: Văn bản | Edges: hướng_dẫn · sửa_đổi · thay_thế · dẫn_chiếu

Evol-Instruct Pipeline
  └─ Seed Prompts → LLM Rewriter (6 kỹ thuật) → Eliminator → JSONL Dataset
     → Fine-tuning LoRA/QLoRA → LLM Chuyên gia Pháp luật (IRAC)

════════════════════ LUỒNG TRỰC TUYẾN (ONLINE) ══════════════════════
[User Query]
    │
    ▼ Stage 1: Query Evolution (WizardLM Prompt Rewriter)
[Evolved Query: thuật ngữ chuẩn + IRAC constraint]
    │
    ├──────────────────────────────────────────┐
    ▼                                          ▼
Stage 2A: Dense Search              Stage 2B: Sparse Search (BM25)
(Vector DB — PhoBERT)               (Từ khóa / Số hiệu văn bản)
    └──────────────┬───────────────────────────┘
                   ▼
         Rank Fusion (RRF) → Top-K Documents
                   │
                   ▼ Stage 3: Legal Graph Expansion (Neo4j)
         Kéo thêm: Nghị định hướng dẫn, Luật sửa đổi liên quan
         Lọc: Metadata tinh_trang ≠ "Hết hiệu lực"
                   │
                   ▼ Stage 4: Cross-Encoder Re-ranking
         mMARCO / bge-reranker-large → Top 5–10 điều khoản
                   │
                   ▼ Stage 5: Generator (Fine-tuned Legal LLM)
         Input: [Evolved Query] + [Re-ranked Context]
         Output: Issue → Rule → Application → Conclusion
```

---

## PHẦN I — LUỒNG NGOẠI TUYẾN

### 1. Xử lý Dữ liệu (171k văn bản) [7]

| Bước | Công việc | Công cụ |
|---|---|---|
| Preprocessing | Chuẩn hóa văn bản, tách từ | Underthesea / PyVi |
| Chunking | Cắt theo **Điều/Khoản** (không cắt ngẫu nhiên) + giữ Metadata | Regex + custom parser |
| Dense Index | Encode chunk → vector | `vinai/phobert-base-v2` hoặc `bkai-foundation-models/vietnamese-bi-encoder` |
| Vector DB | Lưu trữ & tìm kiếm vector | Qdrant (port 6333) hoặc Milvus |
| Sparse Index | Tìm kiếm số hiệu, tên luật chính xác | `rank_bm25.BM25Okapi` |

**Metadata bắt buộc mỗi chunk:** `so_hieu`, `loai_van_ban`, `co_quan_ban_hanh`, `ngay_ban_hanh`, `tinh_trang`.

### 2. Knowledge Graph — Neo4j [1, 7]

Nạp 1.03M quan hệ từ dataset. Cấu trúc:
- **Nodes**: mỗi văn bản pháp luật (Luật, Nghị định, Thông tư, ...)
- **Edges** (có hướng): `hướng_dẫn_thi_hành` · `sửa_đổi_bổ_sung` · `thay_thế_cho` · `dẫn_chiếu_đến`

### 3. Evol-Instruct → Fine-tuning [6]

6 kỹ thuật tiến hóa → dataset IRAC Alpaca JSONL → LoRA/QLoRA fine-tune trên Llama-3-8B / Qwen-2.5-7B.

> **Chi tiết:** xem workflow `/evol-instruct-build` và `scripts/`.

---

## PHẦN II — LUỒNG TRỰC TUYẾN (5 GIAI ĐOẠN)

### Stage 1 — Query Evolution [6]

**Vấn đề:** Câu hỏi thô ngắn, thiếu thuật ngữ → Semantic Search lệch hướng.

**Xử lý:** LLM nhỏ đóng vai **Prompt Rewriter** (WizardLM *Adding Constraints* — Example 3.1 [6]):
- Bổ sung thuật ngữ pháp lý chuẩn hóa
- Làm rõ giả định tình huống
- Ràng buộc cứng: output phải theo **IRAC** [2, 3]

### Stage 2 — Hybrid Retrieval (Dense + Sparse)

Hai luồng song song, hợp nhất bằng **Reciprocal Rank Fusion (RRF)**:
- **Dense (2A):** Vector similarity search — bắt nghĩa câu hỏi tình huống
- **Sparse (2B):** BM25 — bắt chính xác số hiệu luật, tên nghị định

### Stage 3 — Legal Graph Expansion [7]

Lấy ID tài liệu Top-K → truy vấn Neo4j → kéo thêm:
- Nghị định **hướng dẫn thi hành** bộ Luật vừa tìm được
- Luật **sửa đổi bổ sung** liên quan

Lọc bỏ văn bản `tinh_trang = "Hết hiệu lực"` qua Metadata.

### Stage 4 — Cross-Encoder Re-ranking

Toàn bộ pool tài liệu → **Cross-Encoder** tính độ liên quan sâu với Evolved Query → giữ **5–10 điều khoản** chất lượng nhất, tránh *"lost in the middle"*.

Mô hình gợi ý: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` hoặc `BAAI/bge-reranker-large`.

### Stage 5 — Generator IRAC [2, 3, 4, 5]

Fine-tuned LLM nhận `[Evolved Query] + [Re-ranked Context]` → sinh câu trả lời:

| Thành phần | Nội dung |
|---|---|
| **Issue** | Vấn đề / tranh chấp pháp lý cốt lõi |
| **Rule** | Trích dẫn Điều, Khoản từ Context (không hallucination) |
| **Application** | Lập luận áp dụng quy phạm vào tình tiết cụ thể |
| **Conclusion** | Phán quyết, hướng giải quyết, lời khuyên pháp lý |

---

## Tài liệu Tham khảo

| Mã | Nguồn |
|---|---|
| [1] | PhoBERT, Underthesea — Vietnamese NLP |
| [2] | IRAC Method — Legal Reasoning Framework |
| [3] | Prof. Ng (CSUN) — IRAC Legal Analysis |
| [4] | Legal AI Evaluation Benchmarks |
| [5] | Vietnamese Legal QA Datasets |
| [6] | WizardLM Evol-Instruct — https://arxiv.org/pdf/2304.12244 |
| [7] | Dataset: `th1nhng0/vietnamese-legal-documents` (HuggingFace) |