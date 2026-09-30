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
| **Vector DB** | Qdrant local Docker (primary/dev) + Pinecone (cloud, tùy chọn) |
| **Sparse** | BM25 local `.pkl` |
| **Graph DB** | Neo4j local Docker |
| **Routing Classifier** | ✅ Fine-tune `vinai/phobert-base-v2` QLoRA — `backend/models/routing_classifier/` |
| **Query Evolver** | ✅ Tích hợp IRAC rewriting + RoutingClassifier → `evolved_query` + `specificity` |

---

## File từ Evol-Instruct cần giữ để kết nối RAG

Những file này **không chạy lại** nhưng là **input trực tiếp** cho các bước tiếp theo:

| File | Vai trò | Dùng ở đâu |
|---|---|---|
| `backend/data/qa_pairs/final/train.json` | Train routing classifier broad/narrow | Phase 2 ✅ |
| `backend/data/qa_pairs/final/val.json` | Validate classifier | Phase 2 ✅ |
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

### Bước 1c — Build Vector DB (Qdrant primary / Pinecone optional)

```bash
# Qdrant local (dev, không cần API key):
docker run -d -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
python scripts/offline_rag/import_qdrant_from_jsonl.py
# Embedding model: bkai-foundation-models/vietnamese-bi-encoder (dim=768)

# Pinecone cloud (optional — điền PINECONE_API_KEY vào .env trước):
# python scripts/offline_rag/03_build_pinecone.py
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

## Phase 2 — Train Routing Classifier (Broad/Narrow) ✅ HOÀN THÀNH

### Mục tiêu
Phân loại câu hỏi `broad` / `narrow` để `QueryEvolver` chọn đúng chiến lược retrieval:
- **Broad** → `search_multiplier = 4`, `graph_depth = 2` (recall-focused, diện rộng)
- **Narrow** → `search_multiplier = 2`, `graph_depth = 1` (precision-focused, tập trung)

### Dữ liệu ✅ Đã sẵn sàng
```
backend/data/qa_pairs/final/train.json   # ~70% của QA Specificity (203k dòng, 7MB)
backend/data/qa_pairs/final/val.json     # ~15%
```

Mỗi item có: `question` + `final_label` (`broad`/`narrow`) + `source_doc_id` + `pair_id`.
Label ưu tiên: `final_label` → `judge_label` → `specificity`.

### Files đã tạo ✅

| File | Mô tả | Trạng thái |
|---|---|---|
| `backend/evol_instruct/src/qa_specificity/routing_classifier.py` | Inference wrapper PhoBERT + LoRA adapter | ✅ Tạo xong |
| `backend/evol_instruct/scripts/13_train_routing_classifier.py` | QLoRA fine-tune script | ✅ Tạo xong |
| `backend/src/retrieval/query_evolver.py` | Tích hợp RoutingClassifier + IRAC rewriting | ✅ Cập nhật xong |
| `backend/src/api/routers/query.py` | Adaptive retrieval routing theo specificity | ✅ Cập nhật xong |

### Chạy fine-tune

```bash
# Cài đặt dependencies
pip install transformers peft accelerate scikit-learn
pip install bitsandbytes --prefer-binary  # Windows NVIDIA GPU

# Chạy từ thư mục backend/
python evol_instruct/scripts/13_train_routing_classifier.py

# Output: backend/models/routing_classifier/ (adapter + tokenizer + train_config.json)
```

> **Fallback thông minh:** Nếu chưa chạy fine-tune, `RoutingClassifier` tự động fallback về heuristic word-count. Pipeline **không bao giờ crash**.

### `evolve()` sau tích hợp

```python
# query_evolver.py — Trả về dict thay vì str
result = evolver.evolve("Điều kiện bồi thường thiệt hại ngoài hợp đồng?")
# {
#   "evolved_query": "Theo Bộ luật Dân sự 2015, điều kiện phát sinh trách nhiệm ...",
#   "specificity": "narrow"
# }
```

---

## Phase 3 — Đánh giá & Ablation Study

Dùng `backend/data/qa_pairs/final/test.json` để đo hiệu quả:

| Metric | Cách tính |
|---|---|
| **Recall@K** | Với mỗi câu hỏi test, retriever có trả về `doc_id` = `source_doc_id` trong top-K không? |
| **MRR** | Mean Reciprocal Rank của `source_doc_id` trong danh sách kết quả |
| **Ablation routing** | So sánh Recall@K/MRR: pipeline với routing classifier vs không có |

**Cần viết:**
- `backend/evol_instruct/scripts/14_eval_retrieval.py` — load `test.json`, gọi retriever, tính Recall@K và MRR

---

## Thứ tự tổng

```
[✅ Xong] QA Dataset (HF) + QA Specificity (train/val/test.json)
     │
     ▼
[✅ Xong] Phase 1: Build RAG Databases
  import_qdrant_from_jsonl.py → 04 (BM25) → 05 (Neo4j)
     │
     ▼
[✅ Xong] Phase 2: Train Routing Classifier
  script 13 (train PhoBERT QLoRA)
  RoutingClassifier tích hợp vào query_evolver.py
  Adaptive retrieval routing trong query.py
     │
     ▼
[ 🔜 Chưa làm] Phase 3: Ablation Study
  script 14 (eval Recall@K, MRR) → báo cáo Research Gap #2
     │
     ▼
[ 🔜 Chưa làm] Phase 4: Stage 5 Generator
  Fine-tune LLM sinh câu trả lời IRAC (sẽ làm sau khi có kết quả ablation)
     │
     ▼
[Hoàn chỉnh] RAG 5-stage online: FastAPI /api/query
```

> **Chi tiết RAG 5-stage:** xem workflow `/rag-enhancement`.
> **Giao ước doc_id:** xem `docs/doc-id-contract.md` — đọc TRƯỚC Phase 1.
> **Tiêu chí broad/narrow:** xem `docs/specificity-guideline.md`.
