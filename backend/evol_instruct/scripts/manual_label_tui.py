"""
Công cụ gán nhãn tay cho Bước 3 (tính Cohen's kappa).

KHÔNG phải một bước của pipeline — chỉ là cái bàn phím cho việc tay mà
`11_verify_labels.py --export-manual-sample` đã dọn sẵn chỗ. Vì thế không đánh
số thứ tự như 10/11/12.

Vì sao cần: điền `manual_label` thẳng vào JSONL bằng tay thì vừa chậm vừa dễ
sai cú pháp, và — nguy hiểm hơn — người gán phải tự tổng hợp 3 trục + 2 ngoại
lệ phủ quyết trong đầu cho 100 câu liên tiếp. Đó đúng là chỗ con người trượt.
Script này hỏi TỪNG TRỤC rồi tự áp quy tắc §4, nên sai sót còn lại chỉ là sai
ở khâu đọc hiểu câu hỏi — thứ duy nhất thực sự cần người.

KHÔNG hiển thị bất kỳ nhãn máy nào (provenance / heuristic / judge). Tính mù là
điều kiện để κ có giá trị — xem docs/specificity-guideline.md §7 bước 2.

Usage:
    python evol_instruct/scripts/manual_label_tui.py
    python evol_instruct/scripts/manual_label_tui.py --quick    # 1 phím/câu
    python evol_instruct/scripts/manual_label_tui.py --review   # xem lại câu đã gán
"""

import argparse
import json
import os
import re
import shutil
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config.qa_settings import MANUAL_SAMPLE_FILE

# Console Windows mặc định cp1252 → mọi ký tự tiếng Việt nổ UnicodeEncodeError.
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


# ── Đọc phím đơn ──────────────────────────────────────────────────
if sys.platform == "win32":
    import msvcrt

    def get_key() -> str:
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):      # phím mũi tên/chức năng: nuốt byte thứ hai
            msvcrt.getch()
            return ""
        if ch == b"\x03":                 # Ctrl+C không tự raise khi đọc kiểu này
            raise KeyboardInterrupt
        if ch in (b"\r", b"\n"):
            return "\n"
        return ch.decode("utf-8", errors="ignore").lower()
else:
    import termios
    import tty

    def get_key() -> str:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        if ch == "\x03":
            raise KeyboardInterrupt
        return "\n" if ch in ("\r", "\n") else ch.lower()


# ── Màu (tắt bằng NO_COLOR) ───────────────────────────────────────
_NC = os.getenv("NO_COLOR") is not None


def _c(text: str, code: str) -> str:
    return text if _NC else f"\x1b[{code}m{text}\x1b[0m"


def BOLD(s):   return _c(s, "1")
def DIM(s):    return _c(s, "2")
def CYAN(s):   return _c(s, "36")
def GREEN(s):  return _c(s, "32")
def YELLOW(s): return _c(s, "33")
def RED(s):    return _c(s, "31")


def clear():
    print("\x1b[2J\x1b[H", end="")


def width() -> int:
    return min(shutil.get_terminal_size((100, 30)).columns, 100)


# ── Quy tắc tổng hợp — bám sát guideline §4 ───────────────────────
# axis1: both=nêu cả điều VÀ khoản | partial=có nêu điều/văn bản | none=không nêu
# axis2: few=1-2 điều | many=>=3 điều hoặc phải liệt kê | multi=>=2 vấn đề độc lập | unknown
# axis3: situation=đủ dữ kiện | general=khái niệm/chung chung
AXIS_NARROW = {"axis1": {"both", "partial"}, "axis2": {"few"}, "axis3": {"situation"}}


def resolve(axes: dict) -> tuple[str, str]:
    """Trả về (nhãn, lý do). Hai ngoại lệ phủ quyết xét TRƯỚC quy tắc đếm."""
    if axes["axis1"] == "both":
        return "narrow", "phủ quyết #1: nêu đích danh cả điều VÀ khoản"
    if axes["axis2"] == "multi":
        return "broad", "phủ quyết #2: câu gộp >= 2 vấn đề pháp lý độc lập"
    if axes["axis2"] == "unknown":
        return "ambiguous", "Trục 2 không chấm được → vùng xám, loại khỏi κ"
    n = sum(1 for k, allowed in AXIS_NARROW.items() if axes[k] in allowed)
    return ("narrow" if n >= 2 else "broad"), f"{n}/3 trục nghiêng narrow"


