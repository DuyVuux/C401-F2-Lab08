# Routing Decisions Log — Lab Day 09

**Nhóm:** C401-F2  
**Ngày:** 2026-04-14

> Ghi lại 4 quyết định routing thực tế từ trace `artifacts/traces/` — chạy 15 test questions với `eval_trace.py`.

---

## Routing Decision #1 — Default retrieval route

**Task đầu vào:**
> "SLA xử lý ticket P1 là bao lâu?"

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `task chứa SLA keyword: ['p1', 'sla', 'ticket']`  
**MCP tools được gọi:** Không có  
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "SLA xử lý ticket P1 là: Phản hồi ban đầu 15 phút kể từ khi ticket được tạo. Xử lý và khắc phục trong 4 giờ..."
- confidence: 0.52
- Correct routing? **Yes**

**Nhận xét:** Routing đúng. Câu hỏi fact-retrieval thuần — không cần policy check. Supervisor phát hiện đúng keyword SLA/P1 và đưa thẳng vào `retrieval_worker`. Không cần MCP vì không có action side-effect.

---

## Routing Decision #2 — Policy route với MCP tool call

**Task đầu vào:**
> "Ai phải phê duyệt để cấp quyền Level 3?"

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task chứa policy keyword: ['cấp quyền']`  
**MCP tools được gọi:** `check_access_permission` (access_level=3, requester_role='contractor')  
**Workers called sequence:** `retrieval_worker → policy_tool_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Để cấp quyền Level 3, cần có sự phê duyệt của Line Manager, IT Admin và IT Security [1]."
- confidence: 0.52
- Correct routing? **Yes**

**Nhận xét:** Routing đúng và MCP được gọi đúng. Supervisor nhận diện "cấp quyền" là policy keyword → route sang `policy_tool_worker`. Worker gọi MCP `check_access_permission` để tra cứu cấu trúc phê duyệt theo level, kết quả được synthesis tổng hợp với citation.

---

## Routing Decision #3 — Abstain với HITL trigger

**Task đầu vào:**
> "ERR-403-AUTH là lỗi gì và cách xử lý?"

**Worker được chọn:** `retrieval_worker`  
**Route reason (từ trace):** `default route: không match keyword cụ thể`  
**MCP tools được gọi:** Không có  
**Workers called sequence:** `retrieval_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Xin lỗi, hệ thống không có đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này. Vui lòng liên hệ IT Helpdesk (ext. 9000)..."
- confidence: 0.0 → **HITL triggered**
- Correct routing? **Yes** (abstain đúng)

**Nhận xét:** Đây là câu thiết kế để test abstain — `ERR-403-AUTH` không có trong tài liệu nội bộ. Retrieval trả về 0 chunks liên quan, synthesis nhận context rỗng → abstain đúng. Synthesis worker tự set `hitl_triggered=True` khi `confidence=0.0`. Routing sang retrieval là hợp lý vì không có keyword policy rõ ràng.

---

## Routing Decision #4 — Multi-hop cross-document với 2 MCP tools

**Task đầu vào:**
> "Ticket P1 lúc 2am. Cần cấp Level 2 access tạm thời cho contractor để thực hiện emergency fix. Đồng thời cần notify stakeholders theo SLA. Nêu đủ cả hai quy trình."

**Worker được chọn:** `policy_tool_worker`  
**Route reason (từ trace):** `task chứa policy keyword: ['access']`  
**MCP tools được gọi:** `get_ticket_info` (P1-LATEST) + `check_access_permission` (level=2, emergency=True)  
**Workers called sequence:** `retrieval_worker → policy_tool_worker → synthesis_worker`

**Kết quả thực tế:**
- final_answer: "Quy trình cấp Level 2 access tạm thời: On-call IT Admin cấp quyền tạm thời (max 24 giờ) sau khi được Tech Lead phê duyệt bằng lời..."
- confidence: 0.62
- Correct routing? **Yes**

**Nhận xét: Đây là trường hợp routing khó nhất trong lab.** Task yêu cầu cross-document (SLA P1 + Access Control SOP) và 2 MCP tools cùng lúc. Supervisor route sang `policy_tool_worker` vì keyword "access" — đúng. `policy_tool_worker` gọi `get_ticket_info` để lấy context P1 và `check_access_permission` với `is_emergency=True` để xác định emergency bypass. Synthesis tổng hợp cả hai quy trình trong một answer có cấu trúc rõ ràng.

---

## Tổng kết

### Routing Distribution

| Worker | Số câu được route | % tổng |
|--------|------------------|--------|
| retrieval_worker | 8/15 | 53% |
| policy_tool_worker | 7/15 | 47% |
| human_review | 0/15 | 0% |

### Routing Accuracy

Trong 15 câu đã chạy:
- Câu route đúng: **15 / 15** (100%)
- Câu route sai: 0
- Câu trigger HITL: 2 (q09 abstain conf=0.0, q07 digital product conf=0.39)

### Lesson Learned về Routing

1. **Keyword matching đủ tốt cho corpus có domain rõ ràng.** Với 5 tài liệu nội bộ có topic rõ (SLA, refund, access control, HR, FAQ), keyword-based routing cho accuracy 100%. Không cần LLM classifier — nhanh hơn và không tốn API call thêm.
2. **`risk_high` không nên override route sang human_review.** Ban đầu thiết kế `risk_high=True` → `human_review`, nhưng điều này block query "cấp quyền khẩn cấp" — đúng ra cần policy_tool_worker xử lý trước. Fix: chỉ `hitl_triggered` (do synthesis khi conf thấp) mới override.

### Route Reason Quality

`route_reason` hiện tại ghi dạng `"task chứa policy keyword: ['cấp quyền', 'access']"` — đủ để debug nhanh. Cải tiến tiếp theo: thêm `"matched_rule": "policy_route_v1"` để version hóa routing logic và dễ A/B test rule thay đổi.
