"""
Script 25 — So sánh student Qwen2.5-3B (fine-tune) với các mốc khác trên tập test QA.

Hệ thống so sánh (cùng prompt student, cùng context):
    qwen3b_base   Qwen2.5-3B-Instruct gốc (chỉ có STUDENT_SYSTEM)
    qwen3b_ft     Qwen2.5-3B + LoRA của script 24
    llama8b       Llama-3.1-8B qua LM Studio (generator production hiện tại)
    teacher       câu trả lời Gemma-4-12B trong config `answers` (mức trần)

Lệnh (chạy từ backend/):
    python  evol_instruct/scripts/25_eval_qa_student.py sample --n 200
    G:/venv_ft/Scripts/python evol_instruct/scripts/25_eval_qa_student.py gen-hf --name qwen3b_base
    G:/venv_ft/Scripts/python evol_instruct/scripts/25_eval_qa_student.py gen-hf --name qwen3b_ft --adapter models/qa_student_qwen3b_lora
    python  evol_instruct/scripts/25_eval_qa_student.py gen-lms --name llama8b --model meta-llama-3.1-8b-instruct
    python  evol_instruct/scripts/25_eval_qa_student.py metrics
    python  evol_instruct/scripts/25_eval_qa_student.py judge --a qwen3b_ft --b qwen3b_base --judge google/gemma-4-12b-qat

Mọi output ghi append theo item_id → chạy lại là tiếp tục.

Judge: student là Qwen, teacher là Gemma → judge nào trong hai họ cũng có thể
thiên vị. Chấm mỗi cặp HAI thứ tự, báo kết quả riêng từng judge, và dựa chủ yếu
vào thước đo khách quan trong `metrics` (trích Điều ngoài context, đúng kiểu,
lặp, độ dài).
"""

import argparse
import collections
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from config.qa_answer_prompts import style_key

DATA_DIR = ROOT / "data" / "qa_answers" / "final"
EVAL_DIR = ROOT / "data" / "qa_answers" / "eval"
IDS_PATH = EVAL_DIR / "eval_ids.json"
LMS_URL = "http://localhost:1234/v1"


def load_test() -> dict:
    with open(DATA_DIR / "test.json", encoding="utf-8") as f:
        return {r["item_id"]: r for r in json.load(f)}


def eval_items() -> list[dict]:
    test = load_test()
    return [test[i] for i in json.loads(IDS_PATH.read_text(encoding="utf-8")) if i in test]


def out_path(name: str) -> Path:
    return EVAL_DIR / f"outputs_{name}.jsonl"


def read_outputs(name: str) -> dict:
    if name == "teacher":
        return {r["item_id"]: r["answer"] for r in eval_items()}
    p = out_path(name)
    if not p.exists():
        return {}
    out = {}
    for line in open(p, encoding="utf-8"):
        try:
            r = json.loads(line)
            out[r["item_id"]] = r["answer"]
        except (json.JSONDecodeError, KeyError):
            pass
    return out


def append(name: str, rec: dict):
    with open(out_path(name), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cmd_sample(args):
    test = list(load_test().values())
    groups = collections.defaultdict(list)
    for r in test:
        groups[style_key(r["final_label"], r["narrow_mode"])].append(r["item_id"])
    rng = random.Random(args.seed)
    # broad gồm 2 nửa (cặp citation/situation) → lấy cân 3 kiểu trả lời
    per = args.n // len(groups)
    ids = []
    for k in sorted(groups):
        ids += rng.sample(sorted(groups[k]), min(per, len(groups[k])))
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    IDS_PATH.write_text(json.dumps(ids, indent=1), encoding="utf-8")
    print(f"{len(ids)} câu eval → {IDS_PATH} ({ {k: min(per, len(v)) for k, v in groups.items()} })")


def cmd_gen_hf(args):
    import importlib.util
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    spec = importlib.util.spec_from_file_location("ft", ROOT / "evol_instruct/scripts/24_finetune_qa_student.py")
    ft = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ft)

    done = read_outputs(args.name)
    todo = [r for r in eval_items() if r["item_id"] not in done]
    print(f"{args.name}: còn {len(todo)} câu")
    if not todo:
        return
    torch.cuda.set_per_process_memory_fraction(0.92)
    tok = AutoTokenizer.from_pretrained(args.base_model, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(args.base_model, dtype=torch.bfloat16, device_map={"": 0})
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(ROOT / args.adapter))
    model.eval()
    end_id = tok.convert_tokens_to_ids("<|im_end|>")
    t0 = time.time()
    for b in range(0, len(todo), args.batch):
        batch = todo[b:b + args.batch]
        prompts = [tok.apply_chat_template(ft.build_messages(r), add_generation_prompt=True, tokenize=False)
                   for r in batch]
        enc = tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(0)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=args.max_new_tokens, do_sample=False,
                                 repetition_penalty=1.05, eos_token_id=[end_id, tok.eos_token_id],
                                 pad_token_id=tok.pad_token_id)
        for r, g in zip(batch, gen[:, enc["input_ids"].shape[1]:]):
            text = tok.decode(g, skip_special_tokens=True).strip()
            append(args.name, {"item_id": r["item_id"], "answer": text,
                               "truncated": bool(end_id not in g.tolist())})
        n = b + len(batch)
        print(f"  {n}/{len(todo)} — {(time.time() - t0) / n:.1f}s/câu", flush=True)


