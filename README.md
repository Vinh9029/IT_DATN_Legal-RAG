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
pip install -r requirements.txt

# Cấu hình
cp .env.example .env
# Chỉnh sửa .env nếu cần
```

## 🚀 Sử dụng

### Bước 1: Khởi động LM Studio
1. Mở LM Studio
2. Load model `Meta-Llama-3.1-8B-Instruct-GGUF-Q4_K_M`
3. Bật **Local Server** tại port **1234**

### Bước 2: Chạy Pipeline

```bash
# 1. Tải & tiền xử lý dataset
python scripts/01_download_data.py

# 2. Tạo seed prompts
python scripts/02_generate_seeds.py --mode template

# 3. Chạy Evol-Instruct
python scripts/03_run_evolution.py

# 4. Kiểm tra chất lượng
python scripts/04_validate_output.py
```

### Tùy chọn nâng cao

```bash
# Tạo seeds bằng LLM (đa dạng hơn)
python scripts/02_generate_seeds.py --mode llm --max-seeds 200

# Chạy với batch size lớn
python scripts/03_run_evolution.py --batch-size 50

# Giới hạn số lượng documents
python scripts/01_download_data.py --max-items 500
```

## 📁 Cấu trúc

```
├── config/           # Cấu hình & prompt templates
│   ├── settings.py   # Load .env, validation
│   └── prompts.py    # 6 kỹ thuật Evol-Instruct + IRAC prompts
├── src/              # Source code chính
│   ├── data_loader.py    # Load HuggingFace dataset
│   ├── seed_generator.py # Tạo seed prompts (template + LLM)
│   ├── evol_engine.py    # Core Evol-Instruct pipeline
│   ├── filters.py        # 6 bộ lọc chất lượng
│   ├── llm_client.py     # OpenAI-compatible LLM client
│   └── utils.py          # Logging, JSONL I/O, checkpoint
├── scripts/          # Scripts chạy pipeline
├── tests/            # Unit tests
└── data/             # Dữ liệu (git-ignored)
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
pytest tests/ -v
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
