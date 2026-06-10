# Hướng Dẫn Chi Tiết Hệ Thống Data Pipeline & Data Observability (Lab Day 10)

Hệ thống này được xây dựng để giải quyết bài toán Ingestion, Observability và Quality Check cho dữ liệu tài liệu trước khi đưa vào hệ thống RAG (Retrieval-Augmented Generation). 

Dưới đây là tài liệu đặc tả toàn diện về cấu trúc thư mục, chức năng từng file, logic nghiệp vụ chi tiết, và cách vận hành hệ thống.

---

## 1. Bản Đồ Thư Mục & Vai Trò Các File (Directory Architecture)

### 1.1. Tầng Entrypoint & Khởi Chạy
*   **[etl_pipeline.py](etl_pipeline.py)**: 
    *   *Chức năng*: Entrypoint chính điều phối toàn bộ vòng đời pipeline: `Tải CSV thô (Ingest) -> Làm sạch & Cách ly (Clean/Quarantine) -> Kiểm định chất lượng (Expectation Suite) -> Embedding & Dọn dẹp DB (Embed/Prune) -> Xuất Manifest`.
    *   *Xử lý*: Hỗ trợ CLI nhận các lệnh `run` (chạy pipeline) và `freshness` (giám sát độ tươi). Tự động cấu hình mã hóa UTF-8 cho dòng đầu ra trên Windows (`sys.stdout.reconfigure`) để tránh lỗi encoding khi in ký tự tiếng Việt.
*   **[pipeline_ui.html](pipeline_ui.html)**:
    *   *Chức năng*: Cổng thông tin Telemetry & Observability trực quan hóa toàn bộ luồng pipeline dưới dạng đồ họa Light-Mode cao cấp, hỗ trợ tương tác và thử nghiệm mô phỏng client-side.
    *   *Xử lý*: Cho phép kéo thả file JSON bẩn, tinh chỉnh cấu hình tham số động, chạy mô phỏng 4 bước với đường truyền dữ liệu động, hiển thị biểu đồ phân phối SVG, quản lý cách ly dữ liệu thô (Quarantine Inspector), kiểm định chi tiết schema Pydantic và tải console logs.

### 1.2. Tầng Nghiệp Vụ Core (Core Processing Modules)
*   **[transform/cleaning_rules.py](transform/cleaning_rules.py)**:
    *   *Chức năng*: Chứa toàn bộ các hàm lọc (filters), chuẩn hóa (normalizations), khử trùng lặp (deduplications) dữ liệu, và cách ly (quarantining) các dòng dữ liệu không đạt chuẩn.
    *   *Logic*: Áp dụng regex phức tạp và các so sánh logic ngày tháng động, gán Context Title làm tiền tố cho mỗi chunk nhằm tăng chất lượng retrieval.
*   **[quality/expectations.py](quality/expectations.py)**:
    *   *Chức năng*: Định nghĩa và thực thi bộ quy tắc kỳ vọng chất lượng (Expectation Suite) gồm 12 tiêu chí kiểm soát.
    *   *Logic*: Tích hợp kiểm định cấu trúc dữ liệu bằng mô hình **Pydantic Model Validation (`CleanedRow`)** thật. Phân loại nghiêm ngặt giữa lỗi ngắt pipeline (`halt`) và lỗi cảnh báo chất lượng (`warn`).
*   **[monitoring/freshness_check.py](monitoring/freshness_check.py)**:
    *   *Chức năng*: Đánh giá độ trễ và độ tươi mới (Data Freshness) của luồng thông tin.
    *   *Logic*: Phân tích tệp Manifest để kiểm tra SLA tại 2 ranh giới (Ingestion Boundary vs Publish Boundary) độc lập.

### 1.3. Tầng Cấu Hình & Hợp Đồng Dữ Liệu
*   **[contracts/data_contract.yaml](contracts/data_contract.yaml)**:
    *   *Chức năng*: Định nghĩa hợp đồng dữ liệu chuẩn của hệ thống bao gồm: Owner thông tin, cấu hình Allowed Doc IDs, ngưỡng thời hạn SLA Freshness, và mốc giới hạn phiên bản (`policy_versioning`) cho từng loại tài liệu.

### 1.4. Tầng Kiểm Thử & Chấm Điểm (Verification & Evaluation)
*   **[eval_retrieval.py](eval_retrieval.py)**:
    *   *Chức năng*: Thực hiện kiểm thử khả năng truy vấn thông tin (Retrieval Evaluation) dựa trên bộ câu hỏi tự kiểm `test_questions.json`. Xuất kết quả CSV để so sánh chất lượng.
