# Kiến trúc pipeline — Lab Day 10

**Nhóm:** C401-F2  
**Cập nhật:** 2026-04-15 · run_id chuẩn: `sprint2-rules`

---

## 1. Sơ đồ luồng

```
data/raw/policy_export_dirty.csv
        │
        ▼  etl_pipeline.py run
        │
        ├── transform/cleaning_rules.py
        │       rules 1–4 (baseline): allowlist doc_id, parse effective_date ISO,
        │                             quarantine HR stale (<2026-01-01), fix refund 14→7,
        │                             dedupe chunk_text, quarantine empty chunk_text
        │       rules 5–7 (mới, Bách): validate exported_at not empty,
        │                              validate exported_at ISO format,
        │                              check exported_at >= effective_date
        │       rule  8   (mới, Bách): quarantine chunk_text < 20 ký tự
        │
        ├── artifacts/cleaned/cleaned_<run_id>.csv      ← cleaned records
        ├── artifacts/quarantine/quarantine_<run_id>.csv ← quarantined records
        │
        ▼  quality/expectations.py  [FRESHNESS BOUNDARY 1: ingest]
        │       E1–E6 (baseline) + E7–E8 (Sơn, Sprint 2a)
        │       halt nếu expectation severity=halt fail → pipeline dừng
        │
        ▼  cmd_embed_internal() trong etl_pipeline.py   [FRESHNESS BOUNDARY 2: publish]
        │       upsert theo chunk_id (idempotent)
        │       prune chunk_id cũ không còn trong cleaned run này
        │       model: all-MiniLM-L6-v2 (SentenceTransformer, CPU)
        │
        ├── ChromaDB: chroma_db/ · collection: day10_kb
        │
        ▼  artifacts/manifests/manifest_<run_id>.json
        │       run_id, raw_records, cleaned_records, quarantine_records,
        │       latest_exported_at, no_refund_fix, skipped_validate
        │
        ▼  monitoring/freshness_check.py
                đọc latest_exported_at → so sánh với now → PASS/WARN/FAIL (SLA 24h)
                alert_channel: slack:#data-pipeline-alerts

[module mở rộng — Duy]
transform/embed_pipeline.py
        đọc cleaned CSV mới nhất → embed OpenAI text-embedding-3-small
        upsert + prune vào day10_kb (idempotent, cùng collection)
        dùng khi cần embed lại với OpenAI thay vì SentenceTransformer
```

---

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | Owner |
|------------|-------|--------|-------|
| Ingest | `data/raw/policy_export_dirty.csv` | rows list | Nhữ Gia Bách |
| Transform / Clean | rows list | `cleaned[]`, `quarantine[]` | Nhữ Gia Bách |
| Quality / Expectations | `cleaned[]` | `ExpectationResult[]`, halt flag | Đoàn Nam Sơn |
| Embed (baseline) | cleaned CSV | ChromaDB `day10_kb` (upsert + prune) | Vũ Đức Duy |
| Embed (OpenAI module) | cleaned CSV | ChromaDB `day10_kb` (upsert + prune) | Vũ Đức Duy |
| Monitor / Freshness | `manifest_<run_id>.json` | PASS / WARN / FAIL + age_hours | Trần Quang Quí |
| Docs / Report | artifacts thực tế | 3 docs + quality report + group/individual | Trần Quang Quí |

---

## 3. Idempotency & rerun

Embed dùng `col.upsert(ids=[chunk_id], ...)` — cùng `chunk_id` sẽ overwrite, không tạo duplicate.

Sau mỗi run, `cmd_embed_internal()` còn **prune** id không còn trong cleaned CSV:
```python
drop = sorted(prev_ids - set(current_ids))
if drop:
    col.delete(ids=drop)
    log(f"embed_prune_removed={len(drop)}")
```

`chunk_id` được tính bằng `sha256(doc_id|chunk_text|seq)[:16]` — stable theo nội dung, không phụ thuộc thứ tự chạy.

**Verify idempotency:** chạy `python etl_pipeline.py run` 2 lần → `col.count()` không đổi.

---

## 4. Liên hệ Day 09

Day 10 dùng collection `day10_kb` (tách biệt với `rag_lab` / `day09_docs` của Day 09).

**Lý do tách:** Day 10 áp dụng contract mới (exported_at validation, chunk_text min length) — nếu dùng chung collection sẽ làm ảnh hưởng grading Day 09 đang chạy song song.

**Nếu muốn Day 09 agent dùng data sạch của Day 10:** đổi `CHROMA_COLLECTION=day10_kb` trong `.env` của Day 09 và rerun retrieval.

---

## 5. Rủi ro đã biết

| Rủi ro | Mô tả | Mitigation |
|--------|-------|------------|
| Freshness FAIL trên data mẫu | `latest_exported_at=2026-04-10` (5 ngày trước SLA 24h) | Hành vi đúng — giải thích trong runbook; SLA áp cho data snapshot |
| Rule mới không trigger trên data mẫu | 3 rule mới (exported_at) không tăng quarantine vì data mẫu đã hợp lệ | metric_impact được chứng minh qua inject Sprint 3 |
| Embed module song song | `embed_pipeline.py` và `cmd_embed_internal()` cùng upsert `day10_kb` | Idempotent upsert — không tạo duplicate; chạy cái nào cũng ra kết quả giống nhau |
