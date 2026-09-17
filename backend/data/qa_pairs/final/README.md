---
language:
  - vi
license: other
task_categories:
  - text-classification
annotations_creators:
  - machine-generated
pretty_name: Vietnamese Legal QA — Question Specificity 
tags:
  - legal
  - vietnamese
  - question-classification
  - rag
  - synthetic
configs:
  - config_name: default
    data_files:
      - split: train
        path: train.json
      - split: validation
        path: val.json
      - split: test
        path: test.json
---

# Vietnamese Legal QA — Question Specificity

Phân loại **độ cụ thể của câu hỏi pháp luật dân sự Việt Nam**: `broad` (hỏi khái
quát, phải tổng hợp nhiều chế định) hay `narrow` (hỏi vào một tình huống / một
điều luật xác định). Dùng để định tuyến truy vấn trong hệ RAG pháp luật.

## Cấu trúc

Mỗi dòng là một câu hỏi kèm vết gán nhãn. Hai dòng cùng `pair_id` là **một cặp
đối chứng** sinh từ cùng một điều luật — một broad, một narrow.

| Trường | Ý nghĩa |
|---|---|
| `item_id`, `pair_id`, `source_doc_id` | Khoá câu hỏi / cặp đối chứng / điều luật nguồn |
| `question` | Câu hỏi (tiếng Việt) |
| `final_label` | **Nhãn để train**: `broad` hoặc `narrow` |
| `specificity` | Nhãn provenance — câu được sinh ở nhánh nào |
| `heuristic_label`, `heuristic_signals` | Nhãn tầng rule-based (có thể `ambiguous`) và tín hiệu thô |
| `judge_label`, `judge_reason`, `judge_axes` | Nhãn LLM judge (có thể `ambiguous`), lý do, 3 trục rubric |
| `consensus` | Heuristic và judge có trùng nhãn không |
| `metadata` | `scope` (mảng luật), `narrow_mode` (`citation` / `situation`), `title`, `dieu`, `gen_version` |

## Thống kê

| Split | Câu hỏi | Cặp | Văn bản nguồn | broad | narrow |
|---|---:|---:|---:|---:|---:|
| `train` | 4.588 | 2.294 | 1.689 | 2.294 | 2.294 |
| `validation` | 970 | 485 | 362 | 485 | 485 |
| `test` | 948 | 474 | 363 | 474 | 474 |
| **Tổng** | **6.506** | **3.253** | **2.414** | | |

Tỷ lệ train 70% / val 15% / test 15%, seed `42`. **Split theo group
`source_doc_id`** — hai câu cùng cặp luôn cùng một split, nếu không là data leakage.

### Phân bố theo mảng luật

| Mảng luật (`metadata.scope`) | Câu hỏi | Tỷ lệ |
|---|---:|---:|
| `dan_su_chung` | 1.746 | 26.8% |
| `to_tung_thi_hanh_an` | 1.684 | 25.9% |
| `hon_nhan_gia_dinh` | 1.184 | 18.2% |
| `hop_dong_bao_dam` | 676 | 10.4% |
| `boi_thuong` | 430 | 6.6% |
| `dat_dai_nha_o` | 284 | 4.4% |
| `giai_quyet_tranh_chap` | 260 | 4.0% |
| `so_huu_tri_tue` | 242 | 3.7% |

## Baseline tầm thường

**Thấp là tốt.** Đọc F1 của model cạnh bảng này, đừng đọc một mình.

| Baseline | Accuracy trên `test` |
|---|---:|
| Regex bắt số Điều | 73.2% |
| TF-IDF + Logistic Regression | 97.9% |
| Chuyển nhánh `citation→situation` | 53.6% |
| Chuyển nhánh `situation→citation` | 52.0% |

Regex tách theo nhánh: `citation` 99.8%, `situation` 50.0% — nó chỉ ăn ở nhánh có trích dẫn số điều. Cần tập test không shortcut thì lọc `metadata.narrow_mode == "situation"`.

## Độ tin cậy của nhãn

- Tổng: **κ = 0.8427** (n = 76 câu gán tay, đối chiếu `judge_label`)
- `narrow_mode = citation`: **κ = 1.0** (n = 52)
- `narrow_mode = situation`: **κ = 0.5** (n = 24)

Số tổng che mất chênh lệch giữa hai nhánh — κ cao ở `citation` không bảo chứng cho chất lượng nhãn ở `situation`.

## Cách dùng

```python
from datasets import load_dataset

ds = load_dataset("ThanhVu101/Vietnamese-Legal-QA")
train = ds["train"]
validation = ds["validation"]
test = ds["test"]

print(train[0]["question"], train[0]["final_label"])
```

## Quy trình

1. `meta-llama-3.1-8b-instruct` (local) sinh cặp broad + narrow từ mỗi điều luật.
2. Heuristic rule-based gán nhãn yếu, độc lập.
3. LLM judge `google/gemma-4-12b-qat` — **khác họ model sinh**, không có
   self-preference bias — chấm theo rubric 3 trục; câu vùng xám bị loại.
4. Gán tay mẫu mù để đo Cohen's κ, split theo group rồi export.

## Giới hạn

- **Câu hỏi do LLM sinh**, văn phong đều hơn thực tế → accuracy đo ở đây là chặn
  trên lạc quan.
- **Nhãn chủ yếu do máy gán**; gán tay chỉ phủ mẫu nhỏ để đo κ.
- **Hai nhánh narrow không tương đương** về độ khó (xem baseline).
- Chỉ **dân sự và tố tụng dân sự Việt Nam**; phân bố lệch theo độ dài bộ luật nguồn.
- **Không có câu trả lời** — bài toán phân loại câu hỏi, không phải hỏi đáp.
- **Không phải tư vấn pháp lý.**

## Nguồn

Bộ luật Dân sự 2015 (91/2015/QH13), Bộ luật Tố tụng Dân sự 2015 (92/2015/QH13)
và các văn bản dân sự liên quan — bản công báo công khai.