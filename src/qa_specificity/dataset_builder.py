"""
Hợp nhất 3 tầng nhãn, chia tập theo group, tính thống kê và export.

Hai quyết định thiết kế đáng chú ý nằm ở `filter_consensus` (ngữ nghĩa của
`ambiguous`) và `group_split` (vì sao không được random split) — xem docstring
của từng hàm.
"""

import json
import os
from collections import Counter
from pathlib import Path

# Phải đặt TRƯỚC khi numpy/scipy/sklearn được nạp lần đầu — OpenBLAS đọc mấy
# biến này lúc khởi tạo và cấp phát buffer cho MỖI thread theo số nhân CPU.
# Trên máy 20 nhân, lúc RAM đang căng (LM Studio giữ model + tải model khác),
# `from sklearn.model_selection import GroupShuffleSplit` chết ngay ở dòng
# import với "OpenBLAS error: Memory allocation still failed after 10 retries".
# Ta chỉ dùng sklearn để GỌI GroupShuffleSplit trên vài trăm phần tử — không có
# phép nhân ma trận nào đáng kể — nên ép 1 thread không mất gì về tốc độ, đổi
# lại bước export không chết vì lý do chẳng liên quan gì tới dữ liệu.
# `setdefault`: người dùng đã tự set thì tôn trọng, không ghi đè.
for _blas_var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_blas_var, "1")

from loguru import logger

from config.qa_settings import (
    RANDOM_SEED,
    TEST_RATIO,
    TRAIN_RATIO,
    VAL_RATIO,
)
from src.qa_specificity.schema import QAItem, Specificity


# ══════════════════════════════════════════════════════════════════
# Hợp nhất nhãn
# ══════════════════════════════════════════════════════════════════

def resolve_item(item: QAItem, strict: bool = False) -> QAItem:
    """
    Quyết định `final_label` cho một item từ 3 tầng nhãn, gán tại chỗ.

    ─── Vì sao `ambiguous` là ABSTAIN chứ không phải phiếu chống ───

    Spec §4 bước 2 nói "chỉ giữ item có cả 3 tầng cùng nhãn". Đọc chữ thì item
    nào heuristic trả `ambiguous` đều bị loại. Nhưng guideline §6 định nghĩa
    `ambiguous` là "nhường quyết định cho LLM judge và tầng provenance" —
    tức là tầng đó TỰ NHẬN KHÔNG ĐỦ CĂN CỨ, không phải bất đồng.

    Hai cách đọc cho kết quả rất khác nhau: heuristic chỉ chấm được 2/3 trục nên
    `ambiguous` sẽ rất phổ biến; coi nó là bất đồng thì pass rate rơi xuống dưới
    ngưỡng 40% của spec vì lý do kỹ thuật, không phải vì dữ liệu xấu — rồi ta
    lại đi sửa prompt sinh câu, trong khi prompt không có lỗi gì.

    Nên: mặc định ABSTAIN. Judge trả `ambiguous` thì vẫn LOẠI, vì judge chấm đủ
    cả 3 trục nên `ambiguous` của judge là kết luận "câu này vùng xám"
    (guideline §5.3) chứ không phải "tôi không biết".

    `strict=True` cho phép chạy lại theo cách đọc chặt để đối chiếu; script 07
    báo cáo cả hai con số nên phần Limitations của báo cáo có số mà nói.
    """
    provenance = item.specificity
    heuristic = item.heuristic_label
    judge = item.judge_label

    # Judge vắng mặt (lỗi API / không parse được) — không có tầng độc lập nào
    # đối chứng với provenance, giữ lại là tự lừa mình.
    if judge is None:
        item.final_label = None
        item.consensus = False
        item.reject_reason = "judge_missing"
        return item

    # Judge kết luận vùng xám ⇒ loại (guideline §2.2 quy tắc vùng xám:
    # loại bỏ, không ép nhãn).
    if judge == Specificity.AMBIGUOUS:
        item.final_label = None
        item.consensus = False
        item.reject_reason = "judge_ambiguous"
        return item

    if provenance != judge:
        item.final_label = None
        item.consensus = False
        item.reject_reason = "provenance_vs_judge_mismatch"
        return item

    # Tới đây provenance == judge và đều là nhãn thật.
    if heuristic is None:
        item.final_label = None
        item.consensus = False
        item.reject_reason = "heuristic_missing"
        return item

    if heuristic == Specificity.AMBIGUOUS:
        if strict:
            item.final_label = None
            item.consensus = False
            item.reject_reason = "heuristic_ambiguous_strict"
            return item
        # Abstain: hai tầng còn lại đã đồng thuận, đủ căn cứ.
        item.final_label = judge
        item.consensus = True
        item.reject_reason = ""
        return item

    if heuristic != judge:
        item.final_label = None
        item.consensus = False
        item.reject_reason = "heuristic_vs_judge_mismatch"
        return item

    item.final_label = judge
    item.consensus = True
    item.reject_reason = ""
    return item


