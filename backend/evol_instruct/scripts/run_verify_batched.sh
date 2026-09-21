#!/usr/bin/env bash
# Chấm judge theo từng mẻ nhỏ thay vì một tiến trình chạy suốt.
#
# Song sinh với run_generation_batched.sh, cùng một lý do: llama-server giữ
# ~12GB trên máy 31GB, nên tiến trình Python chạy vài tiếng bị hệ điều hành
# kill khi RAM trống xuống thấp. Đã xảy ra ở bước judge ngày 2026-09-15, chết
# tại câu 5.386/5.895 sau ~3 giờ. Mỗi mẻ là một tiến trình riêng, thoát xong
# trả hết RAM; judge_cache.jsonl ghi append từng câu nên không mất lượt nào.
#
# Chạy từ backend/:
#   bash evol_instruct/scripts/run_verify_batched.sh data/qa_pairs/raw/pairs_merged.jsonl [BATCH]

set -u
cd "$(dirname "$0")/../.." || exit 1

INPUT="${1:-data/qa_pairs/raw/pairs.jsonl}"
BATCH="${2:-500}"
PY="../venv/Scripts/python.exe"
CACHE="data/qa_pairs/labeled/judge_cache.jsonl"

cached() { wc -l < "$CACHE" 2>/dev/null || echo 0; }

truoc=$(cached)
echo "== bắt đầu: cache $truoc dòng, mẻ $BATCH câu/lượt, input $INPUT =="

while :; do
  "$PY" evol_instruct/scripts/11_verify_labels.py \
      --input "$INPUT" --warm-judge-cache "$BATCH" 2>&1 \
    | sed 's/\x1b\[[0-9;]*m//g' \
    | grep -Ea "còn lại|Mẻ xong|Judge xong|Không còn câu|Traceback|Error|Killed" \
    | sed 's/^/   /'
  rc=${PIPESTATUS[0]}

  # 3 = script báo đã chấm hết, không còn gì để làm.
  if [ "$rc" -eq 3 ]; then
    echo "== CHẤM XONG TOÀN BỘ =="
    break
  fi

  sau=$(cached)
  echo "== cache $sau dòng =="

  # Không tiến thêm nghĩa là judge hỏng (server chết, prompt lỗi). Lặp tiếp chỉ
  # quay vòng vô hạn mà không chấm được câu nào.
  if [ "$sau" -le "$truoc" ]; then
    echo "== không tiến thêm được (cache vẫn $sau) — dừng =="
    exit 1
  fi
  truoc="$sau"
done

echo "== Bước tiếp: lọc đồng thuận (0 lượt gọi, mọi câu lấy từ cache) =="
"$PY" evol_instruct/scripts/11_verify_labels.py --input "$INPUT" 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -v "DEBUG"
