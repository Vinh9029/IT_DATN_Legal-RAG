"""
Script 13 — Fine-tune PhoBERT Routing Classifier (Broad / Narrow)
====================================================================
Dùng QLoRA (bitsandbytes 4-bit + PEFT LoRA) để fine-tune
`vinai/phobert-base-v2` cho bài toán phân loại câu hỏi pháp lý:
    - broad  (0): câu hỏi tổng quát, cần recall cao
    - narrow (1): câu hỏi cụ thể, cần precision cao

Input  : backend/data/qa_pairs/final/{train,val}.json
Output : backend/models/routing_classifier/  (adapter + tokenizer)

Chạy từ thư mục backend/:
    python evol_instruct/scripts/13_train_routing_classifier.py

Yêu cầu:
    pip install transformers peft bitsandbytes accelerate scikit-learn
    (bitsandbytes Windows: pip install bitsandbytes --prefer-binary)
"""

import json
import sys
import logging
from pathlib import Path
from dataclasses import dataclass, field

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
    BitsAndBytesConfig,
)
from peft import (
    get_peft_model,
    LoraConfig,
    TaskType,
    prepare_model_for_kbit_training,
)
from sklearn.metrics import f1_score, accuracy_score, classification_report

# ─── Đường dẫn ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]          # backend/
DATA_DIR = ROOT / "data" / "qa_pairs" / "final"
OUTPUT_DIR = ROOT / "models" / "routing_classifier"
LOG_DIR = OUTPUT_DIR / "logs"

# ─── Hyper-parameters ─────────────────────────────────────────────────────────
@dataclass
class TrainConfig:
    base_model: str = "vinai/phobert-base-v2"
    # QLoRA
    use_qlora: bool = True          # False → plain LoRA (CPU / không có GPU)
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


# ─── Dataset ──────────────────────────────────────────────────────────────────
class QASpecificityDataset(Dataset):
    """Load train.json / val.json và chuẩn bị input cho PhoBERT."""

    def __init__(self, json_path: Path, tokenizer, max_length: int = 256):
        logger.info(f"Loading: {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        texts, labels = [], []
        skipped = 0
        for item in raw:
            # Ưu tiên final_label → judge_label → specificity
            label_str = (
                item.get("final_label")
                or item.get("judge_label")
                or item.get("specificity")
            )
            if label_str not in CFG.label2id:
                skipped += 1
                continue
            texts.append(item["question"])
            labels.append(CFG.label2id[label_str])

        logger.info(f"  Loaded {len(texts)} samples (skipped {skipped})")

        # Tokenize toàn bộ một lần (dynamic padding qua DataCollator)
        self.encodings = tokenizer(
            texts,
            max_length=max_length,
            truncation=True,
            padding=False,
        )
        self.labels = labels

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


# ─── Model ────────────────────────────────────────────────────────────────────
def build_model_and_tokenizer(cfg: TrainConfig):
    logger.info(f"Loading tokenizer: {cfg.base_model}")
    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model, use_fast=False)

    has_cuda = torch.cuda.is_available()
    torch_dtype = torch.float16 if has_cuda else torch.float32

    logger.info(f"Loading sequence classification model (float32): {cfg.base_model}")
    model = AutoModelForSequenceClassification.from_pretrained(
        cfg.base_model,
        num_labels=2,
        id2label=cfg.id2label,
        label2id=cfg.label2id,
        torch_dtype=torch.float32,
    )

    if has_cuda:
        model = model.to("cuda")

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
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
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    for split in ("train", "val"):
        p = DATA_DIR / f"{split}.json"
        if not p.exists():
            logger.error(f"Không tìm thấy: {p}")
            sys.exit(1)

    model, tokenizer = build_model_and_tokenizer(CFG)
    collator = DataCollatorWithPadding(tokenizer=tokenizer)

    train_ds = QASpecificityDataset(DATA_DIR / "train.json", tokenizer, CFG.max_length)
    val_ds   = QASpecificityDataset(DATA_DIR / "val.json",   tokenizer, CFG.max_length)

    logger.info(f"Train: {train_ds.label_distribution()}")
    logger.info(f"Val  : {val_ds.label_distribution()}")

    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR),
        logging_dir=str(LOG_DIR),
        num_train_epochs=CFG.num_epochs,
        per_device_train_batch_size=CFG.batch_size,
        per_device_eval_batch_size=CFG.batch_size * 2,
        gradient_accumulation_steps=CFG.gradient_accumulation,
        learning_rate=CFG.learning_rate,
        weight_decay=CFG.weight_decay,
        warmup_ratio=CFG.warmup_ratio,
        lr_scheduler_type="cosine",
        fp16=False,
        bf16=False,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        save_total_limit=2,
        logging_steps=50,
        report_to="none",
        seed=42,
        dataloader_num_workers=0,   # Windows: giữ 0 tránh lỗi multiprocess
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        tokenizer=tokenizer,
        data_collator=collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    logger.info("=" * 60)
    logger.info("Fine-tune PhoBERT Routing Classifier (Broad / Narrow)")
    logger.info(f"  Base model : {CFG.base_model}")
    logger.info(f"  Precision  : FP32 | GPU: {torch.cuda.is_available()}")
    logger.info(f"  LoRA       : r={CFG.lora_r}, alpha={CFG.lora_alpha}")
    logger.info(f"  Epochs     : {CFG.num_epochs} | Batch: {CFG.batch_size}")
    logger.info(f"  Output     : {OUTPUT_DIR}")
    logger.info("=" * 60)

    trainer.train()

    # Đánh giá chi tiết
    logger.info("\n--- Val Set Evaluation ---")
    metrics = trainer.evaluate()
    for k, v in metrics.items():
        logger.info(f"  {k}: {v}")

    preds_out = trainer.predict(val_ds)
    pred_labels = np.argmax(preds_out.predictions, axis=-1)
    true_labels = preds_out.label_ids
    report = classification_report(
        true_labels, pred_labels,
        target_names=["broad", "narrow"],
        digits=4,
    )
    logger.info(f"\n{report}")

    # Lưu adapter + tokenizer
    trainer.save_model(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))

    # Lưu metadata để routing_classifier.py tự biết cấu hình
    meta = {
        "base_model": CFG.base_model,
        "label2id": CFG.label2id,
        "id2label": {str(k): v for k, v in CFG.id2label.items()},
        "max_length": CFG.max_length,
        "val_f1_macro": metrics.get("eval_f1_macro", -1),
    }
    with open(OUTPUT_DIR / "train_config.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    logger.info(f"\n✅ Hoàn tất! Adapter lưu tại: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