*   **[grading_run.py](grading_run.py)**:
    *   *Chức năng*: Chạy kiểm định 10 câu hỏi đánh giá chính thức từ giảng viên, chấm điểm trực tiếp sự trùng khớp thông tin và ngăn ngừa các chunk chính sách cũ bị lọt vào kết quả.
*   **[instructor_quick_check.py](instructor_quick_check.py)**:
    *   *Chức năng*: Script chạy nhanh để giảng viên kiểm tra nhanh định dạng manifest và tính đúng đắn của tệp kết quả `grading_run.jsonl`.

---

## 2. Đặc Tả Chi Tiết Logic Nghiệp Vụ (Deep-Dive Business Logic)

### 2.1. Logic Làm Sạch Dữ Liệu (`transform/cleaning_rules.py`)

1.  **Lọc nguồn hợp lệ (Allowlist Filter)**:
    *   Chỉ các bản ghi có `doc_id` thuộc danh sách cho phép (như `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`, `access_control_sop`) được đi tiếp. Các bản ghi lạ hoặc cũ (như `legacy_*`, `invalid_*`) bị đẩy ngay sang Quarantine với lý do `unknown_doc_id`.
2.  **Chuẩn hóa định dạng ngày tháng (`_normalize_effective_date`)**:
    *   Sử dụng regex phân tích các định dạng ngày khác nhau:
        *   ISO Date (`YYYY-MM-DD`) -> Giữ nguyên.
        *   ISO Datetime (`YYYY-MM-DDThh:mm:ss...`) -> Lấy phần ngày `YYYY-MM-DD`.
        *   Sử dụng dấu gạch chéo (`DD/MM/YYYY` hoặc `YYYY/MM/DD`) -> Chuyển về định dạng dấu gạch ngang ISO.
        *   Định dạng ngày Việt Nam (`DD-MM-YYYY`) -> Đảo ngược thứ tự thành `YYYY-MM-DD`.
    *   Nếu trống rỗng -> Quarantine lý do `missing_effective_date`. Nếu không parse được cấu trúc -> Quarantine lý do `invalid_effective_date_format`.
3.  **Kiểm tra phiên bản chính sách cũ (Dynamic Cutoff Validation)**:
    *   Đọc biến môi trường override (ví dụ: `HR_LEAVE_POLICY_CUTOFF_DATE`) hoặc tham chiếu từ `policy_versioning` của Data Contract.
    *   So sánh ngày hiệu lực đã chuẩn hóa với ngày cutoff. Nếu nhỏ hơn -> Quarantine lý do `stale_<doc_id>_effective_date`.
4.  **Làm sạch văn bản (Text Sanitization)**:
    *   Loại bỏ các cụm từ rác sinh ra do xuất lỗi như: `"Nội dung không rõ ràng:"`, hoặc chuỗi dấu chấm than `"!!!"`.
    *   Sử dụng Regex thay thế các khoảng trắng thừa thành dấu cách đơn.
    *   **Rule mới 1: Deduplicate câu trùng (`internal_consecutive_sentence_deduplication`)**: Tách chunk thành các câu bằng regex phân tách dấu câu kết hợp kiểm tra độ dài câu, chỉ giữ lại các câu duy nhất không trùng lặp.
    *   **Rule mới 2: Chuẩn hóa Hotline Extension (`phone_extension_standardization`)**: Định dạng lại các máy lẻ điện thoại từ `ext. <number>` hoặc `ext.<number>` về dạng đồng nhất `extension <number>`.
    *   **Rule mới 3: Enrichment ngoại lệ hoàn tiền (`refund_exception_enrichment`)**: Làm giàu từ khóa cho tài liệu hoàn tiền kỹ thuật số. Chuyển đổi `"Ngoại lệ không được hoàn tiền:"` thành `"Ngoại lệ (các loại sản phẩm bị loại khỏi điều kiện hoàn tiền):"`.
5.  **Ngăn ngừa mâu thuẫn phép năm cũ**:
    *   Cách ly các chunk có `doc_id` là `hr_leave_policy` nhưng văn bản chứa nội dung nghỉ phép `10 ngày` cũ (trong khi quy định mới là 12 ngày) -> Quarantine lý do `stale_hr_policy_text`.
