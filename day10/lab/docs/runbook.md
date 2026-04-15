# Runbook — Lab Day 10

**Nhóm:** C401-F2 · **Owner:** Trần Quang Quí · **Cập nhật:** 2026-04-15

---

## Symptom

Agent trả lời sai version policy — ví dụ:
- Trả lời **"14 ngày"** thay vì **"7 ngày"** cho câu hỏi hoàn tiền (`q_refund_window`)
- Trả lời **"10 ngày phép năm"** thay vì **"12 ngày"** cho chính sách HR 2026 (`q_leave_version`)
- Agent không tìm thấy chunk liên quan (retrieval miss)

---

## Detection

Các signal phát hiện theo thứ tự ưu tiên:

1. `eval_retrieval.py` → `hits_forbidden=yes` hoặc `contains_expected=no` trong `artifacts/eval/*.csv`
2. Log pipeline → `expectation[refund_no_stale_14d_window] FAIL` hoặc `expectation[hr_leave_no_stale_10d_annual] FAIL`
3. `etl_pipeline.py freshness` → `FAIL` (age_hours > 24) — data chưa được cập nhật
4. `artifacts/manifests/manifest_<run_id>.json` → `no_refund_fix=true` hoặc `skipped_validate=true`

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|------------------|
| 1. Freshness | `cat artifacts/manifests/manifest_<run_id>.json` → xem `latest_exported_at` | `age_hours ≤ 24` → PASS; nếu > 24 → data stale, cần rerun |
| 2. Quarantine | `cat artifacts/quarantine/quarantine_<run_id>.csv` | Chunk "14 ngày" hoặc "10 ngày phép" có trong quarantine không? |
| 3. Expectation | Xem log `run_<run_id>.log` → tìm dòng `expectation[...] FAIL` | Expectation nào fail? severity halt hay warn? |
| 4. Collection | `python -c "import chromadb; c=chromadb.PersistentClient('./chroma_db'); col=c.get_collection('day10_kb'); print(col.count()); print(col.peek(3)['documents'])"` | Chunk stale còn trong collection không? |
| 5. Eval | `python eval_retrieval.py --out /tmp/check.csv && cat /tmp/check.csv` | `hits_forbidden=yes` xác nhận chunk stale vẫn được retrieve |

---

## Mitigation

**Trường hợp 1: Pipeline chạy với `--no-refund-fix` (inject có chủ đích)**
```bash
# Rerun chuẩn, không inject
python etl_pipeline.py run --run-id hotfix
python eval_retrieval.py --out artifacts/eval/verify_hotfix.csv
```

**Trường hợp 2: Data stale (freshness FAIL)**
```bash
# Kiểm tra manifest mới nhất
python etl_pipeline.py freshness --manifest artifacts/manifests/manifest_<run_id>.json
# Nếu data source đã cập nhật → rerun pipeline
python etl_pipeline.py run --run-id refresh-$(date +%H%M)
```

**Trường hợp 3: Expectation halt — pipeline không embed**
```bash
# Xem log để biết expectation nào fail
cat artifacts/logs/run_<run_id>.log | grep "FAIL\|HALT"
# Fix data source → rerun (không dùng --skip-validate trừ demo)
python etl_pipeline.py run --run-id fix-<issue>
```

**Verify sau fix:**
```bash
python eval_retrieval.py --out artifacts/eval/verify_after_fix.csv
# Kiểm tra: contains_expected=yes, hits_forbidden=no cho tất cả câu
```

---

## Prevention

| Hành động | Mô tả |
|-----------|-------|
| **Expectation halt** | E3 `refund_no_stale_14d_window` (halt) và E6 `hr_leave_no_stale_10d_annual` (halt) đảm bảo pipeline dừng trước khi embed chunk stale |
| **Freshness monitor** | `FRESHNESS_SLA_HOURS=24` trong `.env`; alert channel `slack:#data-pipeline-alerts` trong `data_contract.yaml` |
| **Idempotent embed** | upsert theo `chunk_id` + prune id cũ → rerun luôn phản ánh đúng cleaned run hiện tại |
| **Quarantine audit** | Sau mỗi run, review `artifacts/quarantine/` — quarantine tăng đột biến là signal có vấn đề ở data source |
| **Kết nối Day 11** | Guardrail từ Day 11 có thể wrap retrieval — nếu `hits_forbidden` trong top-k → reject answer trước khi trả về user |

---

## FAQ nhanh

**Freshness FAIL trên data mẫu có bình thường không?**  
Có — `latest_exported_at=2026-04-10T08:00:00` (5 ngày trước SLA 24h). Data mẫu là snapshot cũ để demo. SLA áp cho production data, không phải data lab. Giải thích nhất quán trong `docs/data_contract.md`.

**`--skip-validate` dùng khi nào?**  
Chỉ dùng để demo Sprint 3 (inject corruption có chủ đích). Không dùng trong run production. Mọi run chính thức phải `exit 0` không có flag này.
