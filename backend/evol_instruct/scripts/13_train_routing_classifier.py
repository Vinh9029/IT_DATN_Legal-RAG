"""
Script 13 — Fine-tune PhoBERT Routing Classifier (Broad / Narrow)
====================================================================
Dùng LoRA (PEFT) để fine-tune `vinai/phobert-base-v2` cho bài toán phân loại
câu hỏi pháp lý:
    - broad  (0): câu hỏi tổng quát, cần recall cao
    - narrow (1): câu hỏi cụ thể, cần precision cao

Input  : backend/data/qa_pairs/final/{train,val,test}.json
Output : backend/models/routing_classifier/  (adapter + tokenizer + train_config.json
         + eval_report.json)

─── Vì sao LoRA thường, không QLoRA ───
PhoBERT-base chỉ ~135M tham số (~540 MB FP32) — lượng tử 4-bit không tiết kiệm
được gì đáng kể, còn kéo theo bitsandbytes (không có bản CPU/Windows ổn định).
LoRA r=16 trên query/value + head phân loại là đủ, chạy được cả trên CPU.

─── Hai điểm hay làm sai ───
1. PhoBERT cần input ĐÃ tách từ ("khởi_kiện"). Train và inference cùng gọi
   `segment_vi()` trong routing_classifier.py — đừng tách bằng công cụ khác ở
   một phía.
2. F1 trên test KHÔNG tự nói lên gì: TF-IDF + LR đã đạt ~98% trên chính tập này
   (xem baselines.json, script 14). Script in kết quả CẠNH các baseline và tách
   theo `narrow_mode` để thấy model hơn baseline ở đâu.

Chạy từ thư mục backend/:
    python evol_instruct/scripts/13_train_routing_classifier.py
    python evol_instruct/scripts/13_train_routing_classifier.py --limit 200 --epochs 1   # chạy thử
    python evol_instruct/scripts/13_train_routing_classifier.py --no-segment              # ablation

Yêu cầu:
    pip install transformers peft accelerate scikit-learn underthesea
"""

import argparse
import json
import random
import shutil
import sys
import logging
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch
import numpy as np
from torch.utils.data import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback,
    DataCollatorWithPadding,
)
from peft import get_peft_model, LoraConfig, TaskType
from sklearn.metrics import f1_score, accuracy_score, classification_report

from evol_instruct.src.qa_specificity.routing_classifier import (
    RoutingClassifier,
    SEGMENTER_NAME,
    segment_vi,
)

# ─── Đường dẫn ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]          # backend/
DATA_DIR = ROOT / "data" / "qa_pairs" / "final"
OUTPUT_DIR = ROOT / "models" / "routing_classifier"
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"         # xoá sau khi lưu model tốt nhất


# ─── Hyper-parameters ─────────────────────────────────────────────────────────
@dataclass
class TrainConfig:
    base_model: str = "vinai/phobert-base-v2"
    # LoRA
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    # Training
    max_length: int = 256
    batch_size: int = 16
    gradient_accumulation: int = 2
    num_epochs: int = 5
    learning_rate: float = 2e-4
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    seed: int = 42
    segment: bool = True
    # Labels
    label2id: dict = field(default_factory=lambda: {"broad": 0, "narrow": 1})
    id2label: dict = field(default_factory=lambda: {0: "broad", 1: "narrow"})