def cmd_gen_lms(args):
    import importlib.util
    import openai
    spec = importlib.util.spec_from_file_location("ft", ROOT / "evol_instruct/scripts/24_finetune_qa_student.py")
    ft = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ft)

    done = read_outputs(args.name)
    todo = [r for r in eval_items() if r["item_id"] not in done]
    print(f"{args.name}: còn {len(todo)} câu")
    client = openai.OpenAI(base_url=LMS_URL, api_key="lm-studio", timeout=300, max_retries=1)
    for n, r in enumerate(todo, 1):
        resp = client.chat.completions.create(model=args.model, messages=ft.build_messages(r),
                                              temperature=0.0, max_tokens=args.max_new_tokens)
        ch = resp.choices[0]
        append(args.name, {"item_id": r["item_id"], "answer": (ch.message.content or "").strip(),
                           "truncated": ch.finish_reason == "length"})
        if n % 10 == 0:
            print(f"  {n}/{len(todo)}", flush=True)


# ── Thước đo khách quan ──────────────────────────────────────────────────────

RE_DIEU = re.compile(r"Điều\s+(\d+[a-zđ]?)", re.IGNORECASE)
IRAC_HEADS = ("**Vấn đề", "**Quy tắc", "**Áp dụng", "**Kết luận")


def objective(answer: str, item: dict) -> dict:
    cited = set(RE_DIEU.findall(answer))
    outside = cited - set(RE_DIEU.findall(item["context"]))
    n_heads = sum(h in answer for h in IRAC_HEADS)
    key = style_key(item["final_label"], item["narrow_mode"])
    style_ok = (n_heads >= 3) if key == "narrow/situation" else (n_heads <= 1)
    paras = [p.strip() for p in re.split(r"\n\s*\n", answer) if len(p.strip()) >= 80]
    loop = any(c >= 3 for c in collections.Counter(paras).values())
    return {"words": len(answer.split()), "cites": len(cited), "outside": bool(outside),
            "style_ok": style_ok, "loop": loop, "group": key}


