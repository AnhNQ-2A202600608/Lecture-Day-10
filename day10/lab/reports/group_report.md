# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** CS_IT_Helpdesk_Data_Team  
**Thành viên:**
| Tên | Vai trò (Day 10) | Email |
|-----|------------------|-------|
| AnhNQ | Ingestion / Raw Owner | anhnq@company.com |
| AnhNQ | Cleaning & Quality Owner | anhnq@company.com |
| AnhNQ | Embed & Idempotency Owner | anhnq@company.com |
| AnhNQ | Monitoring / Docs Owner | anhnq@company.com |

**Ngày nộp:** 2026-06-10  
**Repo:** VinAi-Day-10-Lab  

---

## 1. Pipeline tổng quan (150–200 từ)

Hệ thống sử dụng tệp đầu vào thô từ [policy_export_dirty.csv](../data/raw/policy_export_dirty.csv) đại diện cho dữ liệu xuất bản thô từ 5 hệ thống CS/IT. Luồng xử lý end-to-end bao gồm: nạp dữ liệu -> áp dụng các cleaning rules -> kiểm tra chất lượng qua bộ suite expectations (với Pydantic schema validation và 4 expectations tự thiết lập) -> nạp dữ liệu sạch vào cơ sở dữ liệu vector Chroma DB bằng SentenceTransformers. 

**Lệnh chạy một dòng:**
```bash
python etl_pipeline.py run
```
`run_id` được sinh tự động theo định dạng thời gian UTC (ví dụ: `2026-06-10T06-32Z`), ghi nhận trực tiếp vào tệp manifest và logs tương ứng tại thư mục `artifacts/`.

---

## 2. Cleaning & expectation (150–200 từ)

Bên cạnh các quy tắc baseline, nhóm đã bổ sung **4 cleaning rules** mới và **4 expectations** mới để nâng cao tính ổn định của hệ thống:

### 2a. Bảng metric_impact

| Rule / Expectation mới (tên ngắn) | Trước (số liệu) | Sau / khi inject (số liệu) | Chứng cứ (log / CSV / commit) |
|-----------------------------------|------------------|-----------------------------|-------------------------------|
| `internal_sentence_deduplication` | 33 cleaned records | 32 cleaned records (mất 1 dòng lặp) | `analyze_cleaned.py` & cleaned CSV |
| `export_timestamp_normalization` | 5 dòng dạng slash | Đưa về ISO dash hoàn toàn | `pydantic_schema_validation` PASS |
| `refund_exception_enrichment` | top1 = `it_helpdesk_faq` | top1 = `policy_refund_v4` | `grading_run.jsonl` row 2 |
| `phone_extension_standardization` | chứa `ext. 1234` | chuẩn hóa `extension 1234` | Cleaned CSV |
| `pydantic_schema_validation` | Chưa validate schema | Validate 100% dòng sạch thành công | Log expectation E9 |
| `exported_at_iso_format` | Chưa kiểm tra | Validate ISO format thành công | Log expectation E10 |
| `chunk_max_length_1000` | Chưa kiểm tra | Cảnh báo khi chunk > 1000 ký tự | Log expectation E11 |
| `no_duplicate_chunk_ids` | Chưa kiểm tra | Đảm bảo ID không bị trùng lặp | Log expectation E12 |

---

## 3. Before / after ảnh hưởng retrieval hoặc agent (200–250 từ)

**Kịch bản inject:**
Chúng tôi chạy thử nghiệm inject lỗi thông qua lệnh:
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```
Khi chạy kịch bản này, pipeline không áp dụng sửa lỗi refund window 14 ngày về 7 ngày và cho phép nạp trực tiếp vào Chroma.

**Kết quả định lượng:**
- Ở tập eval lỗi ([after_inject_bad.csv](../artifacts/eval/after_inject_bad.csv)), câu hỏi `gq_d10_01` báo `hits_forbidden = yes` vì kết quả truy vấn chứa dữ liệu stale hoàn tiền 14 ngày làm việc.
- Sau khi khôi phục lại chạy chuẩn ([after_fix_eval.csv](../artifacts/eval/after_fix_eval.csv)), `hits_forbidden` báo `no` (hoặc `false` trên JSONL) và thông tin hoàn trả chính xác là 7 ngày làm việc.
- Việc áp dụng `refund_exception_enrichment` cải thiện đáng kể semantic similarity cho câu hỏi `gq_d10_02`, đưa tài liệu chính xác `policy_refund_v4` lên top-1 (Rank 1) thay vì bị che mờ bởi IT Helpdesk FAQ như ban đầu.

---

## 4. Freshness & monitoring (100–150 từ)

Nhóm áp dụng mô hình giám sát 2 boundary:
- **Ingestion SLA:** Mức trần 24 giờ. Vì tập mẫu xuất từ tháng 4/2026 nên checkpoint này báo `FAIL` (age = 1470h). Trên thực tế, dữ liệu cần được trigger export định kỳ.
- **Publish SLA:** Mức trần 1.0 giờ. Checkpoint báo `PASS` (age = 0.0h) chứng minh cơ sở dữ liệu vector vừa được làm mới tức thì sau khi ETL hoàn tất.

---

## 5. Liên hệ Day 09 (50–100 từ)

Dữ liệu sạch được lưu vào collection `day10_kb`. Agent ở Day 09 sử dụng collection này sẽ ngay lập tức được cập nhật thông tin chuẩn nhất mà không bị lẫn lộn các chính sách cũ (như chính sách phép năm 2025 hoặc cửa sổ hoàn trả cũ). Điều này giúp Agent ra quyết định và trả lời chính xác cho người dùng cuối.

---

## 6. Rủi ro còn lại & việc chưa làm

- Cần tích hợp Slack webhook hoặc PagerDuty alert thực tế ở bước freshness FAIL để gửi thông báo tự động cho Data Ops team.