6.  **Khử trùng lặp chunk (Global Chunk Deduplication)**:
    *   Sử dụng `seen_text` set lưu mã băm chữ thường của chunk. Các chunk trùng lặp nội dung 100% chỉ giữ lại bản ghi đầu tiên, các bản ghi sau bị cách ly lý do `duplicate_chunk_text`.
7.  **Sửa lỗi stale window hoàn tiền**:
    *   Với dữ liệu `policy_refund_v4`, nếu nội dung chứa quy định cũ `14 ngày làm việc`, tự động sửa thành `7 ngày làm việc` và thêm tag `[cleaned: stale_refund_window]`.
8.  **Chuẩn hóa thời gian xuất bản (`export_timestamp_normalization`)**:
    *   Đồng bộ hóa dấu `/` thành `-` trong trường `exported_at` để khớp định dạng ISO datetime của Pydantic.
9.  **Bổ sung tiền tố ngữ cảnh (Context Enrichment)**:
    *   Chèn mô tả nguồn vào đầu mỗi chunk (ví dụ: `"Chính sách nghỉ phép nhân sự HR (HR leave policy): "` + text) giúp tăng tính tương đồng cosine và đảm bảo retrieval hoạt động tối ưu.

---

### 2.2. Logic Kiểm Định Chất Lượng (`quality/expectations.py`)

*   **Pydantic Model Schema Validation**:
    *   Định nghĩa Pydantic model:
        ```python
        class CleanedRow(BaseModel):
            chunk_id: str = Field(..., min_length=1)
            doc_id: str = Field(..., min_length=1)
            chunk_text: str = Field(..., min_length=8)
            effective_date: date
            exported_at: datetime
        ```
    *   Chạy qua toàn bộ dòng sạch. Bất kỳ lỗi kiểu dữ liệu hoặc vi phạm ràng buộc nào sẽ được ghi lại chi tiết và ngắt pipeline ngay lập tức (`halt`).
*   **Bộ 12 Quy Tắc Kiểm Định (Expectation Rules)**:
    *   `min_one_row` (halt): Đầu ra phải có ít nhất 1 bản ghi hợp lệ.
    *   `no_empty_doc_id` (halt): Không chấp nhận doc_id trống.
    *   `refund_no_stale_14d_window` (halt): Không được chứa thông tin 14 ngày của chính sách hoàn tiền cũ.
    *   `chunk_min_length_8` (warn): Cảnh báo nếu có chunk siêu ngắn (< 8 ký tự).
    *   `effective_date_iso_yyyy_mm_dd` (halt): Kiểm tra định dạng ngày hiệu lực.
    *   `hr_leave_no_stale_10d_annual` (halt): Không chứa chuỗi thông tin phép năm 10 ngày cũ.
    *   `min_records_per_doc_id` (halt): Đảm bảo toàn bộ danh sách allowed doc_ids đều có ít nhất 1 chunk được làm sạch và embed (tránh mất mát tài liệu).
    *   `no_corrupted_symbols` (halt): Bảo vệ DB khỏi ký tự rác (!!!, lặp từ).
    *   `pydantic_schema_validation` (halt): Kiểm chứng kiểu dữ liệu toàn diện.
    *   `exported_at_iso_format` (halt): Bảo đảm trường export khớp cấu trúc ISO Datetime.
    *   `chunk_max_length_1000` (warn): Cảnh báo nếu chunk quá dài (>1000 ký tự) gây tràn ngữ cảnh vector.
    *   `no_duplicate_chunk_ids` (halt): chunk_id định danh duy nhất.

---

### 2.3. Logic Giám Sát Độ Tươi Dữ Liệu (`monitoring/freshness_check.py`)

SLA Freshness được đo tại 2 ranh giới độc lập để chẩn đoán chính xác nguyên nhân lỗi hệ thống:
1.  **Ingestion SLA Boundary (Độ tuổi dữ liệu nguồn)**:
    *   *Công thức*: `now` - `latest_exported_at` (bản ghi xuất gần nhất).
    *   *Ngưỡng*: tối đa **24.0 giờ**.
    *   *Ý nghĩa*: Đảm bảo dữ liệu trích xuất từ các hệ thống ERP/CRM thượng nguồn (Upstream) không quá cũ.
2.  **Publish SLA Boundary (Độ trễ cập nhật cơ sở dữ liệu)**:
    *   *Công thức*: `now` - `run_timestamp` (thời điểm chạy và xuất bản manifest).
    *   *Ngưỡng*: tối đa **1.0 giờ**.
    *   *Ý nghĩa*: Đảm bảo bộ lập lịch (scheduler/cron-job) chạy pipeline hoạt động đều đặn để đồng bộ cơ sở dữ liệu vector DB.