# Phủ quyết #1 đòi CẢ "khoản N" VÀ "Điều N" (guideline §4). Đây là điều kiện
# QUAN SÁT ĐƯỢC TRÊN MẶT CHỮ, nên máy kiểm hộ được mà không hề gán nhãn thay —
# nó chỉ hỏi lại "câu này không có chữ khoản, chắc chưa?". Đo trên vòng gán đầu
# tiên: 29/36 lần dùng phủ quyết #1 là áp cho câu chỉ có "Điều N" hoặc số hiệu
# văn bản, tức nhầm sang mức [2]. Không chặn thì lỗi này lặp lại y hệt.
_RE_KHOAN = re.compile(r"kho[aả]n\s*\d+", re.IGNORECASE)
_RE_DIEU = re.compile(r"[Đđ]i[eề]u\s*\d+")


def has_dieu_and_khoan(question: str) -> bool:
    return bool(_RE_KHOAN.search(question) and _RE_DIEU.search(question))


# ── Câu hỏi theo từng trục ────────────────────────────────────────
QUESTIONS = [
    ("axis1", "TRỤC 1 — Câu hỏi có nêu đích danh điều luật / văn bản không?", [
        ("1", "both", 'Nêu CẢ điều VÀ khoản   (vd: "khoản 1 Điều 35")', "→ narrow, PHỦ QUYẾT"),
        ("2", "partial", 'Có nêu điều HOẶC tên/số hiệu văn bản   ("Điều 623", "BLDS 2015")', "→ narrow"),
        ("3", "none", 'Không nêu gì, hoặc chỉ nói chung "theo pháp luật dân sự"', "→ broad"),
    ]),
    ("axis2", "TRỤC 2 — Trả lời ĐẦY ĐỦ cần bao nhiêu điều luật?", [
        ("1", "few", '1–2 điều là đủ; trả lời có dạng "theo Điều X thì…"', "→ narrow"),
        ("2", "many", 'MỘT vấn đề nhưng trả lời phải LIỆT KÊ nhiều mục\n'
                      '         ("có những … nào", "quyền và nghĩa vụ gì", "hậu quả pháp lý nào")',
         "→ broad   ← chọn cái này khi phân vân với [3]"),
        ("3", "multi", 'HAI vấn đề pháp lý TÁCH RỜI nhau, mỗi cái trả lời được độc lập\n'
                       '         ("…lãi suất bao nhiêu, VÀ thủ tục khởi kiện thế nào?")',
         "→ broad, PHỦ QUYẾT"),
        ("4", "unknown", "Không chấm được — câu hỏi không đủ thông tin để quyết", "→ ambiguous"),
    ]),
    ("axis3", "TRỤC 3 — Có tình huống cụ thể đủ dữ kiện không?", [
        ("1", "situation", "Có chủ thể + mốc thời gian / con số cụ thể", "→ narrow"),
        ("2", "general", "Khái niệm, định nghĩa, tổng quan, hoặc tình huống chung chung", "→ broad"),
    ]),
]

HINTS = {
    "axis1": "Thuần quan sát mặt chữ — không cần biết luật. [1] CHỈ khi thấy chữ\n"
             '      "khoản" kèm số; chỉ có "Điều 96" hay số hiệu văn bản thì là [2].',
    "axis2": 'KHÔNG RÀNH LUẬT? Dùng phép thử: "câu trả lời đúng có phải MỘT DANH\n'
             '      SÁCH nhiều mục không?" → có thì chọn [2].  Hỏi MỘT con số / MỘT mốc\n'
             "      thời hiệu / MỘT điều kiện → chọn [1].",
    "axis3": 'Đây là "có dữ kiện để áp luật vào ngay không", không phải "dài hay ngắn".',
}

