# Quality report — Lab Day 10

**Nhóm:** C401-F2  
**run_id:** `sprint2-rules`  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Giá trị | Ghi chú |
|--------|---------|---------|
| `raw_records` | 10 | `data/raw/policy_export_dirty.csv` |
| `cleaned_records` | 6 | Sau toàn bộ cleaning rules |
| `quarantine_records` | 4 | Xem bảng chi tiết bên dưới |
| Expectation halt? | **Không** | Tất cả 6 expectation baseline PASS |
| `no_refund_fix` | false | Rule fix 14→7 ngày đã áp dụng |
| `skipped_validate` | false | Run chuẩn, không bypass |
| `latest_exported_at` | 2026-04-10T08:00:00 | Data mẫu |
| Freshness status | **FAIL** | age ≈ 120h > SLA 24h (xem mục 3) |

**4 records bị quarantine:**

| chunk | doc_id | Reason |
|-------|--------|--------|
| 2 | policy_refund_v4 | `duplicate_chunk_text` |
| 5 | policy_refund_v4 | `missing_effective_date` |
| 7 | hr_leave_policy | `stale_hr_policy_effective_date` (2025-01-01 < cutoff 2026-01-01) |
| 9 | legacy_catalog_xyz_zzz | `unknown_doc_id` |

---

## 2. Before / after retrieval

> Artifact: `artifacts/eval/before_after_eval.csv` (Sprint 2b — Duy) và `artifacts/eval/eval_inject_bad.csv` (Sprint 3 — Giang).

**Câu then chốt: `q_refund_window`**

| Scenario | `contains_expected` | `hits_forbidden` | Ghi chú |
|----------|-------------------|-----------------|---------|
| Inject (`--no-refund-fix`) | yes | **yes** | Chunk "14 ngày làm việc" vẫn trong index |
| Clean (`sprint2-rules`) | yes | **no** | Rule fix 14→7 + expectation E3 halt đảm bảo |

**Merit: `q_leave_version`**

| Scenario | `contains_expected` | `hits_forbidden` | `top1_doc_expected` |
|----------|-------------------|-----------------|-------------------|
| Inject | — | — | — |
| Clean | yes (12 ngày) | no (10 ngày quarantine) | yes (hr_leave_policy) |

Bản HR 2025 (10 ngày) bị quarantine do `stale_hr_policy_effective_date` → không vào index → agent trả lời đúng version 2026.

---

## 3. Freshness & monitor

```
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_sprint2-rules.json
→ FAIL {"latest_exported_at": "2026-04-10T08:00:00", "age_hours": ~120, "sla_hours": 24}
```

**Giải thích:** Data mẫu là snapshot cũ từ 2026-04-10 — SLA 24h áp cho production data, không phải data lab. Hành vi FAIL là đúng và có chủ đích để demo monitoring. Trong production: trigger alert `slack:#data-pipeline-alerts` và rerun pipeline với data mới từ nguồn.

---

## 4. Corruption inject (Sprint 3)

Inject bằng CLI flag — không sửa code:
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
python eval_retrieval.py --out artifacts/eval/eval_inject_bad.csv
```

**Kết quả inject:** chunk "14 ngày làm việc" không bị fix → vào index → `q_refund_window` trả về `hits_forbidden=yes`.  
**Kết quả clean:** rule fix 14→7 áp dụng + expectation E3 halt guard → `hits_forbidden=no`.

> Xem chi tiết bảng `metric_impact` trong `reports/group_report.md` mục 2a.

---

## 5. Hạn chế & việc chưa làm

- Rule mới của Bách (exported_at validation, chunk_text_too_short) không tăng `quarantine_records` trên data mẫu vì data mẫu đã hợp lệ — tác động được chứng minh qua kịch bản inject trong Sprint 3.
- Expectation E7–E8 (Sơn, Sprint 2a) chưa commit tại thời điểm report này — sẽ bổ sung sau khi Sơn push.
- LLM-judge chưa tích hợp — confidence đo bằng keyword matching, không phải answer quality thực sự.
