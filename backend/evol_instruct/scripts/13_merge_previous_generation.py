"""
Gộp một ĐỢT SINH TRƯỚC vào dataset hiện tại — chỉ phần còn hợp lệ.

─── Vì sao không nối thẳng hai file pairs.jsonl ───

Đợt sinh cũ được tạo trên một corpus khác và gán nhãn bằng một bộ tiêu chí
khác. Nối thẳng sẽ kéo ngược vào dataset đúng ba thứ vừa sửa:

  - câu sinh từ văn bản đã HẾT HIỆU LỰC (đo 2026-09-14: 1.374/5.560 câu);
  - câu sinh từ bản BLDS/BLTTDS TRÙNG trên HuggingFace (560 câu) — chính là
    nguồn của vụ 124 Điều trùng / 54 rơi khác split;
  - nhãn chấm bằng guideline đời trước, trộn hai định nghĩa vào một dataset mà
    về sau không tách ra được (đây là thứ `JUDGE_PROMPT_VERSION` sinh ra để
    chặn).

Script này giữ lại đúng phần câu cũ mà nguồn của nó VẪN nằm trong corpus hiện
hành, rồi để `11_verify_labels.py` chấm lại toàn bộ bằng prompt hiện tại. Sau
bước đó, mọi câu trong dataset — cũ lẫn mới — đều đứng trên cùng một bộ tiêu
chí, và `gen_version` vẫn cho biết câu nào sinh ở đợt nào.

─── Cách dùng ───

    cd backend/
    python evol_instruct/scripts/13_merge_previous_generation.py \\
        --previous data/qa_pairs/_archive_v2/raw/pairs.jsonl
    python evol_instruct/scripts/11_verify_labels.py \\
        --input data/qa_pairs/raw/pairs_merged.jsonl
    python evol_instruct/scripts/12_export_dataset.py

Cache judge khoá theo `item_id` + `prompt_version`, nên bước 11 chỉ gọi LLM cho
phần câu cũ; phần mới đã chấm rồi thì lấy lại từ cache, không tốn lượt nào.
"""

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from config.qa_settings import GEN_VERSION, PAIRS_FILE, QA_RAW_DIR
from evol_instruct.src.qa_specificity.corpus_filter import load_scoped_corpus
from evol_instruct.src.utils import load_jsonl


def doc_ids_hien_hanh() -> set[str]:
    """`source_doc_id` của corpus hiện hành — thước đo 'còn hợp lệ'."""
    return {d.get("source_doc_id") for d in load_scoped_corpus()}


def loc_cap_con_nguyen(items: list[dict], hop_le: set[str]) -> list[dict]:
    """
    Giữ câu có nguồn còn trong corpus, và CHỈ giữ cặp còn đủ hai vế.

    Bỏ cặp khuyết vế ngay ở đây thay vì để bước 11 loại: cặp khuyết vế đi tiếp
    thì vẫn tốn một lượt gọi judge rồi mới bị vứt.
    """
    con = [i for i in items if i.get("source_doc_id") in hop_le]
    dem = collections.Counter(i["pair_id"] for i in con)
    return [i for i in con if dem[i["pair_id"]] == 2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Gộp đợt sinh trước vào dataset hiện tại")
    parser.add_argument("--previous", required=True,
                        help="pairs.jsonl của đợt sinh trước")
    parser.add_argument("--current", default=str(PAIRS_FILE),
                        help="pairs.jsonl của đợt hiện tại")
    parser.add_argument("--output", default=str(QA_RAW_DIR / "pairs_merged.jsonl"))
    parser.add_argument("--retag-current", default=GEN_VERSION,
                        help="Ghi đè `gen_version` cho phần hiện tại. Cần khi đợt "
                             "này đã sinh xong TRƯỚC lúc bump GEN_VERSION, nếu "
                             "không hai đợt mang cùng nhãn và không tách được nữa.")
    args = parser.parse_args()

    cu = load_jsonl(Path(args.previous))
    moi = load_jsonl(Path(args.current))
    logger.info(f"Đợt trước: {len(cu)} câu | Đợt này: {len(moi)} câu")

    # ── Gắn lại nhãn phiên bản cho đợt hiện tại ────────────────────
    if args.retag_current:
        for item in moi:
            item.setdefault("metadata", {})["gen_version"] = args.retag_current
        logger.info(f"Đã gắn `gen_version={args.retag_current}` cho {len(moi)} câu đợt này")

    # ── Lọc đợt cũ theo corpus hiện hành ──────────────────────────
    hop_le = doc_ids_hien_hanh()
    giu = loc_cap_con_nguyen(cu, hop_le)
    logger.info(
        f"Đợt trước: giữ {len(giu)}/{len(cu)} câu "
        f"({len(cu) - len(giu)} bị loại vì nguồn không còn trong corpus)"
    )

    # ── Va chạm định danh ─────────────────────────────────────────
    # Trùng `item_id` nghĩa là hai câu hỏi y hệt nhau ở hai đợt. Giữ bản ĐỢT
    # NÀY và bỏ bản cũ: nhãn cache khoá theo item_id nên giữ cả hai thì bản sau
    # ghi đè bản trước một cách âm thầm.
    id_moi = {i["item_id"] for i in moi}
    trung = [i for i in giu if i["item_id"] in id_moi]
    if trung:
        logger.warning(
            f"{len(trung)} câu đợt trước trùng `item_id` với đợt này (câu hỏi y hệt) "
            f"→ bỏ bản cũ, giữ bản đợt này"
        )
        pair_bo = {i["pair_id"] for i in trung}
        giu = [i for i in giu if i["pair_id"] not in pair_bo]

    gop = moi + giu
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in gop:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    theo_ver = collections.Counter(i["metadata"].get("gen_version") for i in gop)
    theo_mode = collections.Counter(i["metadata"].get("narrow_mode") for i in gop)
    logger.info(f"→ {args.output}")
    logger.info(f"   {len(gop)} câu = {len(gop) // 2} cặp")
    logger.info(f"   theo gen_version: {dict(theo_ver)}")
    logger.info(f"   theo narrow_mode: {dict(theo_mode)}")
    logger.info(f"   Điều nguồn: {len({i['source_doc_id'] for i in gop})}")
    logger.info("Bước tiếp: 11_verify_labels.py --input " + args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
