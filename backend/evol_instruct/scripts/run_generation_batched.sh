#!/usr/bin/env bash
# Sinh cặp QA theo từng mẻ nhỏ thay vì một tiến trình chạy suốt.
#
# Vì sao phải chia mẻ: llama-server giữ ~12GB trên máy 31GB, nên tiến trình
# Python chạy liên tục vài giờ bị hệ điều hành kill khi RAM trống xuống thấp
# (đã xảy ra 2 lần: document 3.481/5.017 và 1.819/4.050). Mỗi mẻ là một tiến
# trình riêng, thoát xong là trả hết RAM, và checkpoint giữ tiến độ nên không
# mất gì.
#
# Chạy từ backend/:  bash evol_instruct/scripts/run_generation_batched.sh [BATCH]

set -u
cd "$(dirname "$0")/../.." || exit 1

BATCH="${1:-300}"
PY="../venv/Scripts/python.exe"
CHECKPOINT="data/qa_pairs/raw/generation_checkpoint.json"

export TMPDIR="$(pwd)/data/qa_pairs/raw/tmp"
export TEMP="$TMPDIR" TMP="$TMPDIR"
mkdir -p "$TMPDIR"

processed() {
  "$PY" -c "
import json, io, sys
try:
    print(len(json.load(io.open('$CHECKPOINT', encoding='utf-8'))['processed_ids']))
except Exception:
    print(0)
"
}

truoc=$(processed)
echo "== bắt đầu: đã xử lý $truoc văn bản, mẻ $BATCH văn bản/lượt =="

while :; do
  "$PY" evol_instruct/scripts/10_generate_qa_pairs.py --limit "$BATCH" 2>&1 \
    | sed 's/\x1b\[[0-9;]*m//g' \
    | grep -Ea "Cặp sinh thành công|Documents xử lý|Traceback|Error|Killed" \
    | sed 's/^/   /'

  sau=$(processed)
  echo "== đã xử lý $sau văn bản =="

  if [ "$sau" -le "$truoc" ]; then
    echo "== không tiến thêm được (còn $sau) — dừng =="
    break
  fi
  truoc="$sau"
done

echo "== SINH CẶP XONG: $truoc văn bản =="
