"""
Sinh dataset card (README.md) cho bản dataset QA specificity trên HuggingFace.

Card sinh lại từ `stats.json` + `baselines.json` + `kappa_report.json` mỗi lần
chạy, vì viết tay thì lần nâng cấp dữ liệu sau số trên Hub vẫn là số của bản cũ.
Việc đẩy lên Hub là lệnh `hf upload` — xem `docs/hf-dataset-publishing.md`.

    python -m evol_instruct.src.qa_specificity.hf_publisher --repo-id <user>/<tên>
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

# {tên split trên đĩa: tên split trên Hub}
SPLIT_ALIAS = {"train": "train", "val": "validation", "test": "test"}


def read_json(path: Path | None) -> dict:
    """Đọc file JSON nếu có; thiếu file thì trả dict rỗng (card tự khuyết mục)."""
    if path is None or not Path(path).exists():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pct(value) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "—"


def _num(value) -> str:
    """Số nguyên, dấu chấm ngăn hàng nghìn theo lối Việt Nam."""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _split_table(stats: dict, split_alias: dict[str, str]) -> str:
    rows = ["| Split | Câu hỏi | Cặp | Văn bản nguồn | broad | narrow |",
            "|---|---:|---:|---:|---:|---:|"]
    for local_name, hub_name in split_alias.items():
        s = (stats.get("splits") or {}).get(local_name)
        if not s:
            continue
        counts = s.get("label_counts") or {}
        rows.append(
            f"| `{hub_name}` | {_num(s.get('n_items'))} | {_num(s.get('n_pairs'))} | "
            f"{_num(s.get('n_source_docs'))} | {_num(counts.get('broad'))} | "
            f"{_num(counts.get('narrow'))} |"
        )
    if stats.get("total_items"):
        rows.append(
            f"| **Tổng** | **{_num(stats.get('total_items'))}** | "
            f"**{_num(stats.get('total_pairs'))}** | "
            f"**{_num(stats.get('total_source_docs'))}** | | |"
        )
    return "\n".join(rows)


def _scope_table(stats: dict) -> str:
    """Phân bố theo mảng luật, cộng dồn cả 3 split."""
    totals: dict[str, int] = {}
    for split in (stats.get("splits") or {}).values():
        for scope, n in (split.get("scope_counts") or {}).items():
            totals[scope] = totals.get(scope, 0) + n
    if not totals:
        return "_Chưa có dữ liệu phân bố._"
    grand = sum(totals.values()) or 1
    rows = ["| Mảng luật (`metadata.scope`) | Câu hỏi | Tỷ lệ |", "|---|---:|---:|"]
    for scope, n in sorted(totals.items(), key=lambda kv: -kv[1]):
        rows.append(f"| `{scope}` | {_num(n)} | {n / grand * 100:.1f}% |")
    return "\n".join(rows)


def _baseline_section(baselines: dict) -> str:
    cur = baselines.get("hien_tai") or {}
    if not cur:
        return "_Chưa chạy `14_measure_baselines.py`._"
    shortcut = cur.get("shortcut") or {}
    branches = shortcut.get("theo_nhanh") or {}

    lines = [
        "| Baseline | Accuracy trên `test` |",
        "|---|---:|",
        f"| Regex bắt số Điều | {_pct(shortcut.get('tong'))} |",
        f"| TF-IDF + Logistic Regression | {_pct(cur.get('tfidf'))} |",
    ]
    for name, res in (cur.get("chuyen_nhanh") or {}).items():
        lines.append(f"| Chuyển nhánh `{name}` | {_pct(res.get('acc'))} |")
    table = "\n".join(lines)

    if not branches:
        return table
    parts = [f"`{k}` {_pct(v.get('acc'))}" for k, v in branches.items()]
    return table + (
        "\n\nRegex tách theo nhánh: " + ", ".join(parts) +
        " — nó chỉ ăn ở nhánh có trích dẫn số điều. Cần tập test không shortcut "
        "thì lọc `metadata.narrow_mode == \"situation\"`."
    )


def _kappa_section(kappa: dict) -> str:
    if not kappa:
        return "_Chưa chạy vòng gán nhãn tay._"
    lines = [
        f"- Tổng: **κ = {kappa.get('cohen_kappa')}** "
        f"(n = {_num(kappa.get('n_samples'))} câu gán tay, đối chiếu "
        f"`{kappa.get('compared_against', 'judge_label')}`)",
    ]
    for mode, res in (kappa.get("by_narrow_mode") or {}).items():
        lines.append(
            f"- `narrow_mode = {mode}`: **κ = {res.get('cohen_kappa')}** "
            f"(n = {_num(res.get('n'))})"
        )
    if kappa.get("by_narrow_mode"):
        lines.append(
            "\nSố tổng che mất chênh lệch giữa hai nhánh — κ cao ở `citation` "
            "không bảo chứng cho chất lượng nhãn ở `situation`."
        )
    return "\n".join(lines)


def render_frontmatter(version: str, license_id: str,
                       split_alias: dict[str, str]) -> str:
    """Khối YAML đầu README — HuggingFace đọc nó để dựng trang và bật viewer."""
    data_files = "\n".join(
        f"      - split: {hub}\n        path: {local}.json"
        for local, hub in split_alias.items()
    )
    return f"""---
