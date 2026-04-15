# Phân Công Công Việc — Lab Day 10: Data Pipeline & Data Observability

**Nhóm:** C401-F2  
**Deadline code + artifacts:** 18:00 hôm nay  
**Deadline report:** Sau 18:00 (nếu được phép)

> **Baseline đã có sẵn:** `etl_pipeline.py`, `transform/cleaning_rules.py` (6 rules), `quality/expectations.py` (6 expectations), `monitoring/freshness_check.py`, `eval_retrieval.py`, `grading_run.py`.  
> **Pipeline đã chạy 1 lần:** `run_id=2026-04-15T05-30Z` → 10 raw → 6 cleaned → 4 quarantine.  
> **Nhiệm vụ nhóm:** thêm rules/expectations mới + điền docs + inject + report. Không tạo file ngoài cấu trúc hiện có.

---

## Tổng quan phân vai

| Thành viên | Vai trò | Sprint | Files phụ trách |
|------------|---------|--------|-----------------|
| **Nhữ Gia Bách** | Ingestion Owner | 1 → 2 | `transform/cleaning_rules.py` — thêm ≥3 rule mới |
| **Đoàn Nam Sơn** | Cleaning & Quality Owner | 2 | `quality/expectations.py` — thêm ≥2 expectation mới |
| **Vũ Đức Duy** | Embed & Idempotency Owner | 2 | Verify upsert/prune, chạy `eval_retrieval.py` (baseline) |
| **Hoàng Vĩnh Giang** | Inject & Before/After | 3 | Chạy inject CLI, tạo 2 file eval CSV, điền bảng `metric_impact` |
| **Trần Quang Quí** | Monitoring / Docs / Report | 4 | 3 docs + quality report + group report + individual reports |

> Ai xong sớm → hỗ trợ Sprint tiếp theo.

---

## Dependency

```
Sprint 1 — Bách: thêm ≥3 rule mới → push cleaning_rules.py
    │
    ├──► Sprint 2a — Sơn: thêm ≥2 expectation mới → push expectations.py
    │
    └──► Sprint 2b — Duy: python etl_pipeline.py run → xác nhận embed OK + eval baseline
              │
              └──► Sprint 3 — Giang: inject (--no-refund-fix) → 2 eval CSV → bảng metric_impact
                        │
                        └──► Sprint 4 — Quí: 3 docs + quality report + group/individual reports
```

**Blocking:** Duy và Sơn chờ Bách push rule mới xong mới rerun pipeline để có số liệu thật.

---

## Sprint 1 — Nhữ Gia Bách: Thêm ≥3 rule mới vào `cleaning_rules.py`

Pipeline đã chạy baseline (6 rules). Bách cần thêm ≥3 rule mới vào hàm `clean_rows()` trong `transform/cleaning_rules.py`. **Mỗi rule phải có tác động đo được** (thay đổi `quarantine_records` hoặc `cleaned_records`) để tránh bị trừ điểm "trivial".

### Gợi ý 3 rule có tác động rõ trên bộ mẫu

**Rule 7 — Strip BOM và kiểm soát encoding:**
```python
# Thêm vào đầu hàm clean_rows(), sau khi lấy text:
# Rule 7: Strip BOM và ký tự control không in được (encoding artifact)
import unicodedata
fixed_text = text.replace("\ufeff", "").replace("\ufffd", "")
# Nếu sau strip còn ký tự replacement → quarantine
if "\ufffd" in text:
    quarantine.append({**raw, "reason": "encoding_replacement_char"})
    continue
text = fixed_text
```

**Rule 8 — Tối thiểu độ dài chunk_text (reject cứng):**
```python
# Rule 8: chunk_text < 20 ký tự sau strip → quarantine (quá ngắn để embed có nghĩa)
if len(text.strip()) < 20:
    quarantine.append({**raw, "reason": "chunk_text_too_short"})
    continue
```

**Rule 9 — Normalize dấu gạch ngang/số trong ngày (locale):**
```python
# Rule 9: Chuẩn hoá exported_at — chấp nhận rỗng nhưng log warn nếu không parse được
# (metric_impact: không thay đổi quarantine nhưng chuẩn hoá field trước khi write)
from datetime import datetime
_exported_at = raw.get("exported_at", "").strip()
if _exported_at:
    try:
        datetime.fromisoformat(_exported_at)
    except ValueError:
        _exported_at = ""  # reset về rỗng nếu không parse được
```

