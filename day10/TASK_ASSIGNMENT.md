# Phân Công Công Việc — Lab Day 10: Data Pipeline & Data Observability

**Nhóm:** C401-F2  
**Deadline code:** 18:00 hôm nay  
**Deadline report:** Sau 18:00 (vẫn được commit)

> **Nguyên tắc:** Pipeline phải idempotent — rerun 2 lần không sinh duplicate trong vector store.  
> **Khi push:** Viết commit message rõ role + sprint, ví dụ: `[gia-bach][sprint1] implement etl ingest step`

---

## Tổng quan phân vai

| Thành viên | Vai trò | Sprint chính | Files sở hữu |
|------------|---------|-------------|--------------|
| **Nhữ Gia Bách** | ETL Architect / Ingestion | Sprint 1 | `etl_pipeline.py`, `transform/cleaning_rules.py` |
| **Vũ Đức Duy** | Embedding & Vector Update | Sprint 2 | `transform/embed_pipeline.py`, chroma update logic |
| **Đoàn Nam Sơn** | Data Quality / Expectations | Sprint 2–3 | `quality/expectations.py`, `quality/quality_report.py` |
| **Hoàng Vĩnh Giang** | Inject Corruption + Before/After Eval | Sprint 3 | `quality/inject_corruption.py`, `artifacts/before_after_eval.csv` |
| **Trần Quang Quí** | Monitoring, Docs & Individual Report | Sprint 4 | `monitoring/freshness_check.py`, `docs/`, `reports/` |

> Ai xong sớm → pull sang hỗ trợ sprint tiếp theo.

---

## Dependency giữa các sprint

```
Sprint 1 — Gia Bách (etl_pipeline.py: ingest → clean → log)
    │
    ├──► Sprint 2a — Vũ Đức Duy (embed cleaned data vào ChromaDB)
    │
    └──► Sprint 2b — Đoàn Nam Sơn (viết expectation suite trên cleaned data)
              │
              ├──► Sprint 3 — Hoàng Vĩnh Giang (inject corruption → measure before/after)
              │
              └──► Sprint 4 — Trần Quang Quí (freshness monitor + runbook + 3 docs + reports)
```

**Blocking rule:** Duy và Sơn chỉ bắt đầu sau khi Bách push `etl_pipeline.py` với `cleaned_records` log xác nhận.

---

## Folder tree bắt buộc (tạo ngay từ đầu)

```
day10/lab/
├── etl_pipeline.py              # Bách — pipeline chính: ingest → clean → validate → embed
├── transform/
│   ├── cleaning_rules.py        # Bách — rules: dedupe, date parse, unicode, null drop
│   └── embed_pipeline.py        # Duy — load cleaned → chunk → embed → upsert ChromaDB
├── quality/
│   ├── expectations.py          # Sơn — expectation suite (6 dimensions)
│   ├── quality_report.py        # Sơn — generate quality_report.json
│   └── inject_corruption.py     # Giang — corrupt data để đo ảnh hưởng
├── monitoring/
│   └── freshness_check.py       # Quí — freshness SLA check, alert stub
├── artifacts/
│   ├── quality_report.json      # output của quality_report.py
│   ├── before_after_eval.csv    # Giang — so sánh answer trước/sau clean data
│   └── pipeline_run.log         # log từ etl_pipeline.py (không push log test)
├── docs/
│   ├── pipeline_architecture.md # Quí — ASCII diagram + component table
│   ├── data_contract.md         # Quí — schema, validation rules, freshness SLA
│   └── runbook.md               # Quí — triage flow: freshness → volume → schema → lineage
└── reports/
    ├── group_report.md           # Quí tổng hợp
    └── individual/
        ├── nhu_gia_bach.md
        ├── vu_duc_duy.md
        ├── doan_nam_son.md
        ├── hoang_vinh_giang.md
        └── tran_quang_qui.md
```

---

## Sprint 1 — Nhữ Gia Bách: ETL Ingest + Clean

**Mục tiêu:** `etl_pipeline.py` chạy end-to-end: đọc raw corpus → clean → log số liệu → xuất cleaned data.

**Corpus đầu vào:** Tái dùng 5 docs từ Day 08/09 (`chroma_db` hoặc raw PDF/MD files).

### Skeleton `etl_pipeline.py`

