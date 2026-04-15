# Báo Cáo Nhóm — Lab Day 10: Data Pipeline & Data Observability

**Tên nhóm:** C401-F2  
**Thành viên:**
| Tên | Vai trò (Day 10) | Sprint |
|-----|------------------|--------|
| Nhữ Gia Bách | Ingestion & Cleaning Owner | Sprint 1 |
| Đoàn Nam Sơn | Quality / Expectation Owner | Sprint 2a |
| Vũ Đức Duy | Embed & Idempotency Owner | Sprint 2b |
| Hoàng Vĩnh Giang | Inject Corruption & Before/After | Sprint 3 |
| Trần Quang Quí | Monitoring / Docs / Report | Sprint 4 |

**Ngày nộp:** 2026-04-15  
**Repo:** https://github.com/DuyVuux/C401-F2-Lab08

---

## 1. Pipeline tổng quan

Nguồn raw: `data/raw/policy_export_dirty.csv` — 10 records mô phỏng export từ hệ thống nội bộ CS + IT Helpdesk, chứa sẵn các lỗi: duplicate, missing date, doc_id lạ, stale HR policy, stale refund window.

**Luồng end-to-end:**
```
policy_export_dirty.csv
  → etl_pipeline.py run          (ingest → clean → validate → embed)
  → artifacts/cleaned/           (6 cleaned records)
  → artifacts/quarantine/        (4 quarantined records)
  → quality/expectations.py      (E1–E9, halt nếu cần)
  → ChromaDB day10_kb            (upsert idempotent + prune)
  → artifacts/manifests/         (run_id, raw/cleaned/quarantine counts)
  → monitoring/freshness_check   (PASS/WARN/FAIL vs SLA 24h)
```

**run_id chính thức:** `sprint2-rules` (`artifacts/manifests/manifest_sprint2-rules.json`)  
**Lệnh một dòng:**
```bash
python etl_pipeline.py run
```

**Số liệu run chính thức:**

| Metric | Giá trị |
|--------|---------|
| `raw_records` | 10 |
| `cleaned_records` | 6 |
| `quarantine_records` | 4 |
| `no_refund_fix` | false |
| `skipped_validate` | false |
| Expectation halt | Không |

---

## 2. Cleaning & expectation

Baseline nhận được có 6 rules (allowlist doc_id, chuẩn hoá effective_date ISO, quarantine HR stale < 2026-01-01, fix refund 14→7 ngày, dedupe chunk_text, quarantine empty chunk_text) và 6 expectations (E1–E6).

**Rules mới thêm (Bách — Sprint 1):**

| Rule | Logic | Quarantine reason |
|------|-------|------------------|
| Rule 7 | `exported_at` rỗng → quarantine | `missing_exported_at` |
| Rule 8 | `exported_at` không parse ISO → quarantine | `invalid_exported_at_format` |
| Rule 9 | `exported_at < effective_date` → quarantine | `exported_before_effective_date` |
| Rule 10 | `chunk_text < 20 ký tự` → quarantine | `chunk_text_too_short` |

**Expectations mới thêm (Sơn — Sprint 2a):**

| Expectation | Severity | Logic |
|------------|----------|-------|
| E7 `exported_at_not_empty` | **warn** | Đảm bảo freshness_check có timestamp đúng |
| E8 `chunk_id_unique` | **halt** | Duplicate chunk_id → silent data loss khi upsert ChromaDB |
| E9 `all_canonical_docs_represented` | **warn** | Tất cả 4 doc canonical phải có ít nhất 1 chunk trong cleaned |

### 2a. Bảng metric_impact

| Rule / Expectation | Clean run (`sprint2-rules`) | Inject run (`inject-bad`) | Chứng cứ |
|--------------------|----------------------------|--------------------------|---------|
| E3 `refund_no_stale_14d_window` | PASS | **FAIL** (violations=1) | log `run_id=inject-bad` |
| E8 `chunk_id_unique` | PASS (0 dup) | PASS (0 dup) | log `run_id=inject-bad` |
| E9 `all_canonical_docs_represented` | PASS (4/4 docs) | PASS (4/4 docs) | log `run_id=inject-bad` |
| `q_refund_window` retrieval | `hits_forbidden=no` ✅ | `hits_forbidden=yes` ❌ | `before_after_eval.csv` vs `eval_inject_bad.csv` |
| `q_leave_version` retrieval | `top1_doc_expected=yes` ✅ | `top1_doc_expected=yes` ✅ | cả 2 eval CSV |

**Ví dụ expectation fail và cách xử lý:**  
Run inject (`--no-refund-fix --skip-validate`): E3 `refund_no_stale_14d_window` FAIL vì chunk "14 ngày làm việc" không bị fix. Pipeline không halt vì `--skip-validate` — đây là inject có chủ đích. Fix: rerun pipeline chuẩn (không flag) → E3 PASS.

---

## 3. Before / after ảnh hưởng retrieval

**Kịch bản inject (Sprint 3 — Giang):**
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/eval_inject_bad.csv
```

**Kết quả định lượng:**

| Câu hỏi | Clean (`before_after_eval.csv`) | Inject (`eval_inject_bad.csv`) | Δ |
|---------|--------------------------------|-------------------------------|---|
| `q_refund_window` | `hits_forbidden=no` | `hits_forbidden=yes` | **Thay đổi** ❌→✅ sau fix |
| `q_p1_sla` | `contains_expected=yes` | `contains_expected=yes` | Không đổi |
| `q_lockout` | `contains_expected=yes` | `contains_expected=yes` | Không đổi |
| `q_leave_version` | `top1_doc_expected=yes` | `top1_doc_expected=yes` | Không đổi |

Inject ảnh hưởng đúng câu mục tiêu (`q_refund_window`) và không làm hỏng các câu khác — chứng minh rule và expectation E3 hoạt động có kiểm soát.

**Merit evidence — `q_leave_version`:**  
Bản HR 2025 (10 ngày phép) bị quarantine do `stale_hr_policy_effective_date` → không vào index → `hits_forbidden=no`, `top1_doc_expected=yes` trên cả 2 scenario.

---

## 4. Freshness & monitoring

SLA freshness: **24 giờ** từ `latest_exported_at` (env `FRESHNESS_SLA_HOURS`, mặc định 24).

```
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_sprint2-rules.json
→ FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": ~120.0, "sla_hours": 24}
```

**Giải thích FAIL:** Data mẫu là snapshot cố định từ 2026-04-10 — hành vi FAIL đúng và có chủ đích. Trong production: trigger alert `slack:#data-pipeline-alerts` → on-call rerun pipeline với data mới.

Hai boundary freshness: (1) `exported_at` trong record (nguồn data) và (2) `run_timestamp` trong manifest (khi embed hoàn thành).

---

## 5. Liên hệ Day 09

Day 10 dùng collection `day10_kb` — tách biệt với `rag_lab` / `day09_docs` của Day 09 để không ảnh hưởng grading Day 09 đang chạy song song. Nếu muốn Day 09 multi-agent dùng data sạch của Day 10: đổi `CHROMA_COLLECTION=day10_kb` trong `.env` của Day 09, không cần sửa code.

---

## 6. Rủi ro còn lại & việc chưa làm

- Rules mới (exported_at) không tăng `quarantine_records` trên data mẫu vì data mẫu đã hợp lệ — tác động chứng minh qua inject Sprint 3 (E3 FAIL).
- LLM-judge chưa tích hợp — eval dùng keyword matching, không đo answer quality thực sự.
- `grading_run.jsonl` sẽ chạy sau 17:00 khi giảng viên public `grading_questions.json`.
