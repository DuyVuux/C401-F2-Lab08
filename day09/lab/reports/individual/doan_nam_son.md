# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Đoàn Nam Sơn
**Vai trò trong nhóm:** Policy + Synthesis Worker Owner
**Ngày nộp:** 2026-04-14
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/policy_tool.py`, `workers/synthesis.py`
- File phụ: `contracts/worker_contracts.yaml` (cập nhật status Sprint 2B)
- Functions tôi implement:
  - `analyze_policy(task, chunks)` — rule-based exception detection
  - `run(state)` trong cả hai workers
  - `synthesize(task, chunks, policy_result, mcp_tools_used)` — LLM synthesis với grounding
  - `_call_llm(messages)` — LLM call với fallback chain
  - `_build_context(chunks, policy_result, mcp_tools_used)` — context builder tích hợp MCP results
  - `_estimate_confidence(chunks, answer, policy_result)` — confidence scoring

**Cách công việc của tôi kết nối với phần của thành viên khác:**

- Phụ thuộc **Gia Bách (Sprint 1)**: `AgentState` schema — tôi cần biết các fields `retrieved_chunks`, `needs_tool`, `policy_result`, `mcp_tools_used` trước khi implement workers.
- Phụ thuộc **Đức Duy (Sprint 2A)**: `retrieved_chunks` từ `retrieval_worker` là input chính của cả hai workers tôi implement. Nếu retrieval trả về `[]`, `policy_tool` vẫn chạy được nhờ rule-based detection, còn `synthesis` sẽ abstain đúng theo contract.
- Cung cấp cho **Vĩnh Giang (Sprint 3)**: `policy_tool.py` đã có wiring `_call_mcp_tool()` để gọi MCP khi `needs_tool=True`. Giang chỉ cần implement `dispatch_tool()` trong `mcp_server.py`.
- Cung cấp cho **Quang Quí (Sprint 4)**: cả hai workers đều ghi đầy đủ `worker_io_logs` và `history` để eval_trace.py có thể phân tích.

**Bằng chứng:** Comment `# Sprint 2B — Đoàn Nam Sơn` trong `contracts/worker_contracts.yaml`, các `actual_implementation.status: "done"` được cập nhật.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Tách exception detection ra khỏi LLM call — dùng rule-based cho exceptions, LLM chỉ để synthesis.

**Bối cảnh vấn đề:**

Ban đầu TASK_ASSIGNMENT.md gợi ý gọi LLM ngay trong `policy_tool.py` để phân tích exceptions. Tôi nhận thấy đây là over-engineering: exceptions trong policy_refund_v4.txt là cố định (Flash Sale, digital product, activated product) — không cần LLM để detect, và gọi LLM thêm làm tăng latency + tốn token.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| LLM classify exceptions trong policy_tool | Linh hoạt với cases mới | +~800ms latency, tốn API quota, có thể hallucinate |
| Rule-based keyword matching (đã chọn) | Nhanh (~1ms), deterministic, không hallucinate | Cần update rules thủ công nếu policy thay đổi |

**Phương án đã chọn:** Rule-based `EXCEPTION_RULES` list trong `policy_tool.py`. Mỗi rule có `keywords`, `type`, `rule` (câu trích dẫn từ tài liệu), và `source`. LLM chỉ được gọi một lần duy nhất ở `synthesis_worker` để tổng hợp câu trả lời cuối.

**Trade-off đã chấp nhận:** Nếu tương lai có exception mới (ví dụ "đơn hàng trong chương trình thành viên vàng"), cần sửa `EXCEPTION_RULES` thủ công. Tuy nhiên trong phạm vi lab với 5 tài liệu cố định, đây là trade-off hợp lý.

**Bằng chứng từ trace/code:**

```python
# policy_tool.py — EXCEPTION_RULES
EXCEPTION_RULES = [
    {
        "type": "flash_sale_exception",
        "keywords": ["flash sale", "khuyến mãi đặc biệt", "flash_sale"],
        "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, policy_refund_v4).",
        "source": "policy_refund_v4.txt",
        "policy_applies": False,
    },
    ...
]
```