```python
"""
etl_pipeline.py — Day 10: Data Pipeline
Sprint 1 (Nhữ Gia Bách): ingest → clean → validate
Sprint 2 (Vũ Đức Duy): embed → upsert ChromaDB
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from transform.cleaning_rules import clean_record

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

RAW_DATA_DIR = Path(__file__).parent / "data" / "raw"
CLEANED_OUTPUT  = Path(__file__).parent / "artifacts" / "cleaned_records.jsonl"

def ingest_raw() -> list[dict]:
    """Đọc toàn bộ raw records từ thư mục data/raw (JSON/JSONL)."""
    records = []
    for f in RAW_DATA_DIR.glob("*.jsonl"):
        for line in f.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    log.info(f"raw_records={len(records)}")
    return records

def run_pipeline(run_id: str | None = None) -> dict:
    run_id = run_id or datetime.now().strftime("%Y-%m-%dT%H:%M")
    raw = ingest_raw()

    cleaned, dropped_dup, flagged_missing = [], 0, 0
    seen_ids = set()
    for r in raw:
        result = clean_record(r)
        if result["status"] == "drop_duplicate":
            dropped_dup += 1
        elif result["status"] == "flag_missing":
            flagged_missing += 1
            cleaned.append(result["record"])
        elif result["status"] == "ok":
            if r.get("doc_id") not in seen_ids:
                seen_ids.add(r.get("doc_id"))
                cleaned.append(result["record"])

    CLEANED_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(CLEANED_OUTPUT, "w") as f:
        for rec in cleaned:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    stats = {
        "run_id": run_id,
        "raw_records": len(raw),
        "cleaned_records": len(cleaned),
        "dropped_duplicates": dropped_dup,
        "flagged_missing_date": flagged_missing,
    }
    log.info(json.dumps(stats))
    return stats

if __name__ == "__main__":
    stats = run_pipeline()
    print(stats)
```

### Skeleton `transform/cleaning_rules.py`

```python
"""
cleaning_rules.py — Day 10 Sprint 1 (Nhữ Gia Bách)
6 cleaning rules: dedupe, date parse, unicode normalize, null drop, whitespace, schema check
"""
import re
import unicodedata
from datetime import datetime

DATE_PATTERNS = ["%Y-%m-%d", "%d/%m/%y", "%Y/%m/%d", "%d-%m-%Y"]

def parse_date(raw: str) -> str | None:
    """Thử các format phổ biến, trả về ISO date hoặc None."""
    if not raw:
        return None
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None

def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFC", text) if text else text

def clean_record(record: dict) -> dict:
    """
    Trả về {"status": "ok"|"drop_duplicate"|"flag_missing", "record": {...}}
    Rules:
      1. content rỗng → drop (reject cứng)
      2. doc_id None → reject
      3. duplicate doc_id → caller xử lý (trả về status drop_duplicate)
      4. date parse → chuẩn hoá sang ISO format, nếu fail → flag_missing
      5. unicode normalize content
      6. whitespace trim tất cả string fields
    """
    rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in record.items()}

    if not rec.get("content"):
        return {"status": "drop_duplicate", "record": rec}   # thực ra drop empty
    if not rec.get("doc_id"):
        return {"status": "drop_duplicate", "record": rec}

    parsed = parse_date(rec.get("effective_date", ""))
    if parsed:
        rec["effective_date"] = parsed
    else:
        rec["effective_date"] = None
        return {"status": "flag_missing", "record": rec}

    rec["content"] = normalize_unicode(rec.get("content", ""))
    return {"status": "ok", "record": rec}
```

### DoD Sprint 1

- [ ] `python etl_pipeline.py` chạy không lỗi
- [ ] Log in ra: `raw_records=N`, `cleaned_records=M`, `dropped_duplicates=X`, `flagged_missing_date=Y`
- [ ] `artifacts/cleaned_records.jsonl` được tạo ra
- [ ] Không hard-code path tuyệt đối

---

## Sprint 2a — Vũ Đức Duy: Embed Cleaned Data → ChromaDB

**Mục tiêu:** Load `cleaned_records.jsonl` → chunk → embed với `text-embedding-3-small` → upsert vào ChromaDB collection `day10_docs`.

**Dependency:** Chờ Bách push `artifacts/cleaned_records.jsonl` (hoặc mock 5 records để test trước).

### Skeleton `transform/embed_pipeline.py`

