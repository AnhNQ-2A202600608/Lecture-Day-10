# Runbook — Lab Day 10 (Incident Tối Giản)

Tài liệu hướng dẫn vận hành và khắc phục sự cố dữ liệu.

---

## Symptom

- **User / Agent thấy gì?**
  - Trả lời "14 ngày hoàn tiền" thay vì "7 ngày làm việc" cho khách hàng.
  - Trả lời nhân viên dưới 3 năm kinh nghiệm có "10 ngày phép năm" thay vì "12 ngày".
  - Không truy vấn được hoặc trả lời sai về quy trình "Access Control Level 4".

---

## Detection

- **Metric báo lỗi:**
  - Freshness check báo `FAIL` (vượt quá 24h đối với dữ liệu thô, hoặc vượt quá 1h đối với vector DB).
  - Pipeline chạy bị dừng giữa chừng với thông báo `PIPELINE_HALT`.
  - Kết quả kiểm định truy vấn (`eval_retrieval.py` hoặc `grading_run.py`) báo `hits_forbidden=yes` hoặc `top1_doc_expected=no`.

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| **1** | Kiểm tra file manifest mới nhất `artifacts/manifests/*.json` | Xác định thời điểm xuất dữ liệu `latest_exported_at` và pipeline run `run_timestamp`. |
| **2** | Mở file cách ly `artifacts/quarantine/*.csv` | Xem lý do các record bị loại bỏ (ví dụ: `stale_hr_policy_text`, `unknown_doc_id`). |
| **3** | Chạy kiểm tra nhanh chất lượng | `$env:PYTHONIOENCODING="utf-8"; python instructor_quick_check.py --grading artifacts/eval/grading_run.jsonl` để định vị câu hỏi bị lỗi. |

---

## Mitigation

1. **Khi dữ liệu thô bị stale:** Liên hệ Data Owner của hệ thống nguồn để xuất bản mới nhất.
2. **Khi pipeline bị HALT do expectation:** Kiểm tra log để tìm nguyên nhân, sửa dữ liệu thô hoặc điều chỉnh logic làm sạch nếu có thay đổi chính sách hợp lệ.
3. **Khi vector DB bị nhiễm dữ liệu cũ:** Thực hiện chạy lại pipeline chuẩn để kích hoạt cơ chế `col.delete` tự động xóa bỏ các vector ID thừa.

---

## Prevention

1. **Thêm Expectations:** Duy trì kiểm định schema bằng Pydantic và kiểm định định dạng ngày nghiêm ngặt.
2. **Môi trường:** Đưa các cấu hình cutoff date vào biến môi trường để dễ dàng điều chỉnh khi có chính sách mới mà không cần sửa code.