> **Quan trọng:** Sau khi thêm rule, rerun `python etl_pipeline.py run --run-id sprint2-rules` và ghi lại delta `quarantine_records` để Sơn/Giang dùng cho bảng `metric_impact`.

### DoD Sprint 1

- [ ] `cleaning_rules.py` có ≥3 rule mới với comment/docstring rõ tên rule
- [ ] `python etl_pipeline.py run --run-id sprint2-rules` exit 0
- [ ] Log có số `quarantine_records` khác với run baseline (hoặc ghi lý do nếu không đổi)
- [ ] Push lên repo

---

## Sprint 2a — Đoàn Nam Sơn: Thêm ≥2 expectation mới vào `expectations.py`

Baseline đã có E1–E6. Thêm ≥2 expectation mới với phân biệt `warn` / `halt` rõ ràng.

### Gợi ý 2 expectation có tác động đo được

Thêm vào cuối hàm `run_expectations()` trong `quality/expectations.py`, trước dòng `halt = any(...)`:

```python
# E7: exported_at không rỗng — warn (không halt vì field ít quan trọng hơn)
no_exported = [r for r in cleaned_rows if not (r.get("exported_at") or "").strip()]
ok7 = len(no_exported) == 0
results.append(
    ExpectationResult(
        "exported_at_not_empty",
        ok7,
        "warn",
        f"missing_exported_at={len(no_exported)}",
    )
)

# E8: chunk_id phải unique (idempotency guard — nếu logic hash lỗi sẽ fail ngay)
chunk_ids = [r.get("chunk_id", "") for r in cleaned_rows]
dup_ids = len(chunk_ids) - len(set(chunk_ids))
ok8 = dup_ids == 0
results.append(
    ExpectationResult(
        "chunk_id_unique",
        ok8,
        "halt",
        f"duplicate_chunk_ids={dup_ids}",
    )
)
```

> **Chứng minh không trivial:** chạy `python etl_pipeline.py run --run-id test-e7-e8` và dán dòng log `expectation[exported_at_not_empty]` / `expectation[chunk_id_unique]` vào bảng `metric_impact` trong group report.

### DoD Sprint 2a

- [ ] `expectations.py` có ≥2 expectation mới, rõ severity `warn`/`halt`
- [ ] Ít nhất 1 trong 2 expectation có thể fail khi inject (để demo Sprint 3)
- [ ] Push lên repo

---

## Sprint 2b — Vũ Đức Duy: Verify embed + chạy eval baseline

Embed đã nằm trong `etl_pipeline.py` (`cmd_embed_internal`). Duy không cần tạo file mới — tập trung verify pipeline chạy đúng và sinh eval baseline.

### Việc cần làm

```bash
# 1. Chạy pipeline chuẩn sau khi Bách push rule mới
python etl_pipeline.py run --run-id clean-baseline

# 2. Kiểm tra collection day10_kb
python -c "
import chromadb
c = chromadb.PersistentClient('./chroma_db')
col = c.get_collection('day10_kb')
print('count:', col.count())
print('sample:', col.peek(1)['metadatas'])
"

# 3. Chạy eval baseline (TRƯỚC inject — lưu kết quả này)
python eval_retrieval.py --out artifacts/eval/before_after_eval.csv
cat artifacts/eval/before_after_eval.csv
```

**Kết quả mong đợi sau clean-baseline:**
- `q_refund_window`: `contains_expected=yes`, `hits_forbidden=no` (chunk "14 ngày" đã bị fix)
- `q_p1_sla`: `contains_expected=yes`
- `q_lockout`: `contains_expected=yes`
- `q_leave_version`: `contains_expected=yes` (12 ngày), `hits_forbidden=no` (10 ngày đã quarantine), `top1_doc_expected=yes`

**Verify idempotency:**
```bash
# Chạy 2 lần — collection count không tăng
python etl_pipeline.py run --run-id idempotent-test
python -c "import chromadb; c=chromadb.PersistentClient('./chroma_db'); print(c.get_collection('day10_kb').count())"
```

### DoD Sprint 2b