def filter_consensus(
    items: list[QAItem],
    strict: bool = False,
    require_complete_pairs: bool = True,
) -> tuple[list[QAItem], list[QAItem]]:
    """
    Chia items thành (verified, rejected).

    Args:
        strict: xem `resolve_item`.
        require_complete_pairs: chỉ giữ cặp còn ĐỦ CẢ HAI vế.
            Giữ cặp khuyết vế làm hỏng thiết kế đối chứng: nếu vế narrow bị loại
            nhiều hơn vế broad thì phân bố chủ đề của hai lớp lệch trở lại đúng
            cái confound mà việc sinh theo cặp sinh ra để triệt tiêu.
    """
    for item in items:
        resolve_item(item, strict=strict)

    verified = [i for i in items if i.consensus]
    rejected = [i for i in items if not i.consensus]

    if require_complete_pairs:
        pair_labels: dict[str, set] = {}
        for item in verified:
            pair_labels.setdefault(item.pair_id, set()).add(item.final_label)

        # Cặp hợp lệ = còn đủ 2 vế và hai vế mang hai nhãn khác nhau
        complete = {pid for pid, labels in pair_labels.items() if len(labels) == 2}

        dropped = [i for i in verified if i.pair_id not in complete]
        for item in dropped:
            item.consensus = False
            item.final_label = None
            item.reject_reason = "incomplete_pair"
        verified = [i for i in verified if i.pair_id in complete]
        rejected.extend(dropped)

        if dropped:
            logger.info(f"Loại thêm {len(dropped)} câu vì cặp không còn đủ 2 vế")

    logger.info(
        f"Đồng thuận: {len(verified)}/{len(items)} câu giữ lại "
        f"({len(verified) / max(len(items), 1):.1%})"
    )
    return verified, rejected


def build_verification_stats(
    all_items: list[QAItem],
    verified: list[QAItem],
    rejected: list[QAItem],
    strict_verified_count: int | None = None,
) -> dict:
    """Thống kê pass/reject theo tầng — deliverable #4 của spec §5.1."""
    total = len(all_items)
    reject_reasons = Counter(i.reject_reason for i in rejected if i.reject_reason)

    def _label_dist(items, attr):
        counter = Counter()
        for item in items:
            value = getattr(item, attr)
            counter[value.value if isinstance(value, Specificity) else "none"] += 1
        return dict(counter)

    agree_prov_judge = sum(
        1 for i in all_items
        if i.judge_label is not None and i.judge_label == i.specificity
    )
    agree_prov_heur = sum(
        1 for i in all_items
        if i.heuristic_label is not None and i.heuristic_label == i.specificity
    )
    agree_heur_judge = sum(
        1 for i in all_items
        if i.heuristic_label is not None and i.judge_label is not None
        and i.heuristic_label == i.judge_label
    )

    stats = {
        "total_items": total,
        "total_pairs_input": len({i.pair_id for i in all_items}),
        "verified_items": len(verified),
        "verified_pairs": len({i.pair_id for i in verified}),
        "rejected_items": len(rejected),
        "pass_rate": round(len(verified) / total, 4) if total else 0.0,
        "reject_reasons": dict(reject_reasons.most_common()),
        "label_distribution": {
            "provenance": _label_dist(all_items, "specificity"),
            "heuristic": _label_dist(all_items, "heuristic_label"),
            "judge": _label_dist(all_items, "judge_label"),
            "final_verified": _label_dist(verified, "final_label"),
        },
        "pairwise_agreement": {
            "provenance_vs_judge": round(agree_prov_judge / total, 4) if total else 0.0,
            "provenance_vs_heuristic": round(agree_prov_heur / total, 4) if total else 0.0,
            "heuristic_vs_judge": round(agree_heur_judge / total, 4) if total else 0.0,
        },
    }

    if strict_verified_count is not None:
        stats["strict_consensus"] = {
            "verified_items": strict_verified_count,
            "pass_rate": round(strict_verified_count / total, 4) if total else 0.0,
            "note": (
                "Cách đọc chặt: heuristic trả 'ambiguous' cũng bị coi là bất đồng. "
                "Con số mặc định ở trên dùng cách đọc abstain theo guideline §6."
            ),
        }

    return stats


# ══════════════════════════════════════════════════════════════════
# Chia tập
# ══════════════════════════════════════════════════════════════════

