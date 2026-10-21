"""
Script 20 — QLoRA fine-tune Llama-3.1-8B-Instruct trên dữ liệu Evol-Instruct.

Đầu ra: LoRA adapter ở models/legal_generator_lora/ (gitignored). Prompt giống
responder lúc sinh dữ liệu nhưng bỏ ví dụ few-shot; loss chỉ tính trên câu trả lời.

Cần venv có torch CUDA (xem mục fine-tune trong requirements.txt) và phải
`lms unload --all` trước — train chiếm ~11 GB VRAM. Chạy từ backend/ bằng python của venv đó:

    python evol_instruct/scripts/20_finetune_generator.py
    python evol_instruct/scripts/20_finetune_generator.py --limit 40 --epochs 1   # chạy thử
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA = BACKEND_DIR / "data" / "evol_instruct" / "output" / "legal_evolved.jsonl"
DEFAULT_OUT = BACKEND_DIR / "models" / "legal_generator_lora"
BASE_MODEL = "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"   # bản NF4 sẵn, không gated


def build_messages(record: dict) -> list[dict]:
    """Chat messages của một record — dùng chung cho train và script 21."""
    from config.prompts import SYSTEM_IRAC_RESPONDER, GROUNDED_RULE, GROUNDED_USER_TEMPLATE

    context = record.get("input") or ""
    system = SYSTEM_IRAC_RESPONDER + ("\n" + GROUNDED_RULE if context else "")
    user = (
        GROUNDED_USER_TEMPLATE.format(context=context, instruction=record["instruction"])
        if context else record["instruction"]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_FIRST_IRAC_HEADING = "**Vấn đề"
MAX_PREAMBLE_CHARS = 200


def clean_answer(output: str) -> str:
    """Gọt câu dẫn ngắn trước tiêu đề IRAC đầu tiên (~11% bản ghi có)."""
    idx = output.find(_FIRST_IRAC_HEADING)
    if 0 < idx <= MAX_PREAMBLE_CHARS:
        return output[idx:]
    return output


def split_by_source(records: list[dict], eval_ratio: float, seed: int):
    """Tách train/eval theo Điều nguồn — cùng Điều thì cùng context, để hai phía là rò rỉ."""
    def key(r):
        meta = r.get("metadata") or {}
        return (meta.get("source_metadata") or {}).get("source_doc_id") or meta.get("seed_id")

    groups = sorted({key(r) for r in records})
    random.Random(seed).shuffle(groups)
    n_eval = max(1, int(len(groups) * eval_ratio))
    eval_groups = set(groups[:n_eval])
    train = [r for r in records if key(r) not in eval_groups]
    evals = [r for r in records if key(r) in eval_groups]
    return train, evals


def load_records(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    ap = argparse.ArgumentParser(description="QLoRA fine-tune generator trên dữ liệu Evol-Instruct")
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--max-len", type=int, default=3072)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--eval-ratio", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0, help="Chỉ lấy N record (chạy thử)")
    args = ap.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments,
    )

    if not torch.cuda.is_available():
        sys.exit("❌ Không thấy CUDA — chạy bằng venv fine-tune (torch CUDA), xem docstring.")

    records = load_records(args.data)
    if args.limit:
        records = records[: args.limit]
    train_recs, eval_recs = split_by_source(records, args.eval_ratio, args.seed)
    print(f"Records: {len(records)} → train {len(train_recs)} / eval {len(eval_recs)} (tách theo Điều nguồn)")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token is None:
        # Không dùng eos làm pad, để eos cuối câu trả lời vẫn được tính loss.
        tokenizer.pad_token = "<|finetune_right_pad_id|>"

    def encode(record):
        messages = build_messages(record)
        prompt_ids = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True
        )
        if not isinstance(prompt_ids, list):        # transformers 5: BatchEncoding
            prompt_ids = prompt_ids["input_ids"]
        answer_ids = tokenizer(clean_answer(record["output"]) + "<|eot_id|>",
                               add_special_tokens=False)["input_ids"]
        ids = prompt_ids + answer_ids
        if len(ids) > args.max_len:
            return None                              # cắt cụt câu trả lời IRAC là dạy sai, bỏ hẳn
        labels = [-100] * len(prompt_ids) + answer_ids
        return {"input_ids": ids, "labels": labels}

    def encode_all(recs, name):
        out = [e for e in (encode(r) for r in recs) if e is not None]
        lens = sorted(len(e["input_ids"]) for e in out)
        print(f"  {name}: {len(out)}/{len(recs)} record (bỏ {len(recs) - len(out)} dài > {args.max_len}); "
              f"token median {lens[len(lens) // 2] if lens else 0}, max {lens[-1] if lens else 0}")
        return out

    train_ds = encode_all(train_recs, "train")
    eval_ds = encode_all(eval_recs, "eval")

    def collate(batch):
        width = max(len(b["input_ids"]) for b in batch)
        pad = tokenizer.pad_token_id
        return {
            "input_ids": torch.tensor([b["input_ids"] + [pad] * (width - len(b["input_ids"])) for b in batch]),
            "labels": torch.tensor([b["labels"] + [-100] * (width - len(b["labels"])) for b in batch]),
            "attention_mask": torch.tensor(
                [[1] * len(b["input_ids"]) + [0] * (width - len(b["input_ids"])) for b in batch]
            ),
        }

    # Windows tràn VRAM sang RAM thay vì báo OOM (GPU 0%, máy treo) → chặn trần.
    torch.cuda.set_per_process_memory_fraction(0.92)

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model, dtype=torch.bfloat16, device_map={"": 0},
    )
    # Không dùng prepare_model_for_kbit_training: nó ép embed + lm_head sang fp32
    # và OOM ở max_len 3072 trên card 16 GB; giữ bf16 thì đỉnh ~11 GB.
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    ))
    model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=str(args.out / "checkpoints"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=0.03,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=1,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        bf16=True,
        optim="paged_adamw_8bit",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to=[],
        seed=args.seed,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model, args=training_args,
        train_dataset=train_ds, eval_dataset=eval_ds,
        data_collator=collate, processing_class=tokenizer,
    )
    trainer.train()

    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)

    metrics = trainer.evaluate()
    eval_ids = sorted({r["metadata"]["seed_id"] for r in eval_recs})
    with open(args.out / "train_config.json", "w", encoding="utf-8") as f:
        json.dump({
            "base_model": args.base_model,
            "data": str(args.data.relative_to(BACKEND_DIR)) if args.data.is_relative_to(BACKEND_DIR) else str(args.data),
            "n_train": len(train_ds), "n_eval": len(eval_ds),
            "epochs": args.epochs, "lr": args.lr,
            "lora_r": args.lora_r, "lora_alpha": args.lora_alpha, "max_len": args.max_len,
            "grad_accum": args.grad_accum, "seed": args.seed,
            "eval_loss": metrics.get("eval_loss"),
            "log_history": trainer.state.log_history,
        }, f, ensure_ascii=False, indent=2)
    with open(args.out / "eval_seed_ids.json", "w", encoding="utf-8") as f:
        json.dump(eval_ids, f, ensure_ascii=False)
    print(f"✅ Adapter → {args.out} | eval_loss={metrics.get('eval_loss'):.4f}")


if __name__ == "__main__":
    main()