def cmd_metrics(args):
    items = {r["item_id"]: r for r in eval_items()}
    rows = []
    for name in args.systems:
        outs = read_outputs(name)
        agg = collections.defaultdict(list)
        for iid, ans in outs.items():
            if iid not in items:
                continue
            o = objective(ans, items[iid])
            for g in ("all", o["group"]):
                agg[g].append(o)
        for g in sorted(agg):
            L = agg[g]
            rows.append({
                "system": name, "group": g, "n": len(L),
                "citation_outside_context_%": round(100 * sum(o["outside"] for o in L) / len(L), 1),
                "style_ok_%": round(100 * sum(o["style_ok"] for o in L) / len(L), 1),
                "loop_%": round(100 * sum(o["loop"] for o in L) / len(L), 1),
                "no_citation_%": round(100 * sum(o["cites"] == 0 for o in L) / len(L), 1),
                "words_mean": round(sum(o["words"] for o in L) / len(L)),
            })
    for r in rows:
        print(r)
    (EVAL_DIR / "metrics.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


# ── Judge so cặp ─────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """Bạn là luật sư thẩm định chất lượng câu trả lời pháp lý. Cho một câu hỏi, các điều luật làm căn cứ ([CONTEXT]) và hai câu trả lời A, B.
Tiêu chí theo thứ tự quan trọng:
1. Đúng pháp luật so với [CONTEXT]; không bịa số Điều, mức tiền, thời hạn.
2. Trả lời đúng trọng tâm câu hỏi; tình tiết thiếu thì chia trường hợp thay vì tự giả định.
3. Lập luận rõ ràng, đủ ý, không lan man, không lặp.
Không ưu tiên câu dài hơn chỉ vì dài. Trả lời đúng MỘT dòng JSON: {"winner": "A" | "B" | "tie", "reason": "<1 câu>"}"""

JUDGE_USER = """[CONTEXT]
{context}

[CÂU HỎI]
{question}

[CÂU TRẢ LỜI A]
{a}

[CÂU TRẢ LỜI B]
{b}"""


def cmd_judge(args):
    import openai
    items = {r["item_id"]: r for r in eval_items()}
    A, B = read_outputs(args.a), read_outputs(args.b)
    tag = f"{args.a}__vs__{args.b}__{args.judge.replace('/', '_')}"
    path = EVAL_DIR / f"judge_{tag}.jsonl"
    done = set()
    if path.exists():
        done = {(json.loads(l)["item_id"], json.loads(l)["order"]) for l in open(path, encoding="utf-8")}
    client = openai.OpenAI(base_url=LMS_URL, api_key="lm-studio", timeout=600, max_retries=1)
    ids = [i for i in items if i in A and i in B]
    for n, iid in enumerate(ids, 1):
        it = items[iid]
        for order in ("ab", "ba"):
            if (iid, order) in done:
                continue
            first, second = (A[iid], B[iid]) if order == "ab" else (B[iid], A[iid])
            msgs = [{"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": JUDGE_USER.format(context=it["context"], question=it["question"],
                                                                  a=first, b=second)}]
            try:
                resp = client.chat.completions.create(model=args.judge, messages=msgs, temperature=0.0,
                                                      max_tokens=300, extra_body={"reasoning_effort": "none"})
                txt = resp.choices[0].message.content or ""
                m = re.search(r'"winner"\s*:\s*"(A|B|tie)"', txt)
                w = m.group(1) if m else None
            except Exception as e:                      # noqa: BLE001
                txt, w = f"{type(e).__name__}: {e}", None
            # quy về góc nhìn của --a
            win = None if w is None else ("tie" if w == "tie" else
                                          ("a" if (w == "A") == (order == "ab") else "b"))
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"item_id": iid, "order": order, "raw": txt[:400], "win": win},
                                   ensure_ascii=False) + "\n")
        if n % 10 == 0:
            print(f"  {n}/{len(ids)}", flush=True)
    summarize_judge(path, args.a, args.b, items)


def summarize_judge(path: Path, a: str, b: str, items: dict):
    per = collections.defaultdict(dict)
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        per[r["item_id"]][r["order"]] = r["win"]
    score = {}
    for iid, d in per.items():
        if None in d.values() or len(d) < 2:
            continue
        # mỗi câu: thắng cả hai thứ tự = 1, thua cả hai = 0, còn lại = 0,5 (hoà/không nhất quán)
        v = [1.0 if x == "a" else 0.0 if x == "b" else 0.5 for x in d.values()]
        score[iid] = sum(v) / 2
    vals = list(score.values())
    if not vals:
        print("Chưa có câu nào chấm đủ hai thứ tự")
        return
    rng = random.Random(0)
    boots = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(2000))
    wins = sum(v == 1 for v in vals); losses = sum(v == 0 for v in vals)
    print(f"\n{a} vs {b} (judge {path.stem.split('__')[-1]}): n={len(vals)}  thắng {wins} / hoà-lệch {len(vals) - wins - losses} / thua {losses}")
    print(f"  điểm {sum(vals) / len(vals):.3f}  CI95 [{boots[50]:.3f}, {boots[1949]:.3f}]  (0,5 = ngang nhau)")
    by = collections.defaultdict(list)
    for iid, v in score.items():
        it = items[iid]
        by[style_key(it["final_label"], it["narrow_mode"])].append(v)
    for g, L in sorted(by.items()):
        print(f"  {g:18s} n={len(L)} điểm {sum(L) / len(L):.3f}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sample"); p.add_argument("--n", type=int, default=210); p.add_argument("--seed", type=int, default=42)
    p = sub.add_parser("gen-hf")
    p.add_argument("--name", required=True); p.add_argument("--adapter", default="")
    p.add_argument("--base-model", default="Qwen/Qwen2.5-3B-Instruct")
    p.add_argument("--batch", type=int, default=8); p.add_argument("--max-new-tokens", type=int, default=1200)
    p = sub.add_parser("gen-lms")
    p.add_argument("--name", required=True); p.add_argument("--model", required=True)
    p.add_argument("--max-new-tokens", type=int, default=1200)
    p = sub.add_parser("metrics")
    p.add_argument("--systems", nargs="+", default=["teacher", "qwen3b_base", "qwen3b_ft", "llama8b"])
    p = sub.add_parser("judge")
    p.add_argument("--a", required=True); p.add_argument("--b", required=True); p.add_argument("--judge", required=True)
    args = ap.parse_args()
    {"sample": cmd_sample, "gen-hf": cmd_gen_hf, "gen-lms": cmd_gen_lms,
     "metrics": cmd_metrics, "judge": cmd_judge}[args.cmd](args)


if __name__ == "__main__":
    main()
