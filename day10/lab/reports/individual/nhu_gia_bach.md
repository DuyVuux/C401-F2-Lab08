# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nhữ Gia Bách  
**Vai trò:** ETL Architect / Ingestion / Cleaning  
**Ngày nộp:** 15/04/2026  
**Độ dài yêu cầu:** **400–650 từ**

---

> Viết **"tôi"**, đính kèm **run_id**, **tên file**, **đoạn log** hoặc **dòng CSV** thật. Nếu làm phần clean/expectation, nêu **một số liệu thay đổi** khớp bảng `metric_impact` của nhóm.

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

Tôi chịu trách nhiệm cải thiện lớp làm sạch trong `transform/cleaning_rules.py` và đảm bảo pipeline chạy trơn từ ingest → clean → embed trong `etl_pipeline.py`. Cụ thể tôi thêm ba rule mới: (1) loại chunk quá ngắn (<20 ký tự) để tránh đưa vào vector store, (2) kiểm tra `exported_at` không rỗng và parse được ISO trước khi clean, (3) từ chối record nếu `exported_at` trước `effective_date`. Những thay đổi này giữ `cleaned_sprint2-rules.csv` (run_id `sprint2-rules`) chỉ chứa records có timestamps chuẩn. Tôi cũng thông báo cho Duy rằng `cmd_embed_internal` sẽ dùng file cleaned mới và đã quan sát log `embed_prune_removed=1` để đảm bảo idempotency cho `day10_kb`.

## 2. Một quyết định kỹ thuật (100–150 từ)

Quyết định quan trọng là đặt `exported_at` không hợp lệ vào quarantine thay vì chỉ warn — tức rule mới halt thông tin sai thay vì để downstream dùng timestamp giả. Khi inject data thiếu `exported_at` thì `quarantine_records` tăng (từ 0 lên 4, theo run `sprint2-rules`), cho phép ghi `metric_impact` rõ ràng là số record bị cách ly nhờ rule này. Đồng thời tôi giữ `cleaned` chỉ chứa `effective_date`/`exported_at` chuẩn để expectation `exported_at_not_empty` sau này có cơ hội fail và dẫn đường cho Sprint 3. Thêm vào đó, `cmd_embed_internal` prune các chunk_id không còn trong run mới (`prev_ids - ids`), nên vector cũ (ví dụ chunk stale `policy_refund_v3`) không thể khiến top-k chứa `14 ngày` sau khi clean lại.

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

Triệu chứng: run đầu tiên `2026-04-15T05-29Z` thành công đến phần log expectation nhưng embed chết với lỗi `nodename nor servname provided` khi tải model `all-MiniLM-L6-v2`. Metric thể hiện là pipeline exit code 1 và không tạo manifest (log chỉ tới `freshness_check`). Sau khi xác định nguyên nhân là mạng chưa mở tới `huggingface.co`, tôi báo để cấp phép download và rerun `sprint2-rules`; hiện tại pipeline in ra `embed_upsert count=6 collection=day10_kb` rồi ghi manifest với run_id tương ứng. Vấn đề HF warning (`HF_TOKEN` chưa set) vẫn có thể cải thiện sau nếu cần rate limit cao hơn, nhưng đã đủ để hoàn tất sprint clean + embed.

## 4. Bằng chứng trước / sau (80–120 từ)

**Before (run_id `2026-04-15T05-29Z`):** log dừng sau `freshness_check=FAIL ... reason=freshness_sla_exceeded` vì embed chưa chạy, và message `Warning: You are sending unauthenticated requests to the HF Hub...` xuất hiện trước khi process crash.  
**After (run_id `sprint2-rules`):** log ghi `expectation[refund_no_stale_14d_window] OK (halt) :: violations=0` tiếp theo `embed_upsert count=6 collection=day10_kb` và `manifest_written=artifacts/manifests/manifest_sprint2-rules.json`, chứng tỏ pipeline chạy end-to-end. Dữ liệu clean/quarantine mới (+ `cleaned_records=6`, `quarantine_records=4`) là bằng chứng cấu trúc metric tương ứng bảng `metric_impact` chung.

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm hai giờ, tôi sẽ chuyển `contracts/data_contract.yaml` thành nguồn duy nhất cho cutoff HR (cột `hr_leave_policy#effective_date_threshold`) và đọc giá trị đó trong `clean_rows`. Điều này vừa tránh hard-code ngày `2026-01-01`, vừa cho phép QA/monitoring điều chỉnh cutoff mà không cần redeploy Python, hỗ trợ rõ ràng hơn cho metric `stale_hr_policy_effective_date`.