```python
"""
embed_pipeline.py — Day 10 Sprint 2a (Vũ Đức Duy)
Load cleaned JSONL → embed → upsert ChromaDB (idempotent: dùng doc_id làm id)
"""
import json
import os
from pathlib import Path

import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

CLEANED_INPUT = Path(__file__).parent.parent / "artifacts" / "cleaned_records.jsonl"
CHROMA_PATH   = Path(__file__).parent.parent / "chroma_db"
COLLECTION    = "day10_docs"

def chunk_record(record: dict) -> list[dict]:
    """Simple chunking: 1 record = 1 chunk (có thể mở rộng sau)."""
    return [{
        "id": f"{record['doc_id']}_0",
        "text": record["content"],
        "metadata": {
            "source": record.get("source", "unknown"),
            "effective_date": record.get("effective_date", ""),
            "doc_id": record["doc_id"],
            "run_id": record.get("run_id", ""),
        }
    }]

def embed_and_upsert(run_id: str = "") -> dict:
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    col = client.get_or_create_collection(COLLECTION)
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    records = [json.loads(l) for l in CLEANED_INPUT.read_text().splitlines() if l.strip()]
    chunks = [c for r in records for c in chunk_record(r)]

    ids, docs, metas, embeddings = [], [], [], []
    for c in chunks:
        resp = openai_client.embeddings.create(input=c["text"], model="text-embedding-3-small")
        ids.append(c["id"])
        docs.append(c["text"])
        metas.append(c["metadata"])
        embeddings.append(resp.data[0].embedding)

    # Upsert idempotent — same id sẽ overwrite, không duplicate
    col.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
    print(f"[embed] upserted {len(ids)} chunks into '{COLLECTION}'")
    return {"chunks_upserted": len(ids), "collection": COLLECTION}

if __name__ == "__main__":
    result = embed_and_upsert()
    print(result)
```

### DoD Sprint 2a

- [ ] `python transform/embed_pipeline.py` chạy không lỗi
- [ ] ChromaDB collection `day10_docs` được tạo/update với đúng số chunks
- [ ] Upsert idempotent: chạy 2 lần không tăng số record trong collection
- [ ] Metadata có `effective_date`, `source`, `doc_id`

---

## Sprint 2b — Đoàn Nam Sơn: Data Quality Expectations + Quality Report

**Mục tiêu:** Implement expectation suite cho 6 dimensions + generate `quality_report.json` từ `cleaned_records.jsonl`.

**Dependency:** Chờ Bách push `cleaned_records.jsonl` (mock nếu chưa có).

### Skeleton `quality/expectations.py`

```python
"""
expectations.py — Day 10 Sprint 2b (Đoàn Nam Sơn)
6 dimensions: Completeness, Accuracy, Consistency, Timeliness, Validity, Uniqueness
"""
import json
import re
from pathlib import Path

DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")

class ExpectationResult:
    def __init__(self, name: str, passed: bool, failed_count: int = 0, details: str = ""):
        self.name = name
        self.passed = passed
        self.failed_count = failed_count
        self.details = details

    def to_dict(self):
        return {"name": self.name, "passed": self.passed,
                "failed_count": self.failed_count, "details": self.details}

def run_suite(records: list[dict]) -> list[ExpectationResult]:
    results = []
    ids = [r.get("doc_id") for r in records]

    # 1. Completeness: content không null/rỗng
    empty_content = [r for r in records if not r.get("content")]
    results.append(ExpectationResult(
        "content_not_null", len(empty_content) == 0, len(empty_content),
        f"{len(empty_content)} records thiếu content"
    ))

    # 2. Uniqueness: doc_id không duplicate
    dup_count = len(ids) - len(set(ids))
    results.append(ExpectationResult(
        "doc_id_unique", dup_count == 0, dup_count,
        f"{dup_count} doc_id bị trùng"
    ))

    # 3. Validity: effective_date đúng ISO format
    bad_dates = [r for r in records if r.get("effective_date") and
                 not DATE_REGEX.match(str(r["effective_date"]))]
    results.append(ExpectationResult(
        "effective_date_format", len(bad_dates) == 0, len(bad_dates),
        f"{len(bad_dates)} records có date sai format"
    ))

    # 4. Completeness: source không null
    no_source = [r for r in records if not r.get("source")]
    results.append(ExpectationResult(
        "source_not_null", len(no_source) == 0, len(no_source),
        f"{len(no_source)} records thiếu source"
    ))

    # 5. Validity: content length tối thiểu 20 ký tự
    short_content = [r for r in records if len(r.get("content", "")) < 20]
    results.append(ExpectationResult(
        "content_min_length_20", len(short_content) == 0, len(short_content),
        f"{len(short_content)} records có content quá ngắn"
    ))

    # 6. Consistency: tất cả records có đủ required fields
    required = {"doc_id", "source", "content", "effective_date"}
    missing_fields = [r for r in records if not required.issubset(r.keys())]
    results.append(ExpectationResult(
        "required_fields_present", len(missing_fields) == 0, len(missing_fields),
        f"{len(missing_fields)} records thiếu required fields"
    ))

    return results

if __name__ == "__main__":
    from pathlib import Path
    cleaned = Path(__file__).parent.parent / "artifacts" / "cleaned_records.jsonl"
    records = [json.loads(l) for l in cleaned.read_text().splitlines() if l.strip()]
    for r in run_suite(records):
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name}: {r.details}")
```