- [ ] `artifacts/eval/before_after_eval.csv` tồn tại với 4 dòng (4 test questions)
- [ ] Tất cả 4 câu `contains_expected=yes`, `hits_forbidden=no`
- [ ] Chạy 2 lần không tăng số chunk trong collection (idempotent)
- [ ] Ghi chú kết quả cho Giang dùng làm "before" trong Sprint 3

---

## Sprint 3 — Hoàng Vĩnh Giang: Inject Corruption + Before/After Evidence

Inject bằng CLI flag — **không cần tạo file Python mới**. Giang cần 2 file eval CSV để so sánh.

### Quy trình inject

```bash
# BƯỚC 1: Lưu eval CLEAN (Duy đã làm ở Sprint 2b — đây là "after clean")
# File: artifacts/eval/before_after_eval.csv  ← đây là CLEAN (sau fix)

# BƯỚC 2: Inject corruption — không fix refund 14→7, bỏ qua halt
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate

# BƯỚC 3: Eval sau inject (đây là "before fix" / dirty)
python eval_retrieval.py --out artifacts/eval/eval_inject_bad.csv
cat artifacts/eval/eval_inject_bad.csv

# BƯỚC 4: So sánh 2 file
# artifacts/eval/before_after_eval.csv  → clean pipeline (hits_forbidden=no)
# artifacts/eval/eval_inject_bad.csv    → inject dirty  (hits_forbidden=yes trên q_refund_window)
```

**Kết quả mong đợi sau inject:**
- `q_refund_window`: `hits_forbidden=yes` (chunk "14 ngày làm việc" xuất hiện trong top-k)
- `q_leave_version`: `hits_forbidden` có thể thay đổi nếu inject thêm

### Điền bảng `metric_impact` (paste vào `reports/group_report.md` mục 2a)

| Rule / Expectation | Before inject | After inject | Chứng cứ |
|--------------------|--------------|--------------|-----------|
| `refund_no_stale_14d_window` (E3) | PASS | FAIL (violations=1) | log `run_id=inject-bad` |
| `q_refund_window` retrieval | `hits_forbidden=no` | `hits_forbidden=yes` | `eval_inject_bad.csv` |
| `chunk_id_unique` (E8 — nếu Sơn thêm) | PASS | PASS | log `run_id=inject-bad` |

> Thêm dòng cho rule mới của Bách nếu inject tác động.

### DoD Sprint 3

- [ ] `artifacts/eval/eval_inject_bad.csv` tồn tại — `q_refund_window` có `hits_forbidden=yes`
- [ ] `artifacts/eval/before_after_eval.csv` (clean) và `eval_inject_bad.csv` (dirty) — 2 file để compare
- [ ] Bảng `metric_impact` điền xong (ít nhất 3 dòng) — paste vào group report cho Quí
- [ ] `artifacts/manifests/manifest_inject-bad.json` tồn tại

---

## Sprint 4 — Trần Quang Quí: Monitoring + Docs + Reports

**Dependency:** Chờ Duy push eval baseline + Giang push bảng metric_impact.

### Việc 1: Freshness check

```bash
# Chạy với manifest clean run gần nhất
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_clean-baseline.json
```

> **Lưu ý:** Freshness sẽ ra `FAIL` vì `latest_exported_at=2026-04-10T08:00:00` (5 ngày trước). Đây là hành vi đúng — giải thích trong runbook: SLA 24h áp cho data snapshot, không phải pipeline run. Có thể rerun với `exported_at` mới hơn hoặc giải thích nhất quán trong docs.

### Việc 2: Điền `docs/pipeline_architecture.md`

