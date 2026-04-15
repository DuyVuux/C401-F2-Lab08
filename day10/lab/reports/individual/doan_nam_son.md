# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Data Observability

**Họ và tên:** Đoàn Nam Sơn
**Vai trò trong nhóm:** Cleaning & Quality Owner
**Sprint:** 2A
**Ngày nộp:** 2026-04-15

---

## 1. Phần tôi phụ trách

**File chính:** `quality/expectations.py`

**Các expectation tôi thêm:**
- `E7: exported_at_not_empty` — function body trong `run_expectations()`, severity warn
- `E8: chunk_id_unique` — function body trong `run_expectations()`, severity halt
- `E9: all_canonical_docs_represented` — function body trong `run_expectations()`, severity warn

**Cách kết nối với phần thành viên khác:**

`run_expectations(cleaned_rows)` được gọi bởi `etl_pipeline.py` ngay sau khi Bách's `clean_rows()` trả kết quả. Tôi nhận đúng output của Bách (list of cleaned row dicts) và trả về `(results, halt)` cho pipeline quyết định có embed không. Duy dùng kết quả embed để chạy `eval_retrieval.py` — nếu tôi halt sai, Duy không có eval baseline. Giang dùng log `expectation[...]` từ run inject để điền bảng `metric_impact`.

**Bằng chứng:** commit `eb8660b69e384206e4dfdea25b2c1278c6695be4`

---

## 2. Quyết định kỹ thuật

**Quyết định:** Tách E7, E8, E9 thành ba concerns riêng biệt thay vì gộp vào một expectation "data_quality_general".

**Bối cảnh:** Ban đầu tôi cân nhắc một expectation tổng hợp kiểm tra nhiều field cùng lúc. Nhưng khi đọc cách `etl_pipeline.py` log từng expectation riêng (`expectation[name] OK/FAIL (severity) :: detail`), rõ ràng nếu gộp thì Giang không thể tách `metric_impact` theo từng rule/expectation — bảng trong group report sẽ thiếu granularity.

**Lý do chọn severity cho từng expectation:**

| Expectation | Severity | Lý do |
|-------------|----------|-------|
| E7: exported_at_not_empty | warn | Không ảnh hưởng nội dung câu trả lời; chỉ phá vỡ freshness observability |
| E8: chunk_id_unique | halt | Duplicate chunk_id → silent data loss khi `col.upsert()` ghi đè trong ChromaDB |
| E9: all_canonical_docs_represented | warn | Partial coverage vẫn tốt hơn dừng pipeline; nhưng cần alert sớm |

**Trade-off chấp nhận:** E9 hard-code `CANONICAL_DOC_IDS` giống `ALLOWED_DOC_IDS` trong `cleaning_rules.py`. Nếu nhóm mở rộng thêm doc mới phải cập nhật cả hai chỗ. Giải pháp tốt hơn là đọc từ `contracts/data_contract.yaml`, nhưng trong thời gian lab, tôi ưu tiên code dễ đọc hơn DRY hoàn hảo.

---

## 3. Sự cố phát hiện và fix

**Vấn đề:** E8 phiên bản đầu dùng `len(set(chunk_ids)) != len(chunk_ids)` để detect duplicate. Điều này chỉ cho biết **có** duplicate, không cho biết **chunk_id nào** bị trùng.

**Symptom:** Khi test với mock data có duplicate, log chỉ hiện `duplicate_chunk_ids=1` — Giang không biết phải tìm chunk_id nào trong cleaned CSV để debug.

**Root cause:** Dùng `set()` mất thông tin về phần tử nào bị trùng.

**Cách fix:** Thay bằng loop tường minh tracking `seen: set[str]` và `dup_ids: list[str]`. Detail string trả về cả count lẫn `examples=[...]` — tối đa 3 ID đầu để không flood log.

**Bằng chứng trước/sau:**

Trước:
```
expectation[chunk_id_unique] FAIL (halt) :: duplicate_chunk_ids=1
```

Sau:
```
expectation[chunk_id_unique] FAIL (halt) :: duplicate_chunk_ids=1,examples=['policy_refund_v4_2_c96089a4']
```

---

## 4. Before/After

Chạy `python etl_pipeline.py run --run-id test-sprint2a` sau khi push `expectations.py`:

```
expectation[min_one_row]                    OK   (halt) :: cleaned_rows=6
expectation[no_empty_doc_id]                OK   (halt) :: empty_doc_id_count=0
expectation[refund_no_stale_14d_window]     OK   (halt) :: violations=0
expectation[chunk_min_length_8]             OK   (warn) :: short_chunks=0
expectation[effective_date_iso_yyyy_mm_dd]  OK   (halt) :: non_iso_rows=0
expectation[hr_leave_no_stale_10d_annual]   OK   (halt) :: violations=0
expectation[exported_at_not_empty]          OK   (warn) :: missing_exported_at=0,total_cleaned=6
expectation[chunk_id_unique]                OK   (halt) :: duplicate_chunk_ids=0,examples=[]
expectation[all_canonical_docs_represented] OK   (warn) :: missing_doc_ids=[],present=['hr_leave_policy','it_helpdesk_faq','policy_refund_v4','sla_p1_2026']
```

Sau inject (`--no-refund-fix --skip-validate`):
```
expectation[refund_no_stale_14d_window]     FAIL (halt) :: violations=1
expectation[exported_at_not_empty]          OK   (warn) :: missing_exported_at=0,total_cleaned=6
expectation[chunk_id_unique]                OK   (halt) :: duplicate_chunk_ids=0,examples=[]
expectation[all_canonical_docs_represented] OK   (warn) :: missing_doc_ids=[],present=[...]
```

E3 fail như mong đợi. E7/E8/E9 đều pass → chứng minh inject chỉ tác động đúng vào stale refund window, không phá vỡ các invariant khác.

---

## 5. Nếu có thêm 2 giờ

Tôi sẽ đưa `CANONICAL_DOC_IDS` vào `contracts/data_contract.yaml` (field `allowed_doc_ids`) và cho cả `cleaning_rules.py` lẫn `expectations.py` đọc từ đó thay vì hard-code ở hai nơi. Trace từ E9 (`missing_doc_ids=[...]`) trong log inject cho thấy nếu source CSV tương lai thiếu một doc hoàn toàn thì sẽ khó trace nguyên nhân vì hai file dùng constant riêng — fix này giải quyết đúng root cause đó.

---

*Lưu file tại: `reports/individual/doan_nam_son.md`*