### Skeleton `quality/quality_report.py`

```python
"""
quality_report.py — Day 10 Sprint 2b (Đoàn Nam Sơn)
Generate artifacts/quality_report.json
"""
import json
from datetime import datetime
from pathlib import Path

from quality.expectations import run_suite

CLEANED  = Path(__file__).parent.parent / "artifacts" / "cleaned_records.jsonl"
REPORT   = Path(__file__).parent.parent / "artifacts" / "quality_report.json"

def generate_report(run_id: str | None = None) -> dict:
    run_id = run_id or datetime.now().strftime("%Y-%m-%dT%H:%M")
    records = [json.loads(l) for l in CLEANED.read_text().splitlines() if l.strip()]
    results = run_suite(records)
    passed = sum(1 for r in results if r.passed)
    report = {
        "run_id": run_id,
        "total_records": len(records),
        "expectations_total": len(results),
        "expectations_passed": passed,
        "expectations_failed": len(results) - passed,
        "all_passed": passed == len(results),
        "results": [r.to_dict() for r in results],
        "generated_at": datetime.now().isoformat(),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[quality] Report saved → {REPORT}")
    print(f"[quality] {passed}/{len(results)} expectations passed")
    return report

if __name__ == "__main__":
    generate_report()
```

### DoD Sprint 2b

- [ ] `python quality/expectations.py` in ra PASS/FAIL cho 6 expectations
- [ ] `python quality/quality_report.py` tạo `artifacts/quality_report.json`
- [ ] Bao gồm đủ 6 dimensions: Completeness, Accuracy, Consistency, Timeliness, Validity, Uniqueness
- [ ] JSON report có `run_id`, `total_records`, `expectations_passed`, chi tiết từng expectation

---

## Sprint 3 — Hoàng Vĩnh Giang: Inject Corruption + Before/After Eval

**Mục tiêu:** Cố tình inject lỗi vào data (missing date, duplicate, encoding lỗi), so sánh agent answer trước và sau khi clean.

**Dependency:** Chờ Duy push `embed_pipeline.py` và Sơn push `expectations.py`.

### Skeleton `quality/inject_corruption.py`

```python
"""
inject_corruption.py — Day 10 Sprint 3 (Hoàng Vĩnh Giang)
Inject 4 loại lỗi vào cleaned records để tạo "dirty" dataset:
  1. missing date (set effective_date = None)
  2. duplicate doc_id
  3. encoding error (thêm ký tự lạ vào content)
  4. empty content

Sau đó chạy pipeline trên dirty data → compare answer quality với clean data.
"""
import json
from pathlib import Path
from copy import deepcopy

CLEANED  = Path(__file__).parent.parent / "artifacts" / "cleaned_records.jsonl"
DIRTY    = Path(__file__).parent.parent / "artifacts" / "dirty_records.jsonl"

def inject_corruption(records: list[dict], corruption_rate: float = 0.3) -> tuple[list[dict], dict]:
    """Inject lỗi vào ~30% records. Trả về (dirty_records, corruption_stats)."""
    dirty = deepcopy(records)
    n = len(dirty)
    stats = {"missing_date": 0, "duplicate": 0, "encoding_error": 0, "empty_content": 0}

    # 1. Missing date: record đầu tiên
    if n > 0:
        dirty[0]["effective_date"] = None
        stats["missing_date"] += 1

    # 2. Duplicate: nhân đôi record thứ 2
    if n > 1:
        dirty.append(deepcopy(dirty[1]))
        stats["duplicate"] += 1

    # 3. Encoding error: record thứ 3
    if n > 2:
        dirty[2]["content"] = dirty[2]["content"] + " \ufffd\ufffd SLA = 2h"
        stats["encoding_error"] += 1

    # 4. Empty content: record thứ 4
    if n > 3:
        dirty[3]["content"] = ""
        stats["empty_content"] += 1

    return dirty, stats

def run_before_after_eval(test_queries: list[str]) -> list[dict]:
    """
    Với mỗi query: embed dirty data → lấy answer (before), embed clean data → lấy answer (after).
    Trả về list[{query, before_answer, after_answer, note}]
    """
    # TODO: import run_graph từ Day 09 hoặc implement simple retrieval + GPT-4o-mini call
    results = []
    for q in test_queries:
        results.append({
            "query": q,
            "before_answer": "[dirty data answer - fill after running with dirty embed]",
            "after_answer":  "[clean data answer - fill after running with clean embed]",
            "note": "manual comparison or automated eval"
        })
    return results

if __name__ == "__main__":
    records = [json.loads(l) for l in CLEANED.read_text().splitlines() if l.strip()]
    dirty, stats = inject_corruption(records)

    DIRTY.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in dirty))
    print(f"[corruption] Injected: {stats}")
    print(f"[corruption] Dirty records saved → {DIRTY} ({len(dirty)} records vs {len(records)} clean)")

    # Chạy expectations trên dirty data để thấy failures
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from quality.expectations import run_suite
    print("\n[corruption] Expectations on DIRTY data:")
    for r in run_suite(dirty):
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name}: {r.details}")
```

