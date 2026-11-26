#!/usr/bin/env bash
# Sinh câu trả lời QA (script 23) theo từng mẻ, nạp lại model giữa các mẻ.
#
# Cùng lý do với run_verify_batched.sh: tiến trình chạy vài giờ trên máy 31GB bị
# hệ điều hành kill. Thêm một lý do riêng: llama-server phình RAM dần vì prompt
# cache (đo 2026-11-18: 7GB → 15GB), nên sau mỗi mẻ `lms unload` rồi nạp lại với
# context cố định — RAM về mức ban đầu. Cache câu trả lời ghi append nên tắt ngang
# lúc nào cũng không mất gì; muốn dừng êm thì `touch data/qa_answers/STOP`.
#
# Chạy từ backend/:
#   bash evol_instruct/scripts/run_answers_batched.sh [BATCH] [PARALLEL]

set -u
cd "$(dirname "$0")/../.." || exit 1

BATCH="${1:-300}"
PARALLEL="${2:-3}"
CTX="${ANSWER_CTX:-16384}"
MODEL="${ANSWER_MODEL_NAME:-google/gemma-4-12b-qat}"
PY="../venv/Scripts/python.exe"
CACHE="data/qa_answers/answers_cache.jsonl"
export PYTHONIOENCODING=utf-8

NEED_GB="${ANSWER_NEED_GB:-18}"   # RAM trống cần có (khi CHƯA nạp model) để chạy tiếp

ok_lines() { grep -c '"answer": "' "$CACHE" 2>/dev/null || echo 0; }

free_gb() { powershell -NoProfile -c "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB)"; }

# RAM thấp (vd. người dùng mở game): gỡ model trả RAM, chờ đến khi đủ rồi mới chạy tiếp.
# Không thoát hẳn — tắt app kia là job tự chạy lại.
wait_for_ram() {
  lms unload --all >/dev/null 2>&1
  local f; f=$(free_gb)
  if [ "$f" -lt "$NEED_GB" ]; then
    echo "== $(date '+%F %T') RAM trống ${f}GB < ${NEED_GB}GB — gỡ model, chờ RAM =="
    while [ "$(free_gb)" -lt "$NEED_GB" ]; do
      [ -e data/qa_answers/STOP ] && return 1
      sleep 60
    done
    echo "== $(date '+%F %T') RAM đủ ($(free_gb)GB) — chạy tiếp =="
  fi
}

reload_model() {
  lms unload --all >/dev/null 2>&1
  lms load "$MODEL" -c "$CTX" --parallel "$PARALLEL" --gpu max -y >/dev/null 2>&1 \
    || { echo "== nạp model lỗi =="; return 1; }
}

lms server start >/dev/null 2>&1
truoc=$(ok_lines)
echo "== $(date '+%F %T') bắt đầu: $truoc câu đã có, mẻ $BATCH, song song $PARALLEL, ctx $CTX =="

while :; do
  if [ -e data/qa_answers/STOP ]; then echo "== gặp STOP, dừng =="; break; fi
  wait_for_ram || { echo "== gặp STOP khi chờ RAM, dừng =="; break; }
  reload_model || exit 1
  "$PY" evol_instruct/scripts/23_generate_qa_answers.py generate \
      --max-items "$BATCH" --parallel "$PARALLEL" --min-free-gb "${ANSWER_MIN_FREE_GB:-4}" 2>&1 \
    | sed 's/\x1b\[[0-9;]*m//g' \
    | grep -Ea "Cần sinh|/[0-9]+ —|Mẻ xong|RAM trống .* dừng|STOP|Traceback|Error" \
    | sed 's/^/   /'
  rc=${PIPESTATUS[0]}
  sau=$(ok_lines)
  echo "== $(date '+%F %T') rc=$rc, đã có $sau câu =="

  case "$rc" in
    3) echo "== SINH XONG TOÀN BỘ =="; break ;;
    5) echo "== dừng theo STOP =="; break ;;
    4) echo "== RAM thấp: gỡ model, chờ RAM rồi chạy tiếp =="
       truoc="$sau"; continue ;;     # RAM thấp không phải hỏng server — không tính "không tiến"
  esac
  # Không tiến thêm câu nào = server hỏng hoặc prompt lỗi; lặp tiếp vô ích.
  if [ "$sau" -le "$truoc" ]; then echo "== không tiến thêm được — dừng =="; lms unload --all >/dev/null 2>&1; exit 1; fi
  truoc="$sau"
done
lms unload --all >/dev/null 2>&1
