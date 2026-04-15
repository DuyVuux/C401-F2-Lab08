# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Trần Quang Quí  
**Vai trò:** Monitoring / Docs / Report — Sprint 4  
**Ngày nộp:** 2026-04-15

---

## 1. Tôi phụ trách phần nào?

**File / module:**

- `monitoring/freshness_check.py` — đọc `latest_exported_at` từ manifest, so sánh với `now`, trả về PASS/WARN/FAIL theo SLA 24h
- `docs/pipeline_architecture.md` — sơ đồ ASCII toàn bộ luồng, bảng ranh giới component, idempotency, liên hệ Day 09
- `docs/data_contract.md` — source map 2 nguồn, schema cleaned với constraint, bảng quarantine reasons, canonical sources
- `docs/runbook.md` — 5 mục Symptom → Detection → Diagnosis → Mitigation → Prevention
- `docs/quality_report.md` — số liệu thật từ `manifest_sprint2-rules.json`
- `reports/group_report.md` — tổng hợp toàn nhóm, bảng metric_impact, before/after

**Kết nối với thành viên khác:**  
Tôi phụ thuộc vào output của tất cả sprint trước — cần `manifest_sprint2-rules.json` (Bách), log expectations (Sơn), `before_after_eval.csv` (Duy), `eval_inject_bad.csv` (Giang) để điền số liệu thật vào docs. Docs của tôi là deliverable cuối cùng phản ánh kết quả của cả pipeline.

**Bằng chứng:** commit `9b19ac2` (4 docs), commit cuối (group_report + individual report).

---

## 2. Một quyết định kỹ thuật

**Quyết định: giải thích freshness FAIL thay vì sửa để PASS.**

`monitoring/freshness_check.py` đọc `latest_exported_at=2026-04-10T08:00:00` từ manifest → age ≈ 120h → **FAIL** (SLA 24h). Có 2 lựa chọn:

1. Tăng `FRESHNESS_SLA_HOURS` lên 200h để PASS trên data mẫu
2. Giữ FAIL, giải thích nhất quán trong runbook

Tôi chọn **cách 2** — giữ FAIL và ghi rõ trong `docs/runbook.md` và `docs/quality_report.md`: SLA 24h áp cho production data, không phải data lab; data mẫu là snapshot cố định từ 2026-04-10 để demo monitoring. SCORING.md cũng ghi rõ: "FAIL là hợp lý — miễn giải thích nhất quán."

**Trade-off:** Freshness FAIL trông như lỗi khi nhìn lướt — nhưng đây đúng là giá trị của observability: hệ thống phát hiện data stale trước khi user thấy câu trả lời sai. Giả PASS sẽ che đi chính tính năng cần demo.

---

## 3. Một lỗi đã xử lý

**Lỗi: `embed_pipeline.py` của Duy đọc file sai và upsert vào collection sai.**

Sau khi Duy push `transform/embed_pipeline.py` (commit `2b92277`), tôi review và phát hiện 3 vấn đề:

1. **File sai:** đọc `artifacts/cleaned_records.jsonl` — file này không tồn tại; pipeline của Bách xuất ra `artifacts/cleaned/cleaned_<run_id>.csv`
2. **Collection sai:** dùng `day10_docs` thay vì `day10_kb` — grading_run.py và eval_retrieval.py query `day10_kb`, nên data Duy embed sẽ không được tìm thấy
3. **Thiếu prune:** không xóa chunk_id cũ → rerun 2 lần sẽ phình collection

**Fix:** sửa `embed_pipeline.py` để tự tìm CSV mới nhất trong `artifacts/cleaned/`, đổi collection về `day10_kb`, thêm prune logic (commit `15f2b93`).

**Phát hiện bằng cách nào:** đọc `etl_pipeline.py` của Bách và `grading_run.py` để biết collection name thật — không cần chạy thử.

---

## 4. Bằng chứng trước / sau

**Before (inject run `inject-bad` — `eval_inject_bad.csv`):**
```
q_refund_window,...,hits_forbidden=yes   ← chunk "14 ngày làm việc" vào index
q_leave_version,...,top1_doc_expected=yes
```

**After (clean run `sprint2-rules` — `before_after_eval.csv`):**
```
q_refund_window,...,hits_forbidden=no    ← rule fix 14→7 + E3 halt loại chunk stale
q_leave_version,...,top1_doc_expected=yes
```

`run_id=sprint2-rules`: 10 raw → 6 cleaned → 4 quarantine. Expectation E3 `refund_no_stale_14d_window` PASS. Chunk "14 ngày làm việc" bị fix thành "7 ngày làm việc [cleaned: stale_refund_window]" trước khi embed.

---

## 5. Cải tiến tiếp theo

Nếu có thêm 2 giờ: implement **freshness check ở 2 boundary rõ ràng** — hiện tại `freshness_check.py` chỉ đo `latest_exported_at` (ingest boundary). Tôi sẽ thêm đo `run_timestamp` trong manifest (publish boundary) và log delta giữa 2 boundary để phát hiện pipeline latency cao bất thường (ví dụ: embed mất 3h sau khi ingest xong → tín hiệu ChromaDB chậm). Đây là evidence cho Distinction theo SCORING.md bonus (b): "freshness đo 2 boundary có log minh chứng".