### Tạo `artifacts/before_after_eval.csv` thủ công hoặc tự động

Format cột bắt buộc:
```
query,dirty_answer,clean_answer,improvement_note
"SLA P1 deadline là bao lâu?","SLA = 2h [encoding lỗi]","SLA resolution P1 là 4 giờ","Encoding fix → answer đúng version"
"Policy hoàn tiền?","Refund 14 ngày [stale]","Refund 7 ngày (v4)","Data refresh → đúng version"
"Ai phê duyệt Level 3 access?","Không có thông tin","Line Manager, IT Admin, IT Security","Content đủ → answer đầy đủ"
```

### DoD Sprint 3

- [ ] `python quality/inject_corruption.py` tạo `artifacts/dirty_records.jsonl` với 4 loại lỗi
- [ ] Expectations chạy trên dirty data thấy ít nhất 3 FAIL rõ ràng
- [ ] `artifacts/before_after_eval.csv` có ít nhất 3 queries với cột đủ: query, dirty_answer, clean_answer, improvement_note
- [ ] Có evidence rõ: dirty data → agent answer sai/lệch, clean data → answer đúng

---

## Sprint 4 — Trần Quang Quí: Monitoring + Docs + Reports

**Mục tiêu:** Freshness check, 3 docs, group report, individual report.

**Dependency:** Chạy sau khi Bách/Duy/Sơn/Giang push xong.

### Skeleton `monitoring/freshness_check.py`

```python
"""
freshness_check.py — Day 10 Sprint 4 (Trần Quang Quí)
Check freshness SLA: collection phải được update trong vòng 24h.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import chromadb

CHROMA_PATH     = Path(__file__).parent.parent / "chroma_db"
COLLECTION      = "day10_docs"
FRESHNESS_SLA_H = 24   # hours
REPORT_OUT      = Path(__file__).parent.parent / "artifacts" / "freshness_report.json"

def check_freshness() -> dict:
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    try:
        col = client.get_collection(COLLECTION)
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "checked_at": datetime.now().isoformat()}

    count = col.count()
    # Lấy metadata để tìm run_id gần nhất
    peek = col.peek(limit=count or 1)
    run_ids = [m.get("run_id", "") for m in (peek.get("metadatas") or [])]
    latest_run = max((r for r in run_ids if r), default=None)

    freshness_ok = False
    age_hours = None
    if latest_run:
        try:
            last_update = datetime.fromisoformat(latest_run)
            age_hours = (datetime.now() - last_update).total_seconds() / 3600
            freshness_ok = age_hours <= FRESHNESS_SLA_H
        except ValueError:
            pass

    result = {
        "checked_at": datetime.now().isoformat(),
        "collection": COLLECTION,
        "total_chunks": count,
        "latest_run_id": latest_run,
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "freshness_sla_hours": FRESHNESS_SLA_H,
        "freshness_ok": freshness_ok,
        "status": "PASS" if freshness_ok else "STALE",
    }

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(json.dumps(result, indent=2))
    print(f"[freshness] Status: {result['status']} | age={age_hours:.1f}h | chunks={count}")
    return result

if __name__ == "__main__":
    check_freshness()
```

