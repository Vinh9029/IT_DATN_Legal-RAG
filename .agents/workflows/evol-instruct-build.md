---
description: "Roadmap kết nối Evol-Instruct + QA Specificity → RAG Pipeline hoàn chỉnh"
---

# Evol-Instruct → RAG — Roadmap Tiếp Theo

> **Dataset QA Evol-Instruct: ✅ XONG**
> 🤗 https://huggingface.co/datasets/ThanhVu101/Vietnamese-Legal-QA
> **Không cần chạy lại** bất kỳ script nào từ `01` đến `12`.

---

## Kiến trúc đã chốt

| Thành phần | Quyết định |
|---|---|
| **Corpus RAG** | Toàn bộ 171k văn bản — `th1nhng0/vietnamese-legal-documents` (HF) |
| **Vector DB** | Pinecone (primary) + Qdrant local Docker (fallback/dev) |
| **Sparse** | BM25 local `.pkl` |
| **Graph DB** | Neo4j local Docker |
| **Routing Classifier** | Fine-tune PhoBERT trên `train.json` (QA Specificity) bằng QLoRA local (Llama 8B) |

---

## File từ Evol-Instruct cần giữ để kết nối RAG

Những file này **không chạy lại** nhưng là **input trực tiếp** cho các bước tiếp theo:

| File | Vai trò | Dùng ở đâu |
|---|---|---|
| `backend/data/qa_pairs/final/train.json` | Train routing classifier broad/narrow | Phase 2 |
| `backend/data/qa_pairs/final/val.json` | Validate classifier | Phase 2 |
| `backend/data/qa_pairs/final/test.json` | **Gold set** đánh giá Recall@K, MRR, ablation | Phase 3 |
| `docs/doc-id-contract.md` | Giao ước `doc_id` — đọc trước khi chạy Phase 1 | Bước 1b |

> ⚠️ **`doc_id` contract:** Chunker (`02_chunk_documents.py`) phải gán `doc_id` là **id gốc từ HF dataset, không có tiền tố `doc_`**. Hiện tại `chunker.py` lấy `doc.get("doc_id", "unknown")` — cần xác nhận `preprocessed_cache.jsonl` có trường `doc_id` đúng format trước khi chạy.

---

## Phase 1 — Build RAG Databases (Offline)

### Bước 1a — Preprocess & Cache toàn bộ 171k văn bản

```bash
cd backend
python scripts/offline_rag/01_fix_preprocess.py
# Output: data/rag/raw/preprocessed_cache.jsonl (154k–171k dòng)
# Lần đầu tải HF dataset ~6 GB → setx HF_HOME "G:\hf_cache" nếu ổ C: gần đầy
```

### Bước 1b — Chunk theo Điều/Khoản + đảm bảo doc_id khớp

> ⚠️ Đọc `docs/doc-id-contract.md` trước. Chunker tạo `chunk_id = {doc_id}_dieu_{n}` và giữ `doc_id` của văn bản mẹ — format này phải khớp với `source_doc_id` trong QA dataset.

```bash
python scripts/offline_rag/02_chunk_documents.py
# Output: data/rag/processed/chunks/chunks.jsonl
# Mỗi chunk có: chunk_id, doc_id, dieu, content, metadata
```

### Bước 1c — Build Vector DB (Pinecone primary)

```bash
# Điền PINECONE_API_KEY vào .env trước
python scripts/offline_rag/03_build_pinecone.py
# Embedding model: bkai-foundation-models/vietnamese-bi-encoder (dim=768)
# Upsert theo batch 100, có progress bar
```

**Qdrant local (fallback/dev) — chạy song song:**
```bash
docker run -d -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
# → Cần viết thêm 03b_build_qdrant.py (tương tự pinecone_builder.py)
# Qdrant không cần API key, phù hợp test local không tốn tiền
```

### Bước 1d — Build BM25 Index

```bash
python scripts/offline_rag/04_build_bm25.py
# Output: data/rag/indexes/bm25/bm25_index.pkl
```

### Bước 1e — Build Neo4j Graph (1.03M relationships)