```markdown
## 1. Sơ đồ luồng

data/raw/policy_export_dirty.csv
    │
    ▼  etl_pipeline.py run
transform/cleaning_rules.py ──► artifacts/cleaned/cleaned_<run_id>.csv
                             ──► artifacts/quarantine/quarantine_<run_id>.csv
    │
    ▼  quality/expectations.py (halt nếu fail)
    │
    ▼  cmd_embed_internal() — upsert chunk_id → ChromaDB day10_kb
                             (prune id cũ không còn trong cleaned)
    │
    ▼  artifacts/manifests/manifest_<run_id>.json
    │
    ▼  monitoring/freshness_check.py ← đo latest_exported_at vs now

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Owner |
|------------|-------|--------|-------|
| Ingest | policy_export_dirty.csv | rows list | Nhữ Gia Bách |
| Transform | rows list | cleaned[], quarantine[] | Nhữ Gia Bách |
| Quality | cleaned[] | ExpectationResult[], halt | Đoàn Nam Sơn |
| Embed | cleaned CSV | ChromaDB day10_kb (upsert) | Vũ Đức Duy |
| Monitor | manifest JSON | PASS/WARN/FAIL + age_hours | Trần Quang Quí |

## 3. Idempotency & rerun
Embed dùng col.upsert(ids=[chunk_id], ...) + prune id thừa sau publish.
Rerun 2 lần: collection count không đổi (verified Sprint 2b).
chunk_id = sha256(doc_id|chunk_text|seq)[:16] — stable theo nội dung.

## 4. Liên hệ Day 09
Day 10 dùng collection day10_kb (tách với rag_lab / day09_docs của Day 09).
Lý do tách: Day 10 clean theo contract mới; Day 09 giữ nguyên để không ảnh hưởng grading cũ.
Nếu muốn Day 09 agent dùng data sạch: đổi CHROMA_COLLECTION=day10_kb trong .env.

## 5. Rủi ro đã biết
- freshness_check FAIL trên data mẫu (exported_at=2026-04-10, SLA 24h) — đã ghi runbook
- chunk_text ngắn không lọc được ở baseline (Rule 8 mới fix)
```

### Việc 3: Điền `docs/data_contract.md`

```markdown
## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| policy_export_dirty.csv | load_raw_csv() | missing date, encoding lỗi, doc_id lạ | quarantine_records trong log |
| data/docs/*.txt | (Day 09 retrieval) | stale version, encoding | effective_date < 2026-01-01 |

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Ghi chú |
|-----|------|----------|---------|
| chunk_id | string | Có | sha256(doc_id|chunk_text|seq)[:16] — stable |
| doc_id | string | Có | Phải thuộc ALLOWED_DOC_IDS |
| chunk_text | string | Có | min 8 ký tự (baseline), min 20 ký tự (Rule 8 mới) |
| effective_date | date ISO | Có | YYYY-MM-DD; dd/MM/yyyy được parse tự động |
| exported_at | datetime | Có | ISO 8601 |

## 3. Quy tắc quarantine vs drop
Quarantine: unknown_doc_id, missing_effective_date, invalid_effective_date_format,
            stale_hr_policy_effective_date, missing_chunk_text, duplicate_chunk_text,
            encoding_replacement_char (Rule 7), chunk_text_too_short (Rule 8)
Merge lại: chỉ sau khi fix nguồn gốc + rerun pipeline — không sửa tay CSV.

## 4. Phiên bản & canonical
policy_refund_v4: contracts/data_contract.yaml → allowed_doc_ids
hr_leave_policy: effective_date >= 2026-01-01 (policy_versioning.hr_leave_min_effective_date)
SLA freshness: 24h từ latest_exported_at (đọc từ FRESHNESS_SLA_HOURS env hoặc mặc định)
```

### Việc 4: Điền `docs/runbook.md`

```markdown
## Symptom
Agent trả lời "14 ngày" thay vì "7 ngày" cho câu hỏi hoàn tiền.
Hoặc: agent trả lời "10 ngày phép năm" thay vì "12 ngày" cho chính sách HR 2026.

## Detection
- eval_retrieval.py → hits_forbidden=yes trên q_refund_window
- expectation[refund_no_stale_14d_window] FAIL trong log
- freshness_check FAIL (data > 24h chưa cập nhật)

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1 | Xem artifacts/manifests/*.json mới nhất | no_refund_fix=false? skipped_validate=false? |
| 2 | Xem artifacts/quarantine/*.csv | Dòng "14 ngày" có trong quarantine không? |
| 3 | python eval_retrieval.py --out /tmp/check.csv | hits_forbidden=yes → embed còn chunk stale |
| 4 | Kiểm tra collection: col.peek() | chunk_text có "14 ngày làm việc" không bị prune? |

## Mitigation
python etl_pipeline.py run --run-id hotfix-$(date +%H%M)
python eval_retrieval.py --out artifacts/eval/verify_hotfix.csv
# Xác nhận hits_forbidden=no trước khi thông báo fix xong

## Prevention
- Thêm expectation E3 halt → pipeline không embed nếu còn chunk stale
- Alert freshness: FRESHNESS_SLA_HOURS=24 trong .env (kết nối sang Day 11 guardrails)
- Sau mỗi update policy_refund_v4: rerun pipeline + chạy eval_retrieval.py tự động
```

