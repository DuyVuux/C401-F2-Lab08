# Data contract — Lab Day 10

> File này mở rộng từ `contracts/data_contract.yaml` — đồng bộ với nhau.  
> **Nhóm:** C401-F2 · **Owner:** Trần Quang Quí · **Cập nhật:** 2026-04-15

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|-------------------|----------------|
| `data/raw/policy_export_dirty.csv` | `load_raw_csv()` — đọc toàn bộ CSV một lần | duplicate chunk_text, missing effective_date, doc_id lạ, encoding lỗi | `quarantine_records` trong log + manifest |
| `data/docs/*.txt` | Tài liệu nguồn (Day 08/09) — không ingest trực tiếp trong Day 10 | stale version (HR 2025 vs 2026), policy conflict (refund 14→7 ngày) | `stale_hr_policy_effective_date`, `refund_no_stale_14d_window` expectation |

**Failure modes đã gặp trên data mẫu (`policy_export_dirty.csv`):**

| chunk | doc_id | Lý do quarantine |
|-------|--------|-----------------|
| 2 | policy_refund_v4 | `duplicate_chunk_text` |
| 5 | policy_refund_v4 | `missing_effective_date` |
| 7 | hr_leave_policy | `stale_hr_policy_effective_date` (2025-01-01 < 2026-01-01) |
| 9 | legacy_catalog_xyz_zzz | `unknown_doc_id` |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Constraint | Ghi chú |
|-----|------|----------|-----------|---------|
| `chunk_id` | string | Có | unique, stable | `sha256(doc_id\|chunk_text\|seq)[:16]` — idempotent |
| `doc_id` | string | Có | thuộc `ALLOWED_DOC_IDS` | policy_refund_v4, sla_p1_2026, it_helpdesk_faq, hr_leave_policy |
| `chunk_text` | string | Có | min 20 ký tự (rule mới) | Baseline min 8; rule mới Bách nâng lên 20 |
| `effective_date` | date ISO | Có | `YYYY-MM-DD` | dd/MM/yyyy được auto-parse; rỗng → quarantine |
| `exported_at` | datetime ISO | Có | parse được bằng `datetime.fromisoformat()` | Rỗng → quarantine (rule mới); `exported_at >= effective_date` bắt buộc |

**ALLOWED_DOC_IDS** (từ `contracts/data_contract.yaml`):
```
policy_refund_v4 · sla_p1_2026 · it_helpdesk_faq · hr_leave_policy
```
Thêm doc mới: phải cập nhật cả `ALLOWED_DOC_IDS` trong `cleaning_rules.py` và `allowed_doc_ids` trong `data_contract.yaml`.

---

## 3. Quy tắc quarantine vs drop

| Reason | Hành động | Có thể merge lại không? |
|--------|-----------|------------------------|
| `unknown_doc_id` | Quarantine | Có — sau khi thêm doc_id vào allowlist + rerun |
| `missing_effective_date` | Quarantine | Có — sau khi fix nguồn data |
| `invalid_effective_date_format` | Quarantine | Có — sau khi chuẩn hoá format ở nguồn |
| `stale_hr_policy_effective_date` | Quarantine | Không tự động — cần xác nhận version policy |
| `missing_chunk_text` / `chunk_text_too_short` | Quarantine | Không — chunk quá ngắn không có nghĩa để embed |
| `duplicate_chunk_text` | Quarantine (giữ bản đầu) | Không — bản giữ lại đã đại diện |
| `missing_exported_at` | Quarantine (rule mới) | Có — sau khi fix export pipeline thêm timestamp |
| `invalid_exported_at_format` | Quarantine (rule mới) | Có — sau khi chuẩn hoá format |
| `exported_before_effective_date` | Quarantine (rule mới) | Không tự động — cần điều tra logic export |

**Quy trình merge lại:** fix nguồn → rerun `python etl_pipeline.py run` → verify `quarantine_records` giảm → không sửa tay CSV.

---

## 4. Phiên bản & canonical

| Policy | Canonical source | Version hiệu lực | Rule bảo vệ |
|--------|-----------------|-----------------|-------------|
| Refund | `data/docs/policy_refund_v4.txt` | v4 từ 2026-02-01 | `refund_no_stale_14d_window` (halt) |
| HR Leave | `data/docs/hr_leave_policy.txt` | 2026 từ 2026-01-01 | `stale_hr_policy_effective_date` (quarantine) |
| SLA P1 | `data/docs/sla_p1_2026.txt` | 2026-01-15 | — |
| IT FAQ | `data/docs/it_helpdesk_faq.txt` | 2026-02-01 | — |

**Cutoff version HR** đọc từ `contracts/data_contract.yaml`:
```yaml
policy_versioning:
  hr_leave_min_effective_date: "2026-01-01"
```
Không hard-code trong `cleaning_rules.py` — thay đổi cutoff chỉ cần sửa YAML.

**Freshness SLA:** 24h từ `latest_exported_at` (đọc từ env `FRESHNESS_SLA_HOURS`, mặc định 24).  
Alert channel: `slack:#data-pipeline-alerts` (từ `data_contract.yaml`).