### Docs cần viết (từ kết quả thực tế, không dùng ước đoán)

**`docs/pipeline_architecture.md`** — diagram ASCII + bảng component:
```
raw files → etl_pipeline.py → cleaned_records.jsonl
                                    ↓
                         embed_pipeline.py → ChromaDB day10_docs
                                    ↓
                         expectations.py → quality_report.json
                                    ↓
                         freshness_check.py → freshness_report.json
```
- Bảng: component, file, owner, input, output
- Ghi rõ run_id flow và idempotency guarantee

**`docs/data_contract.md`** — schema bắt buộc:
- Required fields: `doc_id`, `source`, `content`, `effective_date`
- Format: `effective_date` = ISO 8601 (`YYYY-MM-DD`)
- Freshness SLA: collection phải được update ≤ 24h
- Minimum content length: 20 ký tự
- Rejection rule: empty content → drop; missing date → flag

**`docs/runbook.md`** — triage flow khi agent trả lời cũ/sai:
```
1. Check freshness_report.json → age_hours > 24? → rerun embed_pipeline.py
2. Check quality_report.json  → any FAIL? → rerun etl_pipeline.py → re-embed
3. Check dirty_records.jsonl  → có corruption? → fix cleaning_rules.py
4. Rerun: python etl_pipeline.py && python transform/embed_pipeline.py
5. Verify: python monitoring/freshness_check.py → PASS
6. Re-test query → so sánh với before_after_eval.csv
```

### DoD Sprint 4

- [ ] `python monitoring/freshness_check.py` in ra PASS/STALE + `artifacts/freshness_report.json`
- [ ] 3 docs đầy đủ từ kết quả thực tế (không placeholder)
- [ ] `reports/group_report.md` có: kiến trúc, quyết định kỹ thuật chính, trước/sau eval, phân công
- [ ] `reports/individual/tran_quang_qui.md` ≥ 4 mục theo template Day 09

---

## Rubric & Điểm tham khảo

| Hạng mục | Điểm | Ai chịu trách nhiệm |
|----------|------|---------------------|
| `etl_pipeline.py` chạy end-to-end + log chuẩn | 20% | Bách |
| `embed_pipeline.py` upsert idempotent vào ChromaDB | 15% | Duy |
| Expectation suite ≥ 6 dimensions + quality_report.json | 15% | Sơn |
| inject_corruption + before_after_eval.csv có evidence | 15% | Giang |
| freshness_check + 3 docs + runbook | 15% | Quí |
| Individual reports (5 người × 2%) | 10% | Tất cả |
| Bonus: pipeline tích hợp tự động (1 lệnh chạy hết) | +5% | Bách tổng hợp |

---

## Checklist nộp bài (18:00)

- [ ] `etl_pipeline.py` chạy không lỗi
- [ ] `transform/embed_pipeline.py` chạy không lỗi, collection `day10_docs` có data
- [ ] `artifacts/quality_report.json` tồn tại và có ≥ 6 expectations
- [ ] `artifacts/before_after_eval.csv` tồn tại với ≥ 3 rows
- [ ] `artifacts/freshness_report.json` tồn tại
- [ ] `docs/pipeline_architecture.md`, `docs/data_contract.md`, `docs/runbook.md` đủ nội dung
- [ ] `reports/group_report.md` hoàn chỉnh
- [ ] 5 individual reports commit xong
- [ ] `.gitignore` không commit: `.env`, `__pycache__/`, `chroma_db/`, `*.pyc`, `artifacts/dirty_records.jsonl` (chỉ commit clean artifacts)

---

## Lưu ý kỹ thuật

1. **Corpus tái dùng:** Nếu chưa có data/raw, copy 5 docs từ Day 08 sang và convert sang JSONL format (`doc_id`, `source`, `content`, `effective_date`).
2. **Idempotency:** `embed_pipeline.py` dùng `col.upsert()` (không phải `col.add()`) để tránh duplicate khi rerun.
3. **run_id:** Truyền `run_id` từ `etl_pipeline.py` → `embed_pipeline.py` → `freshness_check.py` để trace được pipeline run.
4. **Before/After eval:** Có thể dùng lại `run_graph()` từ Day 09 hoặc implement `simple_retrieve_answer()` gọi trực tiếp ChromaDB + GPT-4o-mini.
5. **Không push `.env`, `chroma_db/`, log test** — chỉ push official artifacts.