RUBRIC = """
  ┌─ TIÊU CHÍ (docs/specificity-guideline.md §2–§4) ────────────────────────┐

    Nhãn KHÔNG đo khó/dễ, KHÔNG đo dài/ngắn. Nó đo HÌNH DẠNG TẬP TÀI LIỆU
    cần để trả lời:
        narrow = khoá chặt vào 1–2 quy định; lấy thêm văn bản chỉ tổ nhiễu
        broad  = phải nhìn bao quát; lấy một điều luật là trả lời thiếu

    TỔNG HỢP:  >= 2/3 trục nghiêng narrow  ->  narrow.   Còn lại -> broad.
    Nhưng xét TRƯỚC hai phủ quyết:
        #1  nêu cả điều VÀ khoản      ->  luôn narrow
        #2  gộp >= 2 vấn đề độc lập   ->  luôn broad
        (cả hai cùng đúng  =>  #1 thắng)

    ambiguous CHỈ dùng khi thật sự có trục không chấm được. Ví dụ
    "Giao dịch dân sự vô hiệu thì xử lý thế nào?" — tuỳ vô hiệu toàn bộ hay
    từng phần mà số điều cần dẫn khác hẳn, nên Trục 2 bó tay.
        Không chắc vì KHÔNG RÀNH LUẬT   -> vẫn chấm, dùng phép thử danh sách
        Không chắc vì CÂU HỎI TỰ MƠ HỒ  -> ambiguous

    Nhớ: narrow KHÔNG đồng nghĩa "có trích điều luật". Ví dụ narrow mà
    không trích điều nào:
        "Ông A mất 2019 không di chúc. Đến 2026 con riêng mới yêu cầu chia
         căn nhà ông đứng tên chung với vợ… Yêu cầu có được chấp nhận không?"
        T1 broad, T2 narrow (~2 điều), T3 narrow  =>  2/3  =>  narrow

  └────────────────────────────────────────────────────────────────────────┘
"""


def load(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"❌ Không thấy {path}\n"
                 f"   Chạy trước: python evol_instruct/scripts/11_verify_labels.py "
                 f"--export-manual-sample 100")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save(records: list[dict], path: Path):
    """Ghi qua file tạm rồi thay thế — Ctrl+C giữa chừng không làm rách file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def show_header(idx: int, total: int, done: int, rec: dict):
    w = width()
    clear()
    bar_w = max(w - 28, 10)
    filled = int(bar_w * done / total) if total else 0
    print()
    print(BOLD(f"  GÁN NHÃN TAY   câu {idx + 1}/{total}   đã xong {done}"))
    print(DIM("  [" + "#" * filled + "." * (bar_w - filled) + "]"))
    print()
    print(DIM("  " + "─" * (w - 4)))
    for line in textwrap.wrap(rec["question"], w - 6):
        print("  " + CYAN(line))
    print(DIM("  " + "─" * (w - 4)))
    print()


def _show_rubric():
    clear()
    print(RUBRIC)
    print(DIM("    Bấm phím bất kỳ để quay lại..."))
    get_key()


def ask_axis(axis_key, title, options, idx, total, done, rec, picked) -> str:
    valid = {o[0]: o[1] for o in options}
    while True:
        show_header(idx, total, done, rec)
        trail = "   ".join(
            f"{lbl}={picked[k]}" for k, lbl in
            (("axis1", "T1"), ("axis2", "T2"), ("axis3", "T3")) if k in picked
        )
        if trail:
            print(DIM("  đã chấm:  " + trail))
            print()
        print("  " + BOLD(title))
        print()
        for key, _, desc, effect in options:
            print(f"    {GREEN('[' + key + ']')}  {desc}")
            print(f"         {DIM(effect)}")
        print()
        print(DIM("   >> " + HINTS[axis_key]))
        print()
        print(DIM("    [h] xem lại tiêu chí    [u] quay lại câu trước    [q] lưu & thoát"))
        k = get_key()
        if k in valid:
            val = valid[k]
            if (axis_key == "axis1" and val == "both"
                    and not has_dieu_and_khoan(rec["question"])):
                if not warn_override1(idx, total, done, rec):
                    continue          # chọn lại Trục 1
            return val
        if k == "h":
            _show_rubric()
        elif k in ("u", "q"):
            return k


def warn_override1(idx, total, done, rec) -> bool:
    """Hỏi lại khi chọn phủ quyết #1 mà câu hỏi không có chữ 'khoản'."""
    while True:
        show_header(idx, total, done, rec)
        print("  " + YELLOW(BOLD("  ⚠  Câu này không có chữ \"khoản\" kèm số.")))
        print()
        print('     Phủ quyết #1 chỉ áp khi nêu đích danh CẢ điều VÀ khoản')
        print('     (vd "khoản 1 Điều 35"). Chỉ có "Điều 96", hay số hiệu văn bản')
        print('     như "Nghị định 139/2017/NĐ-CP", thì thuộc mức ' + BOLD("[2]") + ' chứ không')
        print("     phải [1] — và khi đó Trục 2 / Trục 3 vẫn phải chấm bình thường.")
        print()
        print(DIM("     [2] chuyển sang mức [2] (khuyên dùng)     [1] tôi chắc, giữ phủ quyết"))
        k = get_key()
        if k == "1":
            return True
        if k == "2":
            return False