def group_split(
    items: list[QAItem],
    train_ratio: float = TRAIN_RATIO,
    val_ratio: float = VAL_RATIO,
    test_ratio: float = TEST_RATIO,
    seed: int = RANDOM_SEED,
) -> dict[str, list[QAItem]]:
    """
    Chia train/val/test theo GROUP = `source_doc_id`.

    ─── Vì sao bắt buộc group split, không được random split ───
    Hai câu trong một cặp cùng sinh từ một văn bản, nội dung chồng lấn rất
    nhiều. Nếu câu broad rơi vào train còn câu narrow rơi vào test thì model đã
    "thấy" nội dung điều luật đó lúc train và ăn điểm ở test — data leakage.
    Lỗi này nguy hiểm vì nó KHÔNG BÁO LỖI GÌ CẢ, chỉ âm thầm cho ra một con số
    đẹp không có thật.

    Chia theo `source_doc_id` (chứ không theo `pair_id`) là mức bảo thủ hơn:
    một văn bản có thể sinh ra nhiều cặp, và các cặp đó cũng chồng lấn nội dung.

    Returns:
        {"train": [...], "val": [...], "test": [...]}
    """
    from sklearn.model_selection import GroupShuffleSplit

    if not items:
        return {"train": [], "val": [], "test": []}

    total_ratio = train_ratio + val_ratio + test_ratio
    if abs(total_ratio - 1.0) > 1e-6:
        raise ValueError(f"Tỷ lệ split cộng lại phải bằng 1.0, đang là {total_ratio}")

    groups = [item.source_doc_id for item in items]
    indices = list(range(len(items)))
    n_groups = len(set(groups))

    if n_groups < 3:
        raise ValueError(
            f"Chỉ có {n_groups} source_doc_id duy nhất — không đủ để chia 3 tập mà "
            f"không rò rỉ. Cần sinh thêm dữ liệu từ nhiều văn bản hơn."
        )

    # Vòng 1: train vs (val + test)
    splitter1 = GroupShuffleSplit(n_splits=1, test_size=val_ratio + test_ratio, random_state=seed)
    train_idx, holdout_idx = next(splitter1.split(indices, groups=groups))

    # Vòng 2: tách holdout thành val / test theo tỷ lệ tương đối
    holdout_groups = [groups[i] for i in holdout_idx]
    relative_test = test_ratio / (val_ratio + test_ratio)

    if len(set(holdout_groups)) < 2:
        logger.warning(
            "Holdout chỉ có 1 group — dồn hết vào test, val sẽ rỗng. "
            "Cần thêm văn bản nguồn."
        )
        val_idx, test_idx = [], list(holdout_idx)
    else:
        splitter2 = GroupShuffleSplit(n_splits=1, test_size=relative_test, random_state=seed)
        rel_val, rel_test = next(splitter2.split(list(range(len(holdout_idx))), groups=holdout_groups))
        val_idx = [holdout_idx[i] for i in rel_val]
        test_idx = [holdout_idx[i] for i in rel_test]

    splits = {
        "train": [items[i] for i in train_idx],
        "val": [items[i] for i in val_idx],
        "test": [items[i] for i in test_idx],
    }

    for name, subset in splits.items():
        n_docs = len({i.source_doc_id for i in subset})
        logger.info(f"  {name:5s}: {len(subset):4d} câu | {n_docs} văn bản")

    assert_no_leakage(splits)
    return splits


def assert_no_leakage(splits: dict[str, list[QAItem]]):
    """
    Bất biến bắt buộc: không `source_doc_id` nào xuất hiện ở hai split.

    Kéo theo cả hai vế của mọi cặp luôn nằm cùng một split, vì cặp nào cũng
    chia sẻ `source_doc_id`.

    Raises:
        AssertionError: khi phát hiện rò rỉ.
    """
    doc_ids = {name: {i.source_doc_id for i in subset} for name, subset in splits.items()}

    for a, b in (("train", "val"), ("train", "test"), ("val", "test")):
        overlap = doc_ids[a] & doc_ids[b]
        assert not overlap, (
            f"DATA LEAKAGE: {len(overlap)} source_doc_id xuất hiện ở cả '{a}' và '{b}'. "
            f"Ví dụ: {sorted(overlap)[:5]}"
        )

    pair_split: dict[str, str] = {}
    for name, subset in splits.items():
        for item in subset:
            previous = pair_split.setdefault(item.pair_id, name)
            assert previous == name, (
                f"DATA LEAKAGE: pair_id {item.pair_id} bị chia đôi giữa "
                f"'{previous}' và '{name}'"
            )


# ══════════════════════════════════════════════════════════════════
# Thống kê & export
# ══════════════════════════════════════════════════════════════════