---

### 2.4. Logic Cập Nhật Cơ Sở Dữ Liệu Vector DB (Idempotency & Pruning)

*   **Upsert Idempotent**: 
    *   Sử dụng mã `chunk_id` cố định duy nhất làm khóa chính. Khi chạy lại pipeline nhiều lần trên cùng dữ liệu, hệ thống tự động cập nhật đè lên bản cũ chứ không chèn thêm dòng mới, tránh phình dữ liệu.
*   **Pruning (Xóa vector mồ côi)**:
    *   Trước khi chèn dữ liệu mới, lấy toàn bộ danh sách `ids` hiện có trong collection Chroma DB. So sánh với danh sách `ids` của run hiện tại để xác định các ID bị loại bỏ (ví dụ: các chunk thuộc tệp bẩn bị đẩy sang quarantine hoặc tài liệu đã bị xóa).
    *   Chạy câu lệnh `col.delete(ids=drop)` để giải phóng không gian và làm sạch DB.

---

## 3. Giao Diện Người Dùng Telemetry Portal (`pipeline_ui.html`)

Hệ thống được trang bị một giao diện HTML5/CSS3/Vanilla JS Light-Mode trực quan hóa toàn diện:

1.  **Interactive Configuration Panel**: Cho phép người dùng chỉnh sửa danh sách allowed doc_ids, thay đổi ngày cutoff trực quan qua giao diện, và bật/tắt động 4 quy tắc làm sạch dữ liệu.
2.  **Horizontal Flow Diagram**: Sử dụng SVG vẽ sơ đồ luồng ngang 4 bước của pipeline, hiển thị trạng thái đang xử lý (`active`) và hoàn thành (`completed`) với các xung động di chuyển trên đường nối.
3.  **Real-time Log Terminal**: Mô phỏng console telemetry của lập trình viên, cho phép lọc logs theo level (`System`, `Success`, `Warnings`, `Errors`), bật/tắt tự động cuộn (Auto-Scroll), dọn dẹp và sao chép log nhanh.
4.  **SVG Telemetry Charts**: Trực quan hóa số liệu phân bố tài liệu sạch qua biểu đồ cột nằm ngang và hiển thị kiểm định chất lượng SLAs.
5.  **Quarantine Inspector**: Khi có hàng bị đẩy vào Quarantine, người dùng có thể bấm **Inspect** để xem chi tiết lý do lỗi cấu trúc kèm theo hiển thị JSON nổi bật lỗi.
6.  **Pydantic Accordion Details**: Trong tab Validation Suite, người dùng có thể nhấp vào bất kỳ Expectation nào để xem mã nguồn assertion logic và kết quả kiểm định chi tiết.
7.  **Simulation Speed Controller**: Tùy chỉnh thanh trượt tốc độ chạy mô phỏng từ Chậm đến Tức thời.

---

## 4. Các Cải Tiến So Với Bản Gốc (Upgrades & Baseline Comparison)

Dưới đây là bảng đối chiếu chi tiết giữa bộ mã nguồn gốc (Baseline) ban đầu và hệ thống sau khi đã được nâng cấp:

| Thành phần (Component) | Bản gốc (Baseline) | Bản nâng cấp (Our Upgraded System) | Ý nghĩa / Lý do cải tiến (Rationale) |
| :--- | :--- | :--- | :--- |
| **Quy Tắc Làm Sạch Dữ Liệu (`cleaning_rules.py`)** | Chỉ chứa các quy tắc làm sạch văn bản và chuẩn hóa ngày tháng cơ bản nhất. Dễ bỏ lọt lỗi lặp từ/lặp câu, không chuẩn hóa hotline máy lẻ, thiếu ngữ cảnh RAG. | Bổ sung 4 quy tắc xử lý chuyên sâu:<br>1. Khử lặp câu liên tiếp trong chunk (`internal_consecutive_sentence_deduplication`) <br>2. Chuẩn hóa máy lẻ hotline (`phone_extension_standardization`) <br>3. Enrich từ khóa hoàn tiền RAG (`refund_exception_enrichment`) <br>4. Chuẩn hóa exported timestamp (`export_timestamp_normalization`). | Giảm nhiễu vector, tối ưu hóa độ tương đồng cosine cho mô hình tìm kiếm RAG và sửa triệt để các câu hỏi góc khó như `gq_d10_02`. |
| **Cấu hình Cutoff Date** | Ngày giới hạn chính sách được hardcode trực tiếp trong mã nguồn Python. | Hỗ trợ nạp ngày cutoff linh hoạt qua các biến môi trường hệ thống (`*_CUTOFF_DATE`) hoặc yaml contract. | Phân tách cấu hình và logic. Người quản trị có thể thay đổi mốc giới hạn phiên bản mà không cần sửa code và tái deploy hệ thống. |
| **Expectation Suite (`expectations.py`)** | Bộ kiểm định đơn giản không xác thực kiểu dữ liệu và cấu trúc chặt chẽ. | Tích hợp **Pydantic Model Validation (`CleanedRow`)** thật. Thêm 4 expectations mới: `pydantic_schema_validation`, `exported_at_iso_format`, `chunk_max_length_1000` (warn) và `no_duplicate_chunk_ids` (halt). | Đảm bảo tính toàn vẹn tuyệt đối của kiểu dữ liệu đầu ra và ngăn chặn data corruption trước khi embedding vào DB. |
| **Freshness Check (`freshness_check.py`)** | Đo lường độ trễ dữ liệu cơ bản ở 1 ranh giới duy nhất. | Đo lường Freshness song song tại **2 boundary độc lập**: Ingestion Boundary (SLA 24h) và Publish Boundary (SLA 1h). | Giúp phân biệt chính xác nguyên nhân dữ liệu cũ: lỗi từ hệ thống thượng nguồn (Upstream) hay do bộ lập lịch pipeline (Scheduler) bị treo. |
| **Vector DB Idempotency & Prune** | Dễ bị phình dữ liệu hoặc sót vector rác khi chạy lại pipeline nhiều lần trên dữ liệu cũ/mới. | Áp dụng Upsert idempotent bằng chunk_id duy nhất và tự động **Prune** xóa sạch các vector cũ không còn tồn tại trong run hiện tại. | Đảm bảo Vector DB luôn phản ánh chính xác 100% tài liệu hiện tại, loại bỏ hoàn toàn các mảnh dữ liệu cũ gây trả lời sai. |
| **Giao Diện Telemetry Portal (`pipeline_ui.html`)** | Giao diện tối đơn giản, bố cục dọc dễ bị vỡ khung hình khi màn hình nhỏ, không có tương tác. | Giao diện Light-Mode cao cấp, thanh luồng ngang trực quan chống vỡ, tích hợp **Simulation Speed Control**, **Granular Log Streaming** từng dòng, **biểu đồ SVG tương tác (Tooltip)**, **popovers mô tả bước** và **Pydantic details inspector**. | Mang lại trải nghiệm quan sát telemetry và debug dữ liệu trực quan, sinh động nhất cho kỹ sư vận hành. |

---

## 5. Hướng Dẫn Vận Hành & Khởi Chạy

### 4.1. Chuẩn Bị Môi Trường
```bash
# Di chuyển vào thư mục lab
cd lab

# Tạo môi trường ảo và kích hoạt
python -m venv .venv
source .venv/bin/activate  # Trên Windows dùng: .venv\Scripts\activate

# Cài đặt thư viện phụ thuộc
pip install -r requirements.txt

# Tạo tệp cấu hình môi trường
copy .env.example .env
```

### 4.2. Chạy Pipeline Chuẩn (Mọi Expectations đều đạt)
```bash
# Chạy pipeline, tự động làm sạch, kiểm tra chất lượng và embedding vào DB
python etl_pipeline.py run
```
*Kết quả*: Exit code `0`, pass toàn bộ Expectations, tạo manifests và cập nhật Chroma DB thành công.

### 4.3. Kiểm Tra Freshness SLA
```bash
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run-id>.json
```

### 4.4. Kiểm Thử Inject Lỗi (Sprint 3)
```bash
# Tắt sửa lỗi refund, bỏ qua xác thực expectations để đẩy dữ liệu lỗi vào DB
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate

# Đo chất lượng retrieval khi dữ liệu bị lỗi
python eval_retrieval.py --out artifacts/eval/after_inject_bad.csv
```

### 4.5. Chạy Chấm Điểm & Kiểm Tra Nhanh
```bash
# Chạy chấm điểm 10 câu hỏi
python grading_run.py --out artifacts/eval/grading_run.jsonl

# Giảng viên kiểm tra định dạng và kết quả
python instructor_quick_check.py
```
