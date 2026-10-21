---
language:
  - vi
license: other
license_name: llama3.1
license_link: https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE
task_categories:
  - text-generation
  - question-answering
annotations_creators:
  - machine-generated
pretty_name: Vietnamese Legal Evol-Instruct — Grounded IRAC
tags:
  - legal
  - vietnamese
  - instruction-tuning
  - evol-instruct
  - irac
  - rag
  - synthetic
configs:
  - config_name: default
    data_files:
      - split: train
        path: train.json
      - split: validation
        path: val.json
---

# Vietnamese Legal Evol-Instruct — Grounded IRAC

Dữ liệu **instruction tuning cho hỏi đáp pháp luật dân sự Việt Nam**: câu hỏi
tình huống tiến hoá theo Evol-Instruct (WizardLM), trả lời theo cấu trúc **IRAC**
(Vấn đề – Quy tắc – Áp dụng – Kết luận) và **bám vào một điều luật nguồn** đi kèm.
Dùng để fine-tune generator trong hệ RAG pháp luật.

## Cấu trúc

| Trường | Ý nghĩa |
|---|---|
| `instruction` | Câu hỏi đã tiến hoá |
| `input` | **Điều luật nguồn** (tên văn bản + nội dung Điều, tối đa 2.000 ký tự) — vai trò `[CONTEXT]` trong RAG |
| `output` | Câu trả lời IRAC, chỉ trích dẫn Điều có trong `input` |
| `technique` | Kỹ thuật evolve đã dùng |
| `id`, `source_doc_id`, `document`, `dieu` | Khoá bản ghi / khoá Điều nguồn / số hiệu văn bản / số Điều |
| `scope` | Mảng luật — cùng bộ giá trị với Vietnamese-Legal-QA |
| `seed_instruction` | Câu hỏi seed trước khi tiến hoá |

## Thống kê

| Split | Bản ghi | Điều nguồn |
|---|---:|---:|
| `train` | 996 | 632 |
| `validation` | 115 | 70 |
| **Tổng** | **1.111** | **702** |

**Split theo group `source_doc_id`** (seed `42`) — cùng Điều thì cùng `input`, để
hai phía là data leakage. Không dùng Điều nào thuộc split `test` của
[Vietnamese-Legal-QA](https://huggingface.co/datasets/ThanhVu101/Vietnamese-Legal-QA).

| `technique` | Bản ghi | | Mảng luật (`scope`) | Bản ghi |
|---|---:|---|---|---:|
| `complicating_input` | 219 | | `to_tung_thi_hanh_an` | 252 |
| `concretizing` | 194 | | `dan_su_chung` | 242 |
| `deepening` | 191 | | `hon_nhan_gia_dinh` | 212 |
| `increased_reasoning` | 188 | | `hop_dong_bao_dam` | 105 |
| `constraint_addition` | 178 | | `dat_dai_nha_o` | 92 |
| `mutation` | 141 | | `boi_thuong` | 77 |
| | | | `giai_quyet_tranh_chap` | 73 |
| | | | `so_huu_tri_tue` | 58 |

## Cách dùng

```python
from datasets import load_dataset

ds = load_dataset("ThanhVu101/Vietnamese-Legal-Evol-Instruct")
ex = ds["train"][0]
print(ex["input"], ex["instruction"], ex["output"], sep="\n\n")
```

## Quy trình

1. `meta-llama-3.1-8b-instruct` (local) viết 2 câu hỏi tình huống cho mỗi Điều
   lấy mẫu từ corpus dân sự đã lọc hiệu lực.
2. Mỗi seed tiến hoá **một vòng** bằng một trong 6 kỹ thuật, câu hỏi mới phải
   trả lời được bằng Điều nguồn.
3. Cùng model trả lời theo IRAC, nhận Điều nguồn làm `[CONTEXT]`.
4. Lọc theo tiêu chí của WizardLM cộng thêm: thiếu cấu trúc IRAC, **trích Điều
   ngoài Điều nguồn** (lý do loại chính), số hiệu văn bản không tồn tại, chép
   nguyên Điều nguồn vào câu hỏi. 1.456 seed → 1.111 bản ghi.

Fine-tune QLoRA `Llama-3.1-8B-Instruct` trên `train` đạt chất lượng ngang cấu
hình sinh dữ liệu (LLM judge so cặp trên 40 bản ghi `validation`: thắng 10 / hoà
14 / thua 16) mà không cần ví dụ mẫu trong prompt.

## Giới hạn

- **Toàn bộ do một model 8B sinh ra**, kể cả câu trả lời; không có người kiểm duyệt.
- **Bộ lọc chỉ soát số Điều**, không soát nội dung quy định.
- Mỗi bản ghi dựa trên **một Điều**; tình huống và nhân vật là hư cấu.
- Chỉ **dân sự và tố tụng dân sự Việt Nam**.
- **Không phải tư vấn pháp lý.**

## Giấy phép & nguồn

**Built with Llama** — dùng theo
[Llama 3.1 Community License](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE).

Bộ luật Dân sự 2015 (91/2015/QH13), Bộ luật Tố tụng Dân sự 2015 (92/2015/QH13)
và các văn bản dân sự liên quan (142 văn bản) — bản công báo công khai.