### Việc 5: Điền `docs/quality_report_template.md` → `docs/quality_report.md`

Copy template và điền số thật từ `manifest_clean-baseline.json`:

```
run_id: clean-baseline
raw_records: 10, cleaned_records: 6, quarantine_records: 4
Expectation halt: No (tất cả pass sau clean)
Before/after: xem artifacts/eval/ (2 file CSV)
Freshness: FAIL — age=5d, SLA=24h (giải thích: data snapshot cũ từ 2026-04-10)
```

### Việc 6: Điền `reports/group_report.md`

Điền đủ 6 mục theo template. Quan trọng nhất:
- Mục 2a: bảng `metric_impact` (lấy từ Giang)
- Mục 3: before/after dẫn link 2 file CSV
- Mục 4: freshness FAIL + giải thích

### Việc 7: Individual reports

Mỗi người tự viết `reports/individual/[ten].md` theo template (400–650 từ, 5 mục):
1. Phần phụ trách cụ thể (file + function/rule)
2. 1 quyết định kỹ thuật (warn vs halt, idempotency, freshness SLA)
3. 1 sự cố / anomaly phát hiện + fix + evidence
4. Before/after (trích log hoặc CSV)
5. Cải tiến 2h

### DoD Sprint 4

- [ ] `docs/pipeline_architecture.md` — sơ đồ + bảng component + idempotency + liên hệ Day 09
- [ ] `docs/data_contract.md` — source map (≥2 nguồn) + schema + quarantine rules + canonical
- [ ] `docs/runbook.md` — đủ 5 mục: Symptom → Detection → Diagnosis → Mitigation → Prevention
- [ ] `docs/quality_report.md` (hoặc điền `quality_report_template.md`) — run_id thật + số liệu
- [ ] `reports/group_report.md` — có bảng metric_impact, dẫn 2 file eval CSV, freshness giải thích
- [ ] 5 individual reports commit xong
- [ ] Chạy `grading_run.py` sau 17:00 → `artifacts/eval/grading_run.jsonl` (3 dòng gq_d10_01..03)

---

## Checklist nộp bài (18:00)

- [ ] `python etl_pipeline.py run` exit 0 (run chính thức, không `--skip-validate`)
- [ ] `cleaning_rules.py` có ≥3 rule mới so với baseline
- [ ] `expectations.py` có ≥2 expectation mới so với baseline
- [ ] `artifacts/cleaned/`, `artifacts/quarantine/`, `artifacts/manifests/` — ít nhất 1 run clean
- [ ] `artifacts/eval/before_after_eval.csv` (clean) + `artifacts/eval/eval_inject_bad.csv` (inject)
- [ ] `artifacts/eval/grading_run.jsonl` — 3 dòng `gq_d10_01`, `gq_d10_02`, `gq_d10_03`
- [ ] 3 docs điền đầy đủ (không còn placeholder `___`)
- [ ] `reports/group_report.md` có bảng `metric_impact`
- [ ] 5 individual reports
- [ ] `.gitignore` không commit: `chroma_db/`, `.env`, `__pycache__/`, `*.pyc`
- [ ] Không commit `artifacts/logs/` (log test) — chỉ commit manifests/eval/quarantine/cleaned

---

## Lưu ý kỹ thuật

1. **Không tạo file ngoài cấu trúc hiện có** — mọi thứ đã có entrypoint; chỉ mở rộng `cleaning_rules.py` và `expectations.py`.
2. **Inject bằng CLI flag** — `--no-refund-fix --skip-validate`, không cần script riêng.
3. **Idempotency** — baseline đã dùng `col.upsert()` + prune. Duy chỉ cần verify, không cần sửa.
4. **Freshness FAIL là hành vi đúng** trên data mẫu (`exported_at=2026-04-10`) — giải thích nhất quán trong runbook.
5. **Collection name:** `day10_kb` (không phải `day10_docs` hay `rag_lab`).
6. **grading_run.py** cần file `data/grading_questions.json` — xem `SCORING.md`, file có thể public sau 17:00.