```bash
# Khởi động Neo4j trước (Docker Compose đã có sẵn)
docker compose up neo4j -d
# Chờ Neo4j sẵn sàng (~30s), kiểm tra: http://localhost:7474

python scripts/offline_rag/05_build_neo4j.py
# → Nạp Nodes (văn bản) từ chunks.jsonl
# → Nạp Edges từ HF config 'relationships' (tải online ~lần đầu)
# → Group by relationship type, MERGE bằng string interpolation (không cần APOC)
```

> Thứ tự quan hệ dùng để expand context: ưu tiên `HUONG_DAN_THI_HANH`, `SUA_DOI_BO_SUNG`, `THAY_THE_CHO`. **Không dùng `CAN_CU`** (668k dòng — kéo cả kho về).

---

## Phase 2 — Train Routing Classifier (Broad/Narrow)

### Mục tiêu
Train model phân loại câu hỏi `broad` / `narrow` để `QueryEvolver` chọn đúng `IRetrievalStrategy`:
- **Narrow** → Top-K nhỏ hơn, precision-focused retrieval
- **Broad** → Top-K lớn hơn, recall-focused + graph expansion mạnh hơn

### Dữ liệu
```
backend/data/qa_pairs/final/train.json   # ~70% của QA Specificity dataset
backend/data/qa_pairs/final/val.json     # ~15%
```

Mỗi item có: `question` (text) + `final_label` (`broad`/`narrow`) + `source_doc_id` + `pair_id`.

### Approach: Fine-tune PhoBERT + QLoRA

```python
# Base model: vinai/phobert-base-v2 (sequence classification)
# QLoRA để giảm VRAM — chạy được trên card 8GB
# Training: binary classification (broad=0, narrow=1)
# Metric: F1 macro (vì dataset cân bằng broad/narrow theo thiết kế contrastive pair)
```

**Cần tạo mới:**
- `backend/evol_instruct/src/qa_specificity/routing_classifier.py` — wrap PhoBERT inference
- `backend/evol_instruct/scripts/13_train_routing_classifier.py` — train script
- Tích hợp vào `backend/src/retrieval/query_evolver.py`

### Tích hợp vào QueryEvolver

Hiện tại [`query_evolver.py`](file:///d:/IT_DATN_Legal-RAG/backend/src/retrieval/query_evolver.py) chỉ làm query rewriting.
Sau Phase 2, `evolve()` sẽ trả thêm `specificity: str` để pipeline chọn strategy:

```python
def evolve(self, query: str) -> dict:
    evolved_query = self._rewrite(query)
    specificity = self.classifier.predict(evolved_query)   # "broad" | "narrow"
    return {"evolved_query": evolved_query, "specificity": specificity}
```

---

## Phase 3 — Đánh giá & Ablation Study

Dùng `backend/data/qa_pairs/final/test.json` để đo hiệu quả:

| Metric | Cách tính |
|---|---|
| **Recall@K** | Với mỗi câu hỏi test, retriever có trả về `doc_id` = `source_doc_id` của câu hỏi đó trong top-K không? |
| **MRR** | Mean Reciprocal Rank của `source_doc_id` trong danh sách kết quả |
| **Ablation routing** | So sánh Recall@K/MRR: pipeline với routing classifier vs không có (dùng strategy mặc định) |

**Cần viết:**
- `backend/evol_instruct/scripts/14_eval_retrieval.py` — load `test.json`, gọi retriever, tính Recall@K và MRR

---

## Thứ tự tổng

```
[Đã xong] QA Dataset (HF) + QA Specificity (train/val/test.json)
     │
     ▼
Phase 1: Build RAG Databases
  01 → 02 → 03 (Pinecone) + 03b (Qdrant) → 04 (BM25) → 05 (Neo4j)
     │
     ▼
Phase 2: Train Routing Classifier
  script 13 (train PhoBERT QLoRA) → tích hợp vào query_evolver.py
     │
     ▼
Phase 3: Ablation Study
  script 14 (eval Recall@K, MRR) → báo cáo Research Gap #2
     │
     ▼
[Hoàn chỉnh] RAG 5-stage online: FastAPI /api/query
```

> **Chi tiết RAG 5-stage:** xem workflow `/rag-enhancement`.
> **Giao ước doc_id:** xem `docs/doc-id-contract.md` — đọc TRƯỚC Phase 1.
> **Tiêu chí broad/narrow:** xem `docs/specificity-guideline.md`.