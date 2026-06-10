# Data contract — Lab Day 10

Tài liệu đặc tả hợp đồng dữ liệu cho RAG Knowledge Base.

---

## 1. Nguồn dữ liệu (Source Map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `policy_refund_v4` | CSV Export | Refund window stale (14 ngày), duplicate sentences | Alert khi phát hiện "14 ngày làm việc" sau clean |
| `sla_p1_2026` | CSV Export | Thiếu ngày hiệu lực, trùng lặp dòng | Alert khi missing effective_date hoặc duplicate |
| `it_helpdesk_faq` | CSV Export | Trùng lặp dòng, khoảng trắng thừa, định dạng hotline | Alert khi duplicate hoặc non-ISO date |
| `hr_leave_policy` | CSV Export | Phiên bản cũ (10 ngày phép năm 2025) xen kẽ bản 2026 | Halt pipeline khi phát hiện "10 ngày phép năm" |
| `access_control_sop` | CSV Export | Ngày hiệu lực trước 2026-01-01, thiếu nội dung | Halt pipeline khi phát hiện stale date hoặc missing text |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú / Ràng buộc |
|-----|------|----------|---------|
| `chunk_id` | string | Có | Khóa chính, định dạng `{doc_id}_{seq}_{hash}` |
| `doc_id` | string | Có | Thuộc `allowed_doc_ids` trong data contract |
| `chunk_text` | string | Có | Tiền tố context enrichment + text đã làm sạch. Độ dài >= 8 ký tự |
| `effective_date` | date | Có | Chuẩn ISO YYYY-MM-DD |
| `exported_at` | datetime | Có | Chuẩn ISO YYYY-MM-DDThh:mm:ss |

---

## 3. Quy tắc quarantine vs drop

- **Record bị flag đi đâu?** Toàn bộ các record vi phạm các rule (sai ngày, unknown doc id, trùng lặp, stale content) sẽ được đưa vào thư mục cách ly `artifacts/quarantine/` dưới định dạng CSV với cột `reason` chỉ rõ nguyên nhân.
- **Merge lại:** Dữ liệu trong quarantine chỉ được phép hòa nhập lại vào pipeline chính sau khi Data Owner sửa đổi nguồn dữ liệu thô hoặc cập nhật các quy tắc làm sạch tương ứng.

---

## 4. Phiên bản & canonical

- **Source of truth cho policy refund:** File [policy_refund_v4.txt](file:///d:/code/VinAi%20Action/day10/Lecture-Day-10/day10/lab/data/docs/policy_refund_v4.txt) là tài liệu chuẩn. Mọi thông tin hoàn tiền 14 ngày làm việc đều là stale và được tự động ánh xạ về 7 ngày làm việc để đồng bộ với v4.
- **Source of truth cho HR leave policy:** File [hr_leave_policy.txt](file:///d:/code/VinAi%20Action/day10/Lecture-Day-10/day10/lab/data/docs/hr_leave_policy.txt) quy định 12 ngày phép năm cho nhân viên dưới 3 năm kinh nghiệm kể từ năm 2026. Phiên bản 2025 (10 ngày) bị loại bỏ.
