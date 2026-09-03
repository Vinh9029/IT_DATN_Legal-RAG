# 🏛️ Evol-Instruct Pipeline - Dữ liệu Pháp luật Việt Nam

Hệ thống tự động tạo dữ liệu huấn luyện (Synthetic Data Generation) cho fine-tuning mô hình ngôn ngữ chuyên biệt pháp luật Việt Nam, sử dụng thuật toán **Evol-Instruct** (WizardLM) với cấu trúc **IRAC**.

## 🔧 Yêu cầu

- **Python** 3.10+
- **LM Studio** với model `Meta-Llama-3.1-8B-Instruct-GGUF-Q4_K_M`
- **VRAM** ≥ 6GB (GPU) hoặc ≥ 8GB RAM (CPU mode)

## ⚡ Cài đặt

```bash
# Clone project
git clone <repo-url>
cd IT_DATN

# Tạo virtual environment
python -m venv venv
venv\Scripts\activate    # Windows

# Cài dependencies
pip install -r backend/requirements.txt

# Cấu hình
cp backend/.env.example backend/.env
# Chỉnh sửa backend/.env nếu cần
```

> Mọi lệnh pipeline bên dưới chạy từ thư mục `backend/` (`cd backend`).

## 🚀 Sử dụng

### Bước 1: Khởi động LM Studio
1. Mở LM Studio
2. Load model `Meta-Llama-3.1-8B-Instruct-GGUF-Q4_K_M`
3. Bật **Local Server** tại port **1234**

### Bước 2: Chạy Pipeline

```bash
# 1. Tải & tiền xử lý dataset
python evol_instruct/scripts/01_download_data.py

# 2. Tạo seed prompts
python evol_instruct/scripts/02_generate_seeds.py --mode template

# 3. Chạy Evol-Instruct
python evol_instruct/scripts/03_run_evolution.py

# 4. Kiểm tra chất lượng
python evol_instruct/scripts/04_validate_output.py
```

### Tùy chọn nâng cao

```bash
# Tạo seeds bằng LLM (đa dạng hơn)
python evol_instruct/scripts/02_generate_seeds.py --mode llm --max-seeds 200

# Chạy với batch size lớn
python evol_instruct/scripts/03_run_evolution.py --batch-size 50

# Giới hạn số lượng documents
python evol_instruct/scripts/01_download_data.py --max-items 500
```

## 📁 Cấu trúc

```
backend/                       # Toàn bộ code Python (root của sys.path)
├── config/                    # Cấu hình & prompt dùng chung
│   ├── settings.py            # Load .env, validation
│   ├── prompts.py             # 6 kỹ thuật Evol-Instruct + IRAC prompts
│   ├── qa_settings.py         # Cấu hình riêng QA Specificity (Phần 3)
│   └── qa_prompts.py          # Prompt sinh cặp QA + rubric judge
├── src/                       # RAG online (retrieval, indexing, API)
├── evol_instruct/             # Pipeline sinh dữ liệu (Phần 2 + Phần 3)
│   ├── src/
│   │   ├── data_loader.py     # Load HuggingFace dataset
│   │   ├── seed_generator.py  # Tạo seed prompts (template + LLM)
│   │   ├── evol_engine.py     # Core Evol-Instruct pipeline
│   │   ├── filters.py         # 6 bộ lọc chất lượng
│   │   ├── llm_client.py      # OpenAI-compatible LLM client
│   │   ├── gemini_client.py   # Google Gemini client
│   │   ├── utils.py           # Logging, JSONL I/O, checkpoint
│   │   └── qa_specificity/    # Phần 3 — phân loại độ cụ thể câu hỏi
│   ├── scripts/               # 01–06 (Evol-Instruct), 10–12 (QA Specificity)
│   └── tests/                 # Unit tests
├── scripts/offline_rag/       # Pipeline dựng index cho RAG
└── data/                      # Dữ liệu (git-ignored)
    ├── rag/                   # raw / processed / indexes
    ├── evol_instruct/         # seeds / output
    ├── corpus_civil/          # nguồn luật dân sự (Phần 3)
    └── qa_pairs/              # raw / labeled / final
```

## 🔬 6 Kỹ thuật Tiến hóa

| # | Kỹ thuật | Mô tả |
|---|----------|--------|
| 1 | Constraint Addition | Thêm ràng buộc IRAC |
| 2 | Deepening | Đi sâu vào ngoại lệ pháp lý |
| 3 | Concretizing | Cụ thể hóa thành case study |
| 4 | Increased Reasoning | Tăng bước lập luận |
| 5 | Complicating Input | Phức tạp hóa bằng XML facts |
| 6 | Mutation | Đột biến sang chủ đề ngách |

## 🧪 Testing

```bash
cd backend
pytest evol_instruct/tests/ -v
```

## 📊 Output Format (Alpaca JSONL)

```json
{
  "instruction": "Câu hỏi đã tiến hóa...",
  "input": "",
  "output": "**Vấn đề:** ... **Quy tắc:** ... **Áp dụng:** ... **Kết luận:** ..."
}
```

## 📝 License

MIT
