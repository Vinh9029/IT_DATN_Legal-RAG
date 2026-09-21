# Đưa dataset QA specificity lên HuggingFace

Repo: <https://huggingface.co/datasets/ThanhVu101/Vietnamese-Legal-QA>

Đăng nhập một lần mỗi máy: `venv/Scripts/hf.exe auth login` (token quyền write).

## Cập nhật — chạy từ `backend/`

Đủ thứ tự này: card lấy số từ output của script 12 và 14, bỏ bước nào thì card
mang số của bản cũ.

```bash
../venv/Scripts/python.exe evol_instruct/scripts/12_export_dataset.py
../venv/Scripts/python.exe evol_instruct/scripts/14_measure_baselines.py
../venv/Scripts/python.exe -m evol_instruct.src.qa_specificity.hf_publisher --version v4
../venv/Scripts/hf.exe upload ThanhVu101/Vietnamese-Legal-QA data/qa_pairs/final . \
    --repo-type dataset --commit-message "Cap nhat v4"
```

`--delete "*"` ở lệnh cuối nếu muốn file không còn trong `final/` cũng biến mất
trên Hub.

## Lưu ý

- **Đẩy nguyên folder, không gộp 1 file.** Split là group-split theo
  `source_doc_id`; gộp rồi random split lại là tái tạo đúng leakage đã bỏ công
  tránh.
- **`--private` của `hf upload` không có tác dụng lúc tạo repo mới** (hub
  1.28.0) — repo vẫn ra public. Kiểm bằng `HfApi().repo_info(...).private`.
- **Viewer cần repo public** với tài khoản free.
- **License đang là `other`** — câu hỏi do Llama-3.1 sinh, Llama Community
  License có ràng buộc cần đọc trước khi chốt.
