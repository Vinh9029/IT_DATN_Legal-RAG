"""
Script 24 — LoRA fine-tune Qwen2.5-3B-Instruct trên config `answers` của dataset QA.

Chưng cất: câu trả lời do Gemma-4-12B (script 23) sinh, student 3B học lại.
Student KHÔNG được biết loại câu hỏi — prompt chỉ có STUDENT_SYSTEM + context +
câu hỏi, nên nó phải tự học đổi kiểu trả lời (ngắn / IRAC / tổng hợp).

Khác script 20: model 3B nên train bf16 thẳng (không lượng tử hoá), token kết
thúc lấy từ chat template của Qwen (`<|im_end|>`), không phải `<|eot_id|>`.

Cần venv có torch CUDA (G:/venv_ft) và `lms unload --all` trước. Chạy từ backend/:

    G:/venv_ft/Scripts/python.exe evol_instruct/scripts/24_finetune_qa_student.py
    G:/venv_ft/Scripts/python.exe evol_instruct/scripts/24_finetune_qa_student.py --limit 40 --epochs 1
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_DIR / "data" / "qa_answers" / "final"
DEFAULT_OUT = BACKEND_DIR / "models" / "qa_student_qwen3b_lora"
BASE_MODEL = "Qwen/Qwen2.5-3B-Instruct"


def build_messages(record: dict) -> list[dict]:
    """Prompt của student — dùng chung cho train và script 25."""
    from config.qa_answer_prompts import STUDENT_SYSTEM, USER_TEMPLATE
    return [
        {"role": "system", "content": STUDENT_SYSTEM},
        {"role": "user", "content": USER_TEMPLATE.format(context=record["context"],
                                                         question=record["question"])},
    ]


def load_split(name: str) -> list[dict]:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="LoRA fine-tune Qwen2.5-3B trên QA answers")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    # p99 = 3.481 token; 3584 chỉ bỏ 29/4.560 mẫu. Đo VRAM: mẫu 3.445 token → 15,0/16,3 GB.
    ap.add_argument("--max-len", type=int, default=3584)
    ap.add_argument("--save-steps", type=int, default=200, help="Lưu checkpoint + eval mỗi N bước")
    ap.add_argument("--resume", action="store_true", help="Chạy tiếp từ checkpoint mới nhất")
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--eval-n", type=int, default=300, help="Số câu val dùng tính eval_loss")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0, help="Chỉ lấy N record train (chạy thử)")
    args = ap.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

    if not torch.cuda.is_available():
        sys.exit("❌ Không thấy CUDA — chạy bằng G:/venv_ft (torch CUDA).")

    train_recs = load_split("train.json")
    eval_recs = load_split("val.json")
    rng = random.Random(args.seed)
    rng.shuffle(train_recs)
    if args.limit:
        train_recs = train_recs[: args.limit]
    eval_recs = sorted(eval_recs, key=lambda r: r["item_id"])
    random.Random(args.seed).shuffle(eval_recs)
    eval_recs = eval_recs[: args.eval_n]
    print(f"Records: train {len(train_recs)} / eval {len(eval_recs)}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    end_tok = "<|im_end|>"
    assert end_tok in tokenizer.get_vocab(), "Base model không dùng chat template ChatML"
    assert tokenizer.pad_token and tokenizer.pad_token != end_tok, "pad trùng token kết thúc"

    def encode(record):
        prompt_ids = tokenizer.apply_chat_template(build_messages(record),
                                                   add_generation_prompt=True, tokenize=True)
        if not isinstance(prompt_ids, list):        # transformers 5: BatchEncoding
            prompt_ids = prompt_ids["input_ids"]
        answer_ids = tokenizer(record["answer"] + end_tok, add_special_tokens=False)["input_ids"]
        ids = prompt_ids + answer_ids
        if len(ids) > args.max_len:
            return None                              # cắt cụt câu trả lời là dạy sai, bỏ hẳn
        return {"input_ids": ids, "labels": [-100] * len(prompt_ids) + answer_ids}

    def encode_all(recs, name):
        out = [e for e in (encode(r) for r in recs) if e is not None]
        lens = sorted(len(e["input_ids"]) for e in out)
        print(f"  {name}: {len(out)}/{len(recs)} (bỏ {len(recs) - len(out)} dài > {args.max_len}); "
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
                [[1] * len(b["input_ids"]) + [0] * (width - len(b["input_ids"])) for b in batch]),
        }

    # Windows tràn VRAM sang RAM thay vì báo OOM (GPU 0%, máy treo) → chặn trần.
    torch.cuda.set_per_process_memory_fraction(0.92)

    model = AutoModelForCausalLM.from_pretrained(args.base_model, dtype=torch.bfloat16,
                                                 device_map={"": 0})
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
        # theo bước, không theo epoch: bị ngắt giữa chừng thì mất tối đa save_steps bước
        eval_strategy="steps",
        save_strategy="steps",
        eval_steps=args.save_steps,
        save_steps=args.save_steps,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        bf16=True,
        optim="adamw_torch_fused",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to=[],
        seed=args.seed,
        remove_unused_columns=False,
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=train_ds,
                      eval_dataset=eval_ds, data_collator=collate, processing_class=tokenizer)
    trainer.train(resume_from_checkpoint=True if args.resume else None)

    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    metrics = trainer.evaluate()
    with open(args.out / "train_config.json", "w", encoding="utf-8") as f:
        json.dump({
            "base_model": args.base_model, "data": "data/qa_answers/final",
            "n_train": len(train_ds), "n_eval": len(eval_ds), "epochs": args.epochs,
            "lr": args.lr, "lora_r": args.lora_r, "lora_alpha": args.lora_alpha,
            "max_len": args.max_len, "grad_accum": args.grad_accum, "seed": args.seed,
            "eval_loss": metrics.get("eval_loss"), "log_history": trainer.state.log_history,
        }, f, ensure_ascii=False, indent=2)
    print(f"✅ Adapter → {args.out} | eval_loss={metrics.get('eval_loss'):.4f}")


if __name__ == "__main__":
    main()