def ask_quick(idx, total, done, rec) -> str:
    while True:
        show_header(idx, total, done, rec)
        print("    " + GREEN("[n]") + " narrow       "
              + GREEN("[b]") + " broad       " + GREEN("[a]") + " ambiguous")
        print()
        print(DIM("    [h] tiêu chí    [u] quay lại    [q] lưu & thoát"))
        k = get_key()
        if k in ("n", "b", "a"):
            return {"n": "narrow", "b": "broad", "a": "ambiguous"}[k]
        if k in ("u", "q"):
            return k
        if k == "h":
            _show_rubric()


def confirm(idx, total, done, rec, axes, label, why) -> str:
    colour = {"narrow": GREEN, "broad": YELLOW, "ambiguous": RED}[label]
    while True:
        show_header(idx, total, done, rec)
        print(f"    T1={axes['axis1']}    T2={axes['axis2']}    T3={axes['axis3']}")
        print()
        print("    =>  " + colour(BOLD(label.upper())))
        print(DIM(f"        {why}"))
        print()
        print(DIM("    [Enter] đồng ý & sang câu kế"))
        print(DIM("    [a] ghi đè thành ambiguous    [u] chấm lại câu này    [q] lưu & thoát"))
        k = get_key()
        if k in ("\n", " "):
            return "ok"
        if k in ("a", "u", "q"):
            return k


def _undo(records, pending, history):
    """Xoá nhãn của câu vừa gán và lùi con trỏ về đó. Trả về vị trí mới."""
    if not history:
        return None
    pos = history.pop()
    rec = records[pending[pos]]
    rec["manual_label"] = ""
    rec.pop("manual_axes", None)
    rec.pop("manual_rule", None)
    return pos


def run(records: list[dict], path: Path, quick: bool):
    total = len(records)
    pending = [i for i, r in enumerate(records) if not r.get("manual_label")]
    if not pending:
        clear()
        print(GREEN(f"\n  ✅ Cả {total} câu đã có nhãn."))
        summarize(records)
        return

    clear()
    print(RUBRIC)
    print(BOLD(f"    Còn {len(pending)}/{total} câu chưa gán.")
          + DIM("   Tự lưu sau mỗi câu — bỏ dở lúc nào cũng được."))
    print(DIM("\n    Bấm phím bất kỳ để bắt đầu..."))
    get_key()

    history: list[int] = []
    pos = 0
    while pos < len(pending):
        i = pending[pos]
        rec = records[i]
        done = sum(1 for r in records if r.get("manual_label"))

        if quick:
            ans = ask_quick(i, total, done, rec)
            if ans == "q":
                break
            if ans == "u":
                back = _undo(records, pending, history)
                if back is not None:
                    pos = back
                continue
            rec["manual_label"] = ans
            rec["manual_axes"] = {}
            rec["manual_rule"] = "quick mode — người gán tự tổng hợp 3 trục"
        else:
            picked: dict = {}
            ctrl = None
            for axis_key, title, options in QUESTIONS:
                ans = ask_axis(axis_key, title, options, i, total, done, rec, picked)
                if ans in ("u", "q"):
                    ctrl = ans
                    break
                picked[axis_key] = ans
                # Một khi nhãn đã bị chốt bởi phủ quyết §4, hoặc đã rơi vào vùng
                # xám, thì các trục còn lại KHÔNG thể đổi kết quả nữa. Hỏi tiếp
                # là bắt người gán làm việc thừa — đúng thứ script này sinh ra
                # để tránh.
                if (axis_key == "axis1" and ans == "both") or (
                    axis_key == "axis2" and ans in ("multi", "unknown")
                ):
                    break
            if ctrl == "q":
                break
            if ctrl == "u":
                back = _undo(records, pending, history)
                if back is not None:
                    pos = back
                continue

            # Trục bị bỏ qua do chốt sớm ghi "n/a", KHÔNG ghi "unknown" —
            # "unknown" ở axis2 là một lựa chọn có nghĩa (vùng xám), lẫn hai
            # thứ đó vào nhau là làm hỏng cả `resolve()` lẫn phần audit sau này.
            axes = {k: picked.get(k, "n/a") for k in ("axis1", "axis2", "axis3")}
            label, why = resolve(axes)

            action = confirm(i, total, done, rec, axes, label, why)
            if action == "q":
                break
            if action == "u":
                continue
            if action == "a":
                label, why = "ambiguous", "người gán ghi đè: kết quả nghịch trực giác"
            rec["manual_label"] = label
            rec["manual_axes"] = axes
            rec["manual_rule"] = why

        save(records, path)
        history.append(pos)
        pos += 1

    save(records, path)
    clear()
    summarize(records)