CFG = TrainConfig()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def rel(path: Path) -> str:
    """Đường dẫn tương đối so với backend/ — không ghi đường dẫn tuyệt đối ra file."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def label_of(item: dict) -> str | None:
    # final_label là nhãn đã qua consensus; hai khoá sau chỉ để đọc được bản export cũ.
    return item.get("final_label") or item.get("judge_label") or item.get("specificity")


def branch_of(item: dict) -> str:
    return (item.get("metadata") or {}).get("narrow_mode", "?")


# ─── Dataset ──────────────────────────────────────────────────────────────────
class QASpecificityDataset(Dataset):
    """Load {train,val,test}.json, tách từ và tokenize cho PhoBERT."""

    def __init__(self, json_path: Path, tokenizer, max_length: int, segment: bool,
                 limit: int | None = None):
        logger.info(f"Loading: {rel(json_path)}")
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        if limit:
            raw = random.Random(CFG.seed).sample(raw, min(limit, len(raw)))

        self.items, texts, self.labels = [], [], []
        skipped = 0
        for item in raw:
            label_str = label_of(item)
            if label_str not in CFG.label2id:
                skipped += 1
                continue
            self.items.append(item)
            texts.append(segment_vi(item["question"]) if segment else item["question"])
            self.labels.append(CFG.label2id[label_str])

        logger.info(f"  Loaded {len(texts)} samples (skipped {skipped})")

        # Tokenize toàn bộ một lần (dynamic padding qua DataCollator)
        self.encodings = tokenizer(texts, max_length=max_length, truncation=True, padding=False)
        n_trunc = sum(len(ids) >= max_length for ids in self.encodings["input_ids"])
        if n_trunc:
            logger.warning(f"  {n_trunc} câu bị cắt ở max_length={max_length}")

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item

    def label_distribution(self):
        broad = self.labels.count(0)
        narrow = self.labels.count(1)
        return {"broad": broad, "narrow": narrow, "total": len(self.labels)}


# ─── Metrics ──────────────────────────────────────────────────────────────────
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "f1_macro":  round(f1_score(labels, preds, average="macro"), 4),
        "f1_broad":  round(f1_score(labels, preds, pos_label=0, average="binary"), 4),
        "f1_narrow": round(f1_score(labels, preds, pos_label=1, average="binary"), 4),
        "accuracy":  round(accuracy_score(labels, preds), 4),
    }


def split_report(items: list[dict], y_true, y_pred) -> dict:
    """Accuracy/F1 tổng và tách theo narrow_mode — số gộp che mất nhánh yếu."""
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    out = {
        "n": int(len(y_true)),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro")), 4),
        "theo_nhanh": {},
    }
    branches = np.asarray([branch_of(it) for it in items], dtype=object)
    for b in sorted(set(branches)):
        m = branches == b
        out["theo_nhanh"][b] = {
            "n": int(m.sum()),
            "accuracy": round(float(accuracy_score(y_true[m], y_pred[m])), 4),
        }
    return out


def load_baselines() -> dict:
    """Baseline đã đo bằng script 14 trên CHÍNH tập test này (nếu có)."""
    p = DATA_DIR / "baselines.json"
    if not p.exists():
        return {}
    cur = json.loads(p.read_text(encoding="utf-8")).get("hien_tai", {})
    return {
        "shortcut_regex_dieu": cur.get("shortcut", {}).get("tong"),
        "tfidf_lr": cur.get("tfidf"),
    }


# ─── Model ────────────────────────────────────────────────────────────────────
def build_model_and_tokenizer(cfg: TrainConfig):
    logger.info(f"Loading tokenizer: {cfg.base_model}")
    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model, use_fast=False)

    logger.info(f"Loading sequence classification model (FP32): {cfg.base_model}")
    model = AutoModelForSequenceClassification.from_pretrained(
        cfg.base_model,
        num_labels=2,
        id2label=cfg.id2label,
        label2id=cfg.label2id,
        dtype=torch.float32,
    )

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,          # tự thêm head "classifier" vào modules_to_save
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules=["query", "value"],   # BERT attention projections
        bias="none",
        inference_mode=False,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model, tokenizer


# ─── Main ─────────────────────────────────────────────────────────────────────
def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--epochs", type=int, default=CFG.num_epochs)
    ap.add_argument("--limit", type=int, default=None,
                    help="Chỉ lấy N mẫu mỗi split (chạy thử pipeline)")
    ap.add_argument("--no-segment", action="store_true",
                    help="Bỏ bước tách từ (chỉ để ablation, KHÔNG dùng cho model thật)")
    return ap.parse_args()


def main():
    args = parse_args()
    CFG.num_epochs = args.epochs
    CFG.segment = not args.no_segment

    random.seed(CFG.seed)
    np.random.seed(CFG.seed)
    torch.manual_seed(CFG.seed)

    for split in ("train", "val", "test"):
        p = DATA_DIR / f"{split}.json"
        if not p.exists():
            logger.error(f"Không tìm thấy: {rel(p)}")
            sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model, tokenizer = build_model_and_tokenizer(CFG)
    collator = DataCollatorWithPadding(tokenizer=tokenizer)

    datasets = {
        split: QASpecificityDataset(DATA_DIR / f"{split}.json", tokenizer,
                                    CFG.max_length, CFG.segment, args.limit)
        for split in ("train", "val", "test")
    }
    for split, ds in datasets.items():
        logger.info(f"{split:5s}: {ds.label_distribution()}")

    use_cuda = torch.cuda.is_available()
    training_args = TrainingArguments(
        output_dir=str(CHECKPOINT_DIR),
        num_train_epochs=CFG.num_epochs,
        per_device_train_batch_size=CFG.batch_size,
        per_device_eval_batch_size=CFG.batch_size * 2,
        gradient_accumulation_steps=CFG.gradient_accumulation,
        learning_rate=CFG.learning_rate,
        weight_decay=CFG.weight_decay,
        warmup_steps=CFG.warmup_ratio,   # transformers 5: float < 1 = tỉ lệ (warmup_ratio đã bị bỏ)
        lr_scheduler_type="cosine",
        fp16=use_cuda,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        save_total_limit=2,
        logging_steps=50,
        report_to="none",
        seed=CFG.seed,
        dataloader_num_workers=0,   # Windows: giữ 0 tránh lỗi multiprocess
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=datasets["train"],
        eval_dataset=datasets["val"],
        processing_class=tokenizer,
        data_collator=collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    logger.info("=" * 60)
    logger.info("Fine-tune PhoBERT Routing Classifier (Broad / Narrow)")
    logger.info(f"  Base model : {CFG.base_model}")
    logger.info(f"  Tách từ    : {SEGMENTER_NAME if CFG.segment else 'KHÔNG (ablation)'}")
    logger.info(f"  Device     : {'cuda (fp16)' if use_cuda else 'cpu (fp32)'}")
    logger.info(f"  LoRA       : r={CFG.lora_r}, alpha={CFG.lora_alpha}")
    logger.info(f"  Epochs     : {CFG.num_epochs} | Batch: {CFG.batch_size}x{CFG.gradient_accumulation}")
    logger.info(f"  Output     : {rel(OUTPUT_DIR)}")
    logger.info("=" * 60)

    trainer.train()

    # ─── Đánh giá: val để chọn model, test để báo cáo ─────────────────────────
    val_metrics = trainer.evaluate()
    report = {"val": {}, "test": {}}
    for split in ("val", "test"):
        ds = datasets[split]
        out = trainer.predict(ds)
        y_pred = np.argmax(out.predictions, axis=-1)
        report[split] = split_report(ds.items, out.label_ids, y_pred)
        logger.info(f"\n--- {split.upper()} ---\n" + classification_report(
            out.label_ids, y_pred, target_names=["broad", "narrow"], digits=4))

    # Heuristic fallback hiện chạy trong production khi chưa có adapter — đo cạnh model.
    test_ds = datasets["test"]
    heur = [CFG.label2id[RoutingClassifier._heuristic_fallback(it["question"])]
            for it in test_ds.items]
    report["test_heuristic_fallback"] = split_report(test_ds.items, test_ds.labels, heur)
    report["test_baselines_script14"] = load_baselines()

    logger.info("=" * 60)
    logger.info("TEST accuracy (cao là tốt cho model; baseline càng thấp bài toán càng thật)")
    logger.info(f"  PhoBERT-LoRA       : {report['test']['accuracy']:.4f}  "
                f"{ {str(b): v['accuracy'] for b, v in report['test']['theo_nhanh'].items()} }")
    logger.info(f"  Heuristic >12 từ   : {report['test_heuristic_fallback']['accuracy']:.4f}")
    for k, v in report["test_baselines_script14"].items():
        if v is not None and not args.limit:
            logger.info(f"  {k:19s}: {v:.4f}")
    logger.info("=" * 60)

    # ─── Lưu adapter + tokenizer + metadata ───────────────────────────────────
    trainer.save_model(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    shutil.rmtree(CHECKPOINT_DIR, ignore_errors=True)

    meta = {
        "base_model": CFG.base_model,
        "label2id": CFG.label2id,
        "id2label": {str(k): v for k, v in CFG.id2label.items()},
        "max_length": CFG.max_length,
        # routing_classifier.py đọc khoá này để tách từ đúng như lúc train.
        "segmenter": SEGMENTER_NAME if CFG.segment else None,
        "data_dir": rel(DATA_DIR),
        "limit": args.limit,
        "epochs_run": round(float(trainer.state.epoch or 0), 2),
        "val_f1_macro": val_metrics.get("eval_f1_macro", -1),
        "test_f1_macro": report["test"]["f1_macro"],
        "test_accuracy": report["test"]["accuracy"],
    }
    (OUTPUT_DIR / "train_config.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "eval_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"\n✅ Hoàn tất! Adapter lưu tại: {rel(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()
