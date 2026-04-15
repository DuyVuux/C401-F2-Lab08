"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # ── BASELINE E1–E6 (không chỉnh sửa) ─────────────────────────────────────

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # ── MỚI — Sprint 2A: Đoàn Nam Sơn ───────────────────────────────────────

    # E7: exported_at không rỗng trên cleaned rows
    #
    # Lý do severity=warn (không halt):
    #   freshness_check.py đọc latest_exported_at từ manifest để tính data age.
    #   Nếu exported_at rỗng, manifest ghi latest_exported_at="" → freshness check
    #   cho kết quả sai (PASS khi đáng FAIL). Đây là warn vì không ảnh hưởng trực
    #   tiếp nội dung câu trả lời, nhưng phá vỡ SLA observability.
    #
    # metric_impact: thay đổi khi export source không điền exported_at.
    #   Trên baseline: missing_exported_at=0 (tất cả 6 row đều có giá trị).
    no_exported = [r for r in cleaned_rows if not (r.get("exported_at") or "").strip()]
    ok7 = len(no_exported) == 0
    results.append(
        ExpectationResult(
            "exported_at_not_empty",
            ok7,
            "warn",
            f"missing_exported_at={len(no_exported)},total_cleaned={len(cleaned_rows)}",
        )
    )

    # E8: chunk_id phải unique trên toàn bộ cleaned batch
    #
    # Lý do severity=halt:
    #   Embed pipeline dùng col.upsert(ids=[chunk_id]). Nếu hai row có cùng chunk_id
    #   thì row sau ghi đè row trước trong ChromaDB — không lỗi, nhưng mất dữ liệu
    #   ngầm (silent data loss). Đây là vi phạm contract idempotency nghiêm trọng.
    #
    # metric_impact: thay đổi nếu hàm _stable_chunk_id() bị bug (hash collision
    #   hoặc seq counter reset giữa chừng). Trên baseline: duplicate_chunk_ids=0.
    chunk_ids = [r.get("chunk_id", "") for r in cleaned_rows]
    seen: set[str] = set()
    dup_ids: list[str] = []
    for cid in chunk_ids:
        if cid in seen:
            dup_ids.append(cid)
        seen.add(cid)
    ok8 = len(dup_ids) == 0
    results.append(
        ExpectationResult(
            "chunk_id_unique",
            ok8,
            "halt",
            f"duplicate_chunk_ids={len(dup_ids)},examples={dup_ids[:3] if dup_ids else '[]'}",
        )
    )

    # E9: tất cả 4 doc canonical phải có ít nhất 1 chunk trong cleaned
    #
    # Lý do severity=warn (không halt):
    #   Nếu một cleaning rule quá aggressive quarantine toàn bộ chunk của một doc,
    #   vector store mất coverage hoàn toàn của domain đó (ví dụ: mất hr_leave_policy
    #   → agent không trả lời được câu hỏi về phép năm). Đây là corpus completeness
    #   check — warn vì partial coverage vẫn tốt hơn dừng pipeline.
    #
    # Đây cũng là expectation có thể fail khi inject: nếu --no-refund-fix kết hợp
    #   với source data thiếu chunk từ một doc, E9 sẽ FAIL và alert sớm.
    #
    # metric_impact: thay đổi khi inject xóa hết chunk của một doc. Baseline: all_docs_ok=True.
    CANONICAL_DOC_IDS = frozenset(
        {"policy_refund_v4", "sla_p1_2026", "it_helpdesk_faq", "hr_leave_policy"}
    )
    docs_in_cleaned = {r.get("doc_id", "") for r in cleaned_rows}
    missing_docs = sorted(CANONICAL_DOC_IDS - docs_in_cleaned)
    ok9 = len(missing_docs) == 0
    results.append(
        ExpectationResult(
            "all_canonical_docs_represented",
            ok9,
            "warn",
            f"missing_doc_ids={missing_docs},present={sorted(docs_in_cleaned & CANONICAL_DOC_IDS)}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt