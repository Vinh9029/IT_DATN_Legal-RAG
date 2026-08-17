"""
Script hỗ trợ xử lý THỦ CÔNG bằng ChatGPT / Gemini (không cần API).

Quy trình:
1. Export seeds thành file TXT dễ copy-paste
2. Hướng dẫn format để paste vào ChatGPT/Gemini
3. Import kết quả từ file TXT/JSON do người dùng paste lại
4. Chạy filters và lưu vào JSONL chuẩn Alpaca

Usage:
    python scripts/05_manual_chatgpt.py export --max-seeds 10
    python scripts/05_manual_chatgpt.py import --input data/manual/batch_01_done.txt
    python scripts/05_manual_chatgpt.py export-all
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import ensure_directories, OUTPUT_DIR, SEEDS_DIR, BASE_DIR
from config.prompts import (
    EVOL_TECHNIQUES,
    SYSTEM_IRAC_RESPONDER,
    FEW_SHOT_IRAC_EXAMPLE,
)
from src.utils import setup_logging, load_jsonl, save_jsonl, generate_item_id
from src.filters import instruction_eliminator

# Thư mục lưu file manual
MANUAL_DIR = BASE_DIR / "data" / "manual"


def export_seeds_for_chatgpt(seeds: list[dict], batch_size: int = 5, batch_num: int = 1):
    """
    Export seeds thành các file TXT, mỗi file = 1 batch để copy-paste vào ChatGPT/Gemini.
    """
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)

    total_batches = (len(seeds) + batch_size - 1) // batch_size

    for i in range(0, len(seeds), batch_size):
        batch = seeds[i : i + batch_size]
        batch_id = batch_num + (i // batch_size)
        filename = f"batch_{batch_id:03d}_seeds.txt"
        filepath = MANUAL_DIR / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write(f"BATCH {batch_id} - EVOL-INSTRUCT THỦ CÔNG\n")
            f.write(f"Ngày tạo: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Số lượng seeds: {len(batch)}\n")
            f.write("=" * 70 + "\n\n")

            # Hướng dẫn sử dụng
            f.write("HƯỚNG DẪN:\n")
            f.write("-" * 40 + "\n")
            f.write("1. Copy TOÀN BỘ phần PROMPT bên dưới.\n")
            f.write("2. Paste vào ChatGPT / Gemini.\n")
            f.write("3. Copy kết quả trả về.\n")
            f.write("4. Paste vào file: batch_{:03d}_done.txt\n".format(batch_id))
            f.write("5. Lưu file vào thư mục: data/manual/\n")
            f.write("6. Chạy: python scripts/05_manual_chatgpt.py import "
                    "--input data/manual/batch_{:03d}_done.txt\n\n".format(batch_id))

            # ── PHẦN 1: PROMPT TIẾN HÓA (Evolution) ──
            f.write("=" * 70 + "\n")
            f.write("BƯỚC 1: TIẾN HÓA CÂU HỎI (Copy phần này vào ChatGPT/Gemini)\n")
            f.write("=" * 70 + "\n\n")

            evol_prompt = _build_evolution_prompt(batch)
            f.write(evol_prompt)

            f.write("\n\n")

            # ── PHẦN 2: PROMPT TRẢ LỜI IRAC ──
            f.write("=" * 70 + "\n")
            f.write("BƯỚC 2: TRẢ LỜI IRAC (Copy phần này vào CUỘC HỘI THOẠI MỚI)\n")
            f.write("=" * 70 + "\n\n")

            irac_prompt = _build_irac_prompt(len(batch))
            f.write(irac_prompt)

        print(f"  ✅ Exported: {filepath}")

    print(f"\n📁 Tổng cộng {total_batches} batch files → {MANUAL_DIR}")
    print(f"📋 Mỗi batch chứa {batch_size} seeds")


def export_all_in_one(seeds: list[dict]):
    """
    Export tất cả seeds thành 1 file prompt duy nhất (cho ít seeds).
    Kết hợp cả Evolution + IRAC trong 1 prompt.
    """
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    filepath = MANUAL_DIR / "all_in_one_prompt.txt"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("EVOL-INSTRUCT - ALL-IN-ONE PROMPT\n")
        f.write(f"Copy toàn bộ nội dung này vào ChatGPT hoặc Gemini\n")
        f.write("=" * 70 + "\n\n")

        f.write("Bạn là chuyên gia pháp luật Việt Nam. Thực hiện 2 bước sau:\n\n")
        f.write("BƯỚC 1: Với mỗi câu hỏi gốc bên dưới, hãy VIẾT LẠI thành câu hỏi "
                "pháp lý phức tạp hơn với tình huống cụ thể tại Việt Nam "
                "(tên người Việt, địa danh Việt, luật Việt Nam).\n\n")
        f.write("BƯỚC 2: Trả lời TỪNG câu hỏi đã viết lại theo cấu trúc IRAC:\n")
        f.write("- **Vấn đề (Issue):** Câu hỏi pháp lý trọng tâm.\n")
        f.write("- **Quy tắc (Rule):** Điều luật áp dụng (KHÔNG dùng tên đương sự).\n")
        f.write("- **Áp dụng (Application):** Đối chiếu tình tiết với luật.\n")
        f.write("- **Kết luận (Conclusion):** Kết quả pháp lý cụ thể.\n\n")

        f.write("FORMAT OUTPUT cho mỗi câu:\n")
        f.write("```\n")
        f.write("### Câu [số thứ tự]\n")
        f.write("**Câu hỏi tiến hóa:** [câu hỏi đã viết lại]\n\n")
        f.write("**Vấn đề (Issue):** ...\n")
        f.write("**Quy tắc (Rule):** ...\n")
        f.write("**Áp dụng (Application):** ...\n")
        f.write("**Kết luận (Conclusion):** ...\n")
        f.write("```\n\n")

        f.write("-" * 50 + "\n")
        f.write("CÁC CÂU HỎI GỐC:\n")
        f.write("-" * 50 + "\n\n")

        for idx, seed in enumerate(seeds, 1):
            f.write(f"{idx}. {seed['instruction']}\n\n")

    print(f"✅ Exported all-in-one prompt → {filepath}")
    print(f"   Chứa {len(seeds)} câu hỏi gốc")


def _build_evolution_prompt(batch: list[dict]) -> str:
    """Xây dựng prompt tiến hóa cho 1 batch."""
    lines = []
    lines.append("Bạn là chuyên gia thiết kế chương trình đào tạo pháp luật Việt Nam.")
    lines.append("")
    lines.append("NHIỆM VỤ: Với mỗi câu hỏi gốc bên dưới, hãy VIẾT LẠI thành câu hỏi "
                 "pháp lý phức tạp hơn theo KỸ THUẬT được chỉ định.")
    lines.append("")
    lines.append("QUY TẮC:")
    lines.append("- Sử dụng tên người Việt (Nguyễn Văn A, Trần Thị B...), "
                 "địa danh Việt, luật Việt Nam.")
    lines.append("- Câu hỏi mới phải yêu cầu trả lời theo IRAC "
                 "(Issue, Rule, Application, Conclusion).")
    lines.append("- CHỈ trả về câu hỏi đã viết lại, đánh số thứ tự tương ứng.")
    lines.append("")
    lines.append("-" * 40)

    import random
    technique_keys = list(EVOL_TECHNIQUES.keys())

    for idx, seed in enumerate(batch, 1):
        tech_key = random.choice(technique_keys)
        tech = EVOL_TECHNIQUES[tech_key]
        lines.append(f"\nCâu {idx} (Kỹ thuật: {tech['name']}):")
        lines.append(f"  Gốc: {seed['instruction']}")

    return "\n".join(lines)


def _build_irac_prompt(num_questions: int) -> str:
    """Xây dựng prompt IRAC response."""
    lines = []
    lines.append("Bạn là Thẩm phán/Chuyên gia Tư vấn Pháp lý cao cấp tại Việt Nam.")
    lines.append("")
    lines.append("NHIỆM VỤ: Với mỗi câu hỏi từ kết quả BƯỚC 1, "
                 "hãy trả lời NGHIÊM NGẶT theo IRAC:")
    lines.append("")
    lines.append("**Vấn đề (Issue):** Xác định vấn đề dưới dạng câu hỏi.")
    lines.append("**Quy tắc (Rule):** Trích dẫn Điều, Khoản cụ thể. "
                 "KHÔNG dùng tên đương sự.")
    lines.append("**Áp dụng (Application):** Đối chiếu tình tiết cụ thể với luật.")
    lines.append("**Kết luận (Conclusion):** Kết luận rõ ràng, nêu hệ quả pháp lý.")
    lines.append("")
    lines.append("LƯU Ý: KHÔNG bịa số hiệu điều luật. Nếu không nhớ chính xác, "
                 "ghi 'theo quy định pháp luật hiện hành'.")
    lines.append("")
    lines.append(f"Hãy trả lời lần lượt {num_questions} câu hỏi từ BƯỚC 1.")
    lines.append("Đánh dấu mỗi câu bằng: ### Câu [số thứ tự]")
    return "\n".join(lines)


def import_manual_results(input_path: str):
    """
    Import kết quả từ file text do người dùng paste từ ChatGPT/Gemini.

    Hỗ trợ 2 format:
    - Format "### Câu X" với **Câu hỏi tiến hóa:** và IRAC sections
    - Format JSON (nếu người dùng format sẵn)
    """
    filepath = Path(input_path)
    if not filepath.exists():
        print(f"❌ File không tồn tại: {filepath}")
        return

    content = filepath.read_text(encoding="utf-8")

    # Thử parse JSON trước
    records = _try_parse_json(content)
    if not records:
        records = _parse_markdown_format(content)

    if not records:
        print("❌ Không parse được kết quả. Kiểm tra format file.")
        print("   Format mong đợi: ### Câu 1 / **Câu hỏi tiến hóa:** ... / IRAC sections")
        return

    # Chạy filters
    accepted = []
    rejected = 0

    for rec in records:
        instruction = rec.get("instruction", "")
        output = rec.get("output", "")

        passed, fails = instruction_eliminator(
            original_prompt=rec.get("seed_instruction", instruction),
            evolved_prompt=instruction,
            response=output,
        )

        if passed:
            alpaca_record = {
                "instruction": instruction,
                "input": "",
                "output": output,
                "metadata": {
                    "technique": "manual_chatgpt",
                    "timestamp": datetime.now().isoformat(),
                    "source_file": filepath.name,
                },
            }
            accepted.append(alpaca_record)
        else:
            rejected += 1
            print(f"  ⚠️ Rejected: {fails} → {instruction[:60]}...")

    # Lưu kết quả
    if accepted:
        output_path = OUTPUT_DIR / "legal_evolved.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_jsonl(accepted, output_path, mode="a")
        print(f"\n✅ Imported: {len(accepted)} accepted, {rejected} rejected")
        print(f"   Saved → {output_path}")
    else:
        print(f"\n❌ Không có record nào pass filters ({rejected} rejected)")


def _try_parse_json(content: str) -> list[dict] | None:
    """Thử parse content dưới dạng JSON array."""
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return None


def _parse_markdown_format(content: str) -> list[dict]:
    """
    Parse format markdown từ ChatGPT/Gemini output.

    Nhận dạng pattern:
    ### Câu 1
    **Câu hỏi tiến hóa:** ...
    **Vấn đề (Issue):** ...
    **Quy tắc (Rule):** ...
    **Áp dụng (Application):** ...
    **Kết luận (Conclusion):** ...
    """
    records = []

    # Split theo ### Câu
    sections = re.split(r"###\s*Câu\s*\d+", content)

    for section in sections[1:]:  # Bỏ phần trước câu đầu tiên
        section = section.strip()
        if not section:
            continue

        record = {"instruction": "", "output": ""}

        # Trích instruction
        inst_match = re.search(
            r"\*\*Câu hỏi tiến hóa:\*\*\s*(.+?)(?=\n\s*\*\*Vấn đề|\n\s*\*\*Issue|\Z)",
            section, re.DOTALL
        )
        if inst_match:
            record["instruction"] = inst_match.group(1).strip()

        # Trích IRAC output
        irac_parts = []
        for label in [
            r"Vấn đề \(Issue\)",
            r"Quy tắc \(Rule\)",
            r"Áp dụng \(Application\)",
            r"Kết luận \(Conclusion\)",
        ]:
            match = re.search(
                rf"\*\*{label}:\*\*\s*(.+?)(?=\n\s*\*\*|\Z)",
                section, re.DOTALL
            )
            if match:
                irac_parts.append(match.group(0).strip())

        if irac_parts:
            record["output"] = "\n\n".join(irac_parts)

        if record["instruction"] or record["output"]:
            records.append(record)

    return records


def main():
    parser = argparse.ArgumentParser(
        description="Xử lý Evol-Instruct thủ công bằng ChatGPT/Gemini"
    )
    subparsers = parser.add_subparsers(dest="command", help="Lệnh")

    # Export
    export_parser = subparsers.add_parser("export", help="Export seeds thành TXT")
    export_parser.add_argument("--max-seeds", type=int, default=10)
    export_parser.add_argument("--batch-size", type=int, default=5)
    export_parser.add_argument("--seeds-file", default="seeds.jsonl")

    # Export all-in-one
    aio_parser = subparsers.add_parser("export-all", help="Export all-in-one prompt")
    aio_parser.add_argument("--max-seeds", type=int, default=10)
    aio_parser.add_argument("--seeds-file", default="seeds.jsonl")

    # Import
    import_parser = subparsers.add_parser("import", help="Import kết quả từ TXT")
    import_parser.add_argument("--input", required=True, help="File TXT đầu vào")

    args = parser.parse_args()

    logger = setup_logging("05_manual.log")
    ensure_directories()

    if args.command == "export":
        seeds = load_jsonl(SEEDS_DIR / args.seeds_file)
        if not seeds:
            print(f"❌ Không tìm thấy seeds. Chạy scripts/02_generate_seeds.py trước.")
            sys.exit(1)
        seeds = seeds[: args.max_seeds]
        export_seeds_for_chatgpt(seeds, args.batch_size)

    elif args.command == "export-all":
        seeds = load_jsonl(SEEDS_DIR / args.seeds_file)
        if not seeds:
            print(f"❌ Không tìm thấy seeds.")
            sys.exit(1)
        seeds = seeds[: args.max_seeds]
        export_all_in_one(seeds)

    elif args.command == "import":
        import_manual_results(args.input)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