def summarize(records: list[dict]):
    from collections import Counter
    labelled = [r for r in records if r.get("manual_label")]
    dist = Counter(r["manual_label"] for r in labelled)
    print(BOLD(f"\n  📊 Đã gán {len(labelled)}/{len(records)} câu"))
    for k in ("narrow", "broad", "ambiguous"):
        if dist.get(k):
            print(f"     {k:<11}{dist[k]:>4}")
    if len(labelled) < len(records):
        print(YELLOW(f"\n  ⏸  Còn {len(records) - len(labelled)} câu. "
                     f"Chạy lại script này để gán tiếp."))
        return
    if dist.get("ambiguous", 0) > len(records) * 0.2:
        print(YELLOW(f"\n  ⚠️  {dist['ambiguous']} câu ambiguous (>20%) sẽ bị loại khỏi κ — "
                     f"κ tính trên mẫu quá nhỏ thì yếu (guideline §7)."))
    print(GREEN("\n  ✅ Xong. Bước cuối:"))
    print("     python evol_instruct/scripts/11_verify_labels.py \\")
    print("            --compute-kappa data/qa_pairs/labeled/manual_sample_blind.jsonl")


def review(records: list[dict]):
    from collections import Counter
    labelled = [r for r in records if r.get("manual_label")]
    if not labelled:
        sys.exit("Chưa gán câu nào.")
    w = width()
    for n, r in enumerate(labelled, 1):
        print(BOLD(f"\n[{n}] ") + DIM(r["item_id"]) + "  =>  " + BOLD(r["manual_label"]))
        for line in textwrap.wrap(r["question"], w - 4):
            print("    " + line)
        if r.get("manual_rule"):
            print(DIM(f"    ({r['manual_rule']})"))
    print(BOLD(f"\nTổng: {dict(Counter(r['manual_label'] for r in labelled))}"))


def main():
    p = argparse.ArgumentParser(description="Gán nhãn tay cho vòng tính Cohen's kappa")
    p.add_argument("--file", type=Path, default=MANUAL_SAMPLE_FILE)
    p.add_argument("--quick", action="store_true",
                   help="1 phím/câu (n/b/a) — tự tổng hợp 3 trục trong đầu")
    p.add_argument("--review", action="store_true", help="In lại các câu đã gán rồi thoát")
    args = p.parse_args()

    records = load(args.file)

    if args.review:
        review(records)
        return

    # Bản gốc chưa gán, để còn làm lại từ đầu nếu cần.
    backup = args.file.with_name(args.file.stem + ".orig.jsonl")
    if not backup.exists():
        shutil.copy2(args.file, backup)

    try:
        run(records, args.file, quick=args.quick)
    except KeyboardInterrupt:
        save(records, args.file)
        clear()
        print(YELLOW("\n  ⏸  Đã dừng — tiến độ đã lưu."))
        summarize(records)


if __name__ == "__main__":
    main()
