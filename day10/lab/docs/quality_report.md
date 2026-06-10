# Quality Report — Lab Day 10 (Nhóm)

**run_id:** `2026-06-10T06-32Z` (Standard) & `inject-bad` (Corrupt)  
**Ngày:** 2026-06-10

---

## 1. Tóm tắt số liệu

| Chỉ số | Trước (Baseline) | Sau (Fix) | Ghi chú |
|--------|-------|-----|---------|
| `raw_records` | 247 | 247 | Khớp dữ liệu nguồn |
| `cleaned_records` | 33 | 32 | Giảm 1 record do gộp câu lặp ở dòng 26 |
| `quarantine_records` | 214 | 215 | Tăng 1 record bị loại bỏ |
| Expectation halt? | Không | Không | Pipeline chạy qua và exit 0 |

---

## 2. Before / after retrieval

Tập tin kiểm thử before/after được lưu tại:
- Chuẩn: [after_fix_eval.csv](file:///d:/code/VinAi%20Action/day10/Lecture-Day-10/day10/lab/artifacts/eval/after_fix_eval.csv)
- Inject lỗi: [after_inject_bad.csv](file:///d:/code/VinAi%20Action/day10/Lecture-Day-10/day10/lab/artifacts/eval/after_inject_bad.csv)

### Câu hỏi: `gq_d10_02` (refund exception - hàng kỹ thuật số)
- **Trước (Chạy thô / Index bẩn):**
  - Trả về `top1_doc_id` = `it_helpdesk_faq` (sai lệch thông tin).
  - Trạng thái `top1_doc_matches` = `false`.
- **Sau (Sau khi áp dụng rule `refund_exception_enrichment`):**
  - Trả về `top1_doc_id` = `policy_refund_v4` (chính xác).
  - Trạng thái `top1_doc_matches` = `true`.

### Câu hỏi: `gq_d10_09` (HR leave policy 2026 vs 2025)
- **Khi bị Inject lỗi (chạy với `--no-refund-fix --skip-validate`):**
  - `expectation[refund_no_stale_14d_window]` bị `FAIL (halt) :: violations=1` do lọt refund window 14 ngày.
- **Khi chạy chuẩn:**
  - `expectation[refund_no_stale_14d_window]` đạt `OK (halt)`.

---

## 3. Freshness & monitor

Kết quả `freshness_check` trả về trạng thái **FAIL** chung do Ingestion SLA vượt quá mốc cấu hình, cụ thể:
1. **Ingestion Boundary:** `latest_exported_at` của dữ liệu mẫu là `"2026-04-10T00:00:00"` (trễ 1470.55 giờ so với hiện tại), vượt quá `sla_hours = 24.0` -> **FAIL**.
2. **Publish Boundary:** `run_timestamp` của vector DB là `"2026-06-10T06:33:08"` (trễ 0.0 giờ), đạt yêu cầu `sla_hours = 1.0` -> **PASS**.

*Giải thích:* Việc Ingestion Boundary bị FAIL trên tập dữ liệu mẫu là hoàn toàn bình thường do ngày export cố định trong quá khứ.

---

## 4. Corruption inject (Sprint 3)

- **Cách thức thực hiện:** Chạy pipeline với tham số `--no-refund-fix --skip-validate` để cố tình nạp dữ liệu hoàn tiền stale 14 ngày vào Chroma DB mà bỏ qua kiểm duyệt.
- **Phát hiện:** Pipeline log báo `FAIL` ở expectation `refund_no_stale_14d_window`. File eval sinh ra chứa `hits_forbidden = yes` cho câu hỏi `gq_d10_01`.

---

## 5. Hạn chế & việc chưa làm

- Cần tự động hóa cập nhật ngày xuất bản dữ liệu thô (tiệm cận thời gian thực) để Ingestion Freshness đạt trạng thái PASS khi chạy production.