Khi test độc lập `python workers/policy_tool.py` với task "Khách hàng Flash Sale yêu cầu hoàn tiền":
```
policy_applies:  False
exception:       flash_sale_exception — Đơn hàng Flash Sale không được hoàn tiền...
workers_called:  ['policy_tool_worker']
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `synthesis_worker` crash khi `mcp_tools_used` chứa ticket info nhưng `_build_context()` chỉ xử lý chunks.

**Symptom:** Khi policy_tool gọi `get_ticket_info` và đưa kết quả vào `mcp_tools_used`, synthesis tạo context chỉ từ `chunks` — bỏ qua hoàn toàn thông tin ticket. Câu hỏi gq09 (P1 lúc 2am + Level 2 access) sẽ trả lời thiếu phần thông tin ticket.

**Root cause:** `_build_context()` ban đầu chỉ nhận `chunks` và `policy_result`. MCP tool results không được đưa vào context, nên LLM không biết thông tin từ MCP để trả lời.

**Cách sửa:** Thêm tham số `mcp_tools_used` vào `_build_context()`, parse kết quả của từng tool type (`get_ticket_info`, `check_access_permission`) thành text có cấu trúc, append vào context trước khi gọi LLM.

**Bằng chứng trước/sau:**

Trước (context chỉ có chunks):
```
=== TÀI LIỆU NỘI BỘ ===
[1] sla_p1_2026.txt (relevance: 0.88)
Ticket P1: SLA phản hồi 15 phút...
```

Sau (context có cả MCP results):
```
=== TÀI LIỆU NỘI BỘ ===
[1] sla_p1_2026.txt (relevance: 0.88)
Ticket P1: SLA phản hồi 15 phút...

=== TICKET INFO (MCP: get_ticket_info) ===
Ticket: IT-9847 | Priority: P1 | Status: in_progress
Created: 2026-04-13T22:47:00 | SLA deadline: 2026-04-14T02:47:00
Notifications: slack:#incident-p1, email:incident@company.internal, pagerduty:oncall

=== ACCESS PERMISSION CHECK (MCP: check_access_permission) ===
Level: 2 | Can grant: True
Required approvers: IT Admin on-call, Tech Lead verbal approval
Emergency override: True
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**

Phần `analyze_policy()` với rule-based exception detection và temporal scoping flag. Đây là phần quan trọng nhất cho câu gq02 (đơn 31/01) và gq10 (Flash Sale + lỗi nhà sản xuất + 7 ngày) — hai câu yêu cầu nhận biết exception chính xác mà không hallucinate.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Chưa có LLM-based policy analysis để xử lý cases phức tạp hơn (ví dụ kết hợp nhiều điều kiện). Confidence estimation hiện tại còn đơn giản (avg chunk score) — chưa dùng LLM-as-Judge như synthesis.py gợi ý.

**Nhóm phụ thuộc vào tôi ở đâu?**

`synthesis_worker` là bước cuối cùng trước khi trả kết quả — nếu nó crash hoặc hallucinate, toàn bộ grading bị ảnh hưởng. Đặc biệt, ABSTAIN logic trong synthesis quyết định điểm câu gq07 (abstain question, 10 điểm).

**Phần tôi phụ thuộc vào thành viên khác:**

- Gia Bách: `AgentState` schema phải đủ fields (`mcp_tools_used`, `needs_tool`) để policy_tool hoạt động đúng.
- Vĩnh Giang: `dispatch_tool()` trong `mcp_server.py` phải trả về đúng format để `_call_mcp_tool()` parse được. Nếu Giang chưa xong, policy_tool vẫn chạy được nhờ `needs_tool=False` fallback.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ thêm **LLM-based confidence calibration** vào `synthesis_worker`. Trace của câu gq09 (multi-hop, 16 điểm) sẽ cho thấy confidence estimate hiện tại (avg chunk score) không phản ánh đúng độ khó — câu cần cross-reference 2 tài liệu nhưng confidence vẫn tính theo score của từng chunk riêng lẻ. Thêm một LLM call ngắn để rate answer quality dựa trên context coverage sẽ cải thiện calibration và giúp HITL trigger đúng hơn cho câu multi-hop.

---

*Lưu file này tại: `reports/individual/doan_nam_son.md`*