language:
  - vi
license: {license_id}
task_categories:
  - text-classification
annotations_creators:
  - machine-generated
pretty_name: Vietnamese Legal QA — Question Specificity ({version})
tags:
  - legal
  - vietnamese
  - question-classification
  - rag
  - synthetic
configs:
  - config_name: default
    data_files:
{data_files}
---
"""


def render_card_body(
    repo_id: str,
    version: str,
    stats: dict,
    baselines: dict,
    kappa: dict,
    split_alias: dict[str, str],
    updated: str | None = None,
) -> str:
    """Sinh phần thân (markdown) của dataset card."""
    updated = updated or date.today().isoformat()
    ratios = stats.get("ratios") or {}
    ratio_text = " / ".join(f"{k} {v:.0%}" for k, v in ratios.items()) or "chưa rõ"
    load_example = "\n".join(f'{hub} = ds["{hub}"]' for hub in split_alias.values())
    first_split = next(iter(split_alias.values()), "train")

    return f"""# Vietnamese Legal QA — Question Specificity ({version})

Phân loại **độ cụ thể của câu hỏi pháp luật dân sự Việt Nam**: `broad` (hỏi khái
quát, phải tổng hợp nhiều chế định) hay `narrow` (hỏi vào một tình huống / một
điều luật xác định). Dùng để định tuyến truy vấn trong hệ RAG pháp luật.

Cập nhật: **{updated}** · Phiên bản: **{version}**

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

{_split_table(stats, split_alias)}

Tỷ lệ {ratio_text}, seed `{stats.get('random_seed', '—')}`. **Split theo group
`source_doc_id`** — hai câu cùng cặp luôn cùng một split, nếu không là data leakage.

### Phân bố theo mảng luật

{_scope_table(stats)}

## Baseline tầm thường

**Thấp là tốt.** Đọc F1 của model cạnh bảng này, đừng đọc một mình.

{_baseline_section(baselines)}

## Độ tin cậy của nhãn

{_kappa_section(kappa)}

## Cách dùng

```python
from datasets import load_dataset

ds = load_dataset("{repo_id}")
{load_example}

print({first_split}[0]["question"], {first_split}[0]["final_label"])
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
"""


def main():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from config.qa_settings import (
        BASELINES_FILE,
        HF_DATASET_REPO_ID,
        HF_DATASET_VERSION,
        KAPPA_REPORT_FILE,
        QA_FINAL_DIR,
        STATS_FILE,
    )

    parser = argparse.ArgumentParser(description="Sinh dataset card cho dataset trên HuggingFace")
    parser.add_argument("--repo-id", default=HF_DATASET_REPO_ID or "<user>/<tên-dataset>",
                        help="Chỉ dùng cho ví dụ `load_dataset` trong card")
    parser.add_argument("--version", default=HF_DATASET_VERSION,
                        help="Nhãn phiên bản ghi vào card (vd: v3)")
    parser.add_argument("--license", default="other",
                        help="Định danh giấy phép theo danh mục của Hub")
    parser.add_argument("--output", type=Path, default=QA_FINAL_DIR / "README.md")
    args = parser.parse_args()

    stats = read_json(STATS_FILE)
    baselines = read_json(BASELINES_FILE)
    kappa = read_json(KAPPA_REPORT_FILE)
    for label, data in (("stats.json", stats), ("baselines.json", baselines),
                        ("kappa_report.json", kappa)):
        if not data:
            print(f"[!] Không đọc được {label} — card sẽ khuyết mục tương ứng.")

    card = render_frontmatter(args.version, args.license, SPLIT_ALIAS) + "\n" + \
        render_card_body(
            repo_id=args.repo_id,
            version=args.version,
            stats=stats,
            baselines=baselines,
            kappa=kappa,
            split_alias=SPLIT_ALIAS,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(card, encoding="utf-8")
    print(f"[OK] Da ghi {args.output}")


if __name__ == "__main__":
    main()