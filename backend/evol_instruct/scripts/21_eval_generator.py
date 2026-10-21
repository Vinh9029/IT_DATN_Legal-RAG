"""
Script 21 — So sánh base / base+fewshot / finetuned trên tập eval của script 20,
chấm bằng chính các bộ lọc của pipeline Evol-Instruct (filters.py).

Chạy ở venv fine-tune, từ backend/, sau khi `lms unload --all`:
    python evol_instruct/scripts/21_eval_generator.py --n 40
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ADAPTER = BACKEND_DIR / "models" / "legal_generator_lora"


def score(response: str, context: str) -> dict:
    from evol_instruct.src.filters import (
        filter_context_citations, filter_irac_structure, filter_min_length, filter_refusal,
    )
    checks = {
        "irac_structure": filter_irac_structure(response),
        "context_citation": filter_context_citations(response, context),
        "refusal_free": filter_refusal(response),
        "min_length": filter_min_length(response),
    }
    checks["all_pass"] = all(checks.values())
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER)
    ap.add_argument("--data", type=Path, default=None, help="Mặc định lấy từ train_config.json")
    ap.add_argument("--n", type=int, default=40, help="Số record hold-out đem chấm")
    ap.add_argument("--max-new-tokens", type=int, default=1536)
    args = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from loguru import logger
    logger.remove()  # filters.py log debug từng câu — không cần ở đây

    from config.prompts import FEW_SHOT_IRAC_EXAMPLE
    # Tên file bắt đầu bằng số nên không `import` thẳng được.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ft20", Path(__file__).resolve().parent / "20_finetune_generator.py")
    ft20 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ft20)

    cfg = json.loads((args.adapter / "train_config.json").read_text(encoding="utf-8"))
    data_path = args.data or (BACKEND_DIR / cfg["data"])
    eval_ids = set(json.loads((args.adapter / "eval_seed_ids.json").read_text(encoding="utf-8")))
    records = [r for r in ft20.load_records(data_path) if r["metadata"]["seed_id"] in eval_ids]
    records = records[: args.n]
    print(f"Hold-out: {len(records)} record")

    tokenizer = AutoTokenizer.from_pretrained(args.adapter)
    base = AutoModelForCausalLM.from_pretrained(cfg["base_model"], dtype=torch.bfloat16, device_map={"": 0})
    model = PeftModel.from_pretrained(base, args.adapter)
    model.eval()

    def generate(messages):
        ids = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
        if not torch.is_tensor(ids):
            ids = ids["input_ids"]
        ids = ids.to(model.device)
        with torch.no_grad():
            out = model.generate(
                ids, max_new_tokens=args.max_new_tokens, do_sample=False,
                pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.convert_tokens_to_ids("<|eot_id|>"),
            )
        new = out[0, ids.shape[1]:]
        truncated = len(new) >= args.max_new_tokens
        return tokenizer.decode(new, skip_special_tokens=True).strip(), len(new), truncated

    def fewshot(messages):
        return [{"role": "system", "content": messages[0]["content"] + "\n\n" + FEW_SHOT_IRAC_EXAMPLE},
                messages[1]]

    configs = {
        "base": (False, lambda m: m),
        "base+fewshot": (False, fewshot),
        "finetuned": (True, lambda m: m),
    }
    results = {name: [] for name in configs}
    samples = []
    for i, rec in enumerate(records):
        messages = ft20.build_messages(rec)
        row = {"seed_id": rec["metadata"]["seed_id"], "instruction": rec["instruction"][:300]}
        for name, (use_adapter, wrap) in configs.items():
            t0 = time.time()
            if use_adapter:
                text, n_tok, trunc = generate(wrap(messages))
            else:
                with model.disable_adapter():
                    text, n_tok, trunc = generate(wrap(messages))
            s = score(text, rec.get("input") or "")
            s.update({"tokens": n_tok, "truncated": trunc, "seconds": round(time.time() - t0, 1)})
            results[name].append(s)
            row[name] = text
        samples.append(row)
        print(f"[{i + 1}/{len(records)}] " + " | ".join(
            f"{n}: {'✓' if results[n][-1]['all_pass'] else '✗'}" for n in configs))

    summary = {}
    for name, rows in results.items():
        n = max(len(rows), 1)
        summary[name] = {k: round(sum(r[k] for r in rows) / n, 4)
                         for k in ("irac_structure", "context_citation", "refusal_free",
                                   "min_length", "all_pass", "truncated")}
        summary[name]["avg_tokens"] = round(sum(r["tokens"] for r in rows) / n, 1)
        summary[name]["avg_seconds"] = round(sum(r["seconds"] for r in rows) / n, 1)

    report = {"n": len(records), "adapter": args.adapter.name, "summary": summary}
    (args.adapter / "eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.adapter / "eval_samples.jsonl").write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in samples), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