def build_stats(splits: dict[str, list[QAItem]]) -> dict:
    """Thống kê dataset cuối — deliverable #2 của spec §5.1."""
    stats = {
        "random_seed": RANDOM_SEED,
        "ratios": {"train": TRAIN_RATIO, "val": VAL_RATIO, "test": TEST_RATIO},
        "total_items": sum(len(s) for s in splits.values()),
        "total_pairs": len({i.pair_id for s in splits.values() for i in s}),
        "total_source_docs": len({i.source_doc_id for s in splits.values() for i in s}),
        "splits": {},
        "leakage_check": "passed",
    }

    for name, subset in splits.items():
        labels = Counter(
            i.final_label.value for i in subset if isinstance(i.final_label, Specificity)
        )
        scopes = Counter(i.metadata.get("scope", "") or "unknown" for i in subset)
        lengths = [len(i.question.split()) for i in subset]
        n_total = len(subset)

        stats["splits"][name] = {
            "n_items": n_total,
            "n_pairs": len({i.pair_id for i in subset}),
            "n_source_docs": len({i.source_doc_id for i in subset}),
            "label_counts": dict(labels),
            "label_balance": {
                label: round(count / n_total, 4) for label, count in labels.items()
            } if n_total else {},
            "scope_counts": dict(scopes),
            "question_words": {
                "mean": round(sum(lengths) / n_total, 2) if n_total else 0,
                "min": min(lengths) if lengths else 0,
                "max": max(lengths) if lengths else 0,
            },
        }

    # Cảnh báo mất cân bằng: nhãn lệch quá thì accuracy mất ý nghĩa (spec §7)
    warnings = []
    for name, split_stats in stats["splits"].items():
        balance = split_stats["label_balance"]
        if balance and (max(balance.values()) > 0.65 or len(balance) < 2):
            warnings.append(
                f"Split '{name}' mất cân bằng nhãn ({balance}) — đọc F1 theo từng lớp, "
                f"đừng đọc accuracy."
            )
    if warnings:
        stats["warnings"] = warnings
        for warning in warnings:
            logger.warning(warning)

    return stats


def export(splits: dict[str, list[QAItem]], paths: dict[str, Path]) -> dict:
    """
    Ghi train/val/test ra JSON (mảng object, dễ đọc bằng mắt hơn JSONL).

    Args:
        splits: kết quả `group_split`.
        paths: {"train": Path, "val": Path, "test": Path}.
    """
    for name, subset in splits.items():
        filepath = paths[name]
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump([i.to_dict() for i in subset], f, ensure_ascii=False, indent=2)
        logger.info(f"Đã ghi {len(subset)} câu → {filepath}")
    return {name: str(paths[name]) for name in splits}


def save_json(data: dict, filepath: Path):
    """Ghi một dict ra file JSON có indent."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Đã ghi → {filepath}")


# ══════════════════════════════════════════════════════════════════
# Bước 3 — độ tin cậy liên người gán nhãn
# ══════════════════════════════════════════════════════════════════

def compute_kappa(manual_labels: list[str], machine_labels: list[str]) -> dict:
    """
    Cohen's kappa giữa nhãn gán tay và nhãn máy.

    κ đo mức đồng thuận đã TRỪ đi phần trùng nhau do ngẫu nhiên — cần trừ vì
    với bài toán nhị phân, hai người gán bừa vẫn trùng nhau khoảng 50%.

    Thang đọc (guideline §7): κ > 0.8 tốt; 0.6-0.8 chấp nhận được;
    < 0.6 nghĩa là TIÊU CHÍ trong guideline chưa đủ rõ — sửa guideline, không
    phải sửa code.
    """
    from sklearn.metrics import cohen_kappa_score, confusion_matrix

    if len(manual_labels) != len(machine_labels):
        raise ValueError(
            f"Số nhãn không khớp: tay={len(manual_labels)}, máy={len(machine_labels)}"
        )
    if not manual_labels:
        raise ValueError("Không có nhãn nào để tính kappa")

    labels = sorted(set(manual_labels) | set(machine_labels))
    kappa = float(cohen_kappa_score(manual_labels, machine_labels, labels=labels))
    matrix = confusion_matrix(manual_labels, machine_labels, labels=labels).tolist()
    agreement = sum(1 for a, b in zip(manual_labels, machine_labels) if a == b) / len(manual_labels)

    if kappa > 0.8:
        interpretation = "Đồng thuận tốt — dùng dataset, báo cáo con số này"
    elif kappa >= 0.6:
        interpretation = "Chấp nhận được — dùng được, nêu rõ trong báo cáo"
    else:
        interpretation = (
            "κ thấp: tiêu chí trong docs/specificity-guideline.md chưa đủ rõ. "
            "Sửa GUIDELINE rồi gán nhãn lại, không phải sửa code."
        )

    return {
        "n_samples": len(manual_labels),
        "cohen_kappa": round(kappa, 4),
        "raw_agreement": round(agreement, 4),
        "labels": labels,
        "confusion_matrix": matrix,
        "confusion_matrix_note": "hàng = nhãn tay, cột = nhãn máy, thứ tự theo `labels`",
        "interpretation": interpretation,
    }
