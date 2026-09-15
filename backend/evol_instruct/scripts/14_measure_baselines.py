"""
Script 14: Đo các BASELINE TẦM THƯỜNG trên dataset đã export.

─── Vì sao cần script này ───

F1 của model fine-tune không tự nó nói lên điều gì. Nếu một quy tắc regex một
dòng cũng đạt 84% thì F1 92% chỉ hơn regex 8 điểm, và cả Phần 3 mất chỗ đứng
khi bảo vệ. Con số phải báo cáo CẠNH F1 là: "baseline tầm thường đạt bao nhiêu
trên chính tập test này".

Ba baseline, từ ngây thơ đến mạnh:

  1. Shortcut regex — "câu có nhắc số Điều ⇒ narrow", đúng một dòng. Đây là
     shortcut mà Phần 3 phải triệt: nếu nó cao, dataset chỉ đang dạy model đếm
     chữ "Điều".
  2. TF-IDF + Logistic Regression — túi từ, không hiểu nghĩa. Nếu nó gần như
     hoàn hảo thì nhãn đoán được từ VĂN PHONG template, không phải từ độ cụ thể.
  3. Chuyển nhánh (train citation → test situation và ngược lại) — đo xem hai
     nhánh có thật sự cùng một khái niệm "độ cụ thể" hay là hai template rời.

Với cả ba, THẤP LÀ TỐT: baseline càng kém thì bài toán càng thật.

─── Cách dùng ───

    cd backend/
    python evol_instruct/scripts/14_measure_baselines.py
    python evol_instruct/scripts/14_measure_baselines.py --output data/qa_pairs/final/baselines.json
    python evol_instruct/scripts/14_measure_baselines.py --compare <thư mục final của bản cũ>
"""

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loguru import logger

from config.qa_settings import BASE_DIR, QA_FINAL_DIR, RANDOM_SEED
from evol_instruct.src.qa_specificity.weak_labeler import RE_ARTICLE_NUM


def relative_to_base(path: Path) -> str:
    try:
        return path.resolve().relative_to(BASE_DIR).as_posix()
    except ValueError:
        return path.name


def doc(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def nhan(r: dict) -> str:
    return r.get("final_label") or r.get("specificity")


def nhanh(r: dict) -> str:
    return (r.get("metadata") or {}).get("narrow_mode", "?")


def shortcut_du_doan(cau: str) -> str:
    """Quy tắc một dòng: có nhắc số Điều ⇒ narrow."""
    return "narrow" if RE_ARTICLE_NUM.search(cau) else "broad"


def do_shortcut(test: list[dict]) -> dict:
    """Độ chính xác của quy tắc regex, tổng thể và tách theo nhánh."""
    def acc(rs):
        if not rs:
            return None
        return sum(shortcut_du_doan(r["question"]) == nhan(r) for r in rs) / len(rs)

    theo_nhanh = collections.defaultdict(list)
    for r in test:
        theo_nhanh[nhanh(r)].append(r)

    return {
        "tong": acc(test),
        "n": len(test),
        "theo_nhanh": {k: {"acc": acc(v), "n": len(v)} for k, v in sorted(theo_nhanh.items())},
    }


def do_tfidf(train: list[dict], test: list[dict]) -> float | None:
    """TF-IDF + LR huấn luyện trên train, đo trên test."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    if not train or not test or len({nhan(r) for r in train}) < 2:
        return None
    pipe = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2),
        LogisticRegression(max_iter=1000, random_state=RANDOM_SEED),
    )
    pipe.fit([r["question"] for r in train], [nhan(r) for r in train])
    du_doan = pipe.predict([r["question"] for r in test])
    return sum(p == nhan(r) for p, r in zip(du_doan, test)) / len(test)


def do_chuyen_nhanh(train: list[dict], test: list[dict]) -> dict:
    """Huấn luyện trên một nhánh, đo trên nhánh kia."""
    ket_qua = {}
    for nguon in ("citation", "situation"):
        dich = "situation" if nguon == "citation" else "citation"
        tr = [r for r in train if nhanh(r) == nguon]
        te = [r for r in test if nhanh(r) == dich]
        ket_qua[f"{nguon}→{dich}"] = {"acc": do_tfidf(tr, te), "n_train": len(tr), "n_test": len(te)}
    return ket_qua


def do_toan_bo(data_dir: Path) -> dict:
    train = doc(data_dir / "train.json")
    test = doc(data_dir / "test.json")
    return {
        "data_dir": relative_to_base(data_dir),
        "n_train": len(train),
        "n_test": len(test),
        "shortcut": do_shortcut(test),
        "tfidf": do_tfidf(train, test),
        "chuyen_nhanh": do_chuyen_nhanh(train, test),
    }


def pct(x) -> str:
    return "—" if x is None else f"{x:.1%}"


def in_bang(kq: dict, ten: str) -> None:
    logger.info(f"\n── {ten}  ({kq['n_train']} train / {kq['n_test']} test) ──")
    sc = kq["shortcut"]
    logger.info(f"   1. Shortcut regex 'có số Điều ⇒ narrow' : {pct(sc['tong'])}")
    for mode, d in sc["theo_nhanh"].items():
        logger.info(f"        {mode:<10} n={d['n']:<5} {pct(d['acc'])}")
    logger.info(f"   2. TF-IDF + LR                          : {pct(kq['tfidf'])}")
    logger.info("   3. Chuyển nhánh:")
    for huong, d in kq["chuyen_nhanh"].items():
        logger.info(f"        {huong:<22} n={d['n_test']:<5} {pct(d['acc'])}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo baseline tầm thường trên dataset")
    parser.add_argument("--data-dir", type=Path, default=QA_FINAL_DIR,
                        help="Thư mục chứa train.json/test.json")
    parser.add_argument("--compare", type=Path, metavar="DIR",
                        help="Đo thêm một dataset nữa để đối chiếu (ví dụ bản cũ)")
    parser.add_argument("--output", type=Path,
                        help="Ghi kết quả ra JSON")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("📏 ĐO BASELINE TẦM THƯỜNG — thấp là tốt")
    logger.info("=" * 60)

    chinh = do_toan_bo(args.data_dir)
    in_bang(chinh, f"HIỆN TẠI · {relative_to_base(args.data_dir)}")

    ket_qua = {"hien_tai": chinh}
    if args.compare:
        cu = do_toan_bo(args.compare)
        in_bang(cu, f"ĐỐI CHIẾU · {relative_to_base(args.compare)}")
        ket_qua["doi_chieu"] = cu

        logger.info("\n── CHÊNH LỆCH (hiện tại − đối chiếu; ÂM là tiến bộ) ──")
        for ten, a, b in [
            ("Shortcut regex", chinh["shortcut"]["tong"], cu["shortcut"]["tong"]),
            ("TF-IDF + LR", chinh["tfidf"], cu["tfidf"]),
        ]:
            if a is not None and b is not None:
                logger.info(f"   {ten:<22} {pct(b)} → {pct(a)}   ({(a - b) * 100:+.1f} điểm)")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(ket_qua, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"\n→ {relative_to_base(args.output)}")

    logger.info(
        "\n⚠️  Đọc đúng chiều: baseline THẤP nghĩa là dataset khó bằng shortcut, "
        "tức Phần 3 có chỗ đứng. Baseline cao thì F1 của model fine-tune dù đẹp "
        "cũng không chứng minh được gì."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
