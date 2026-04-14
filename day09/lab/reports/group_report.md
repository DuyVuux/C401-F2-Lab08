# Báo Cáo Nhóm — Lab Day 09: Multi-Agent Orchestration

**Tên nhóm:** C401-F2  
**Thành viên:**
| Tên | Vai trò | Sprint |
|-----|---------|--------|
| Nhữ Gia Bách | Supervisor / Graph Architect | Sprint 1 |
| Vũ Đức Duy | Retrieval Worker | Sprint 2 |
| Đoàn Nam Sơn | Policy + Synthesis Worker | Sprint 2 |
| Hoàng Vĩnh Giang | MCP Capability | Sprint 3 |
| Trần Quang Quí | Trace & Docs | Sprint 4 |

**Ngày nộp:** 2026-04-14  
**Repo:** https://github.com/DuyVuux/C401-F2-Lab08

---

## 1. Kiến trúc nhóm đã xây dựng

Nhóm xây dựng hệ thống **Supervisor-Worker** bằng Python thuần — không dùng LangGraph library để giữ code đơn giản và dễ trace.

Pipeline gồm 4 thành phần chính:
1. **Supervisor** (`graph.py`) — nhận task, phân tích keyword, quyết định route và set shared state
2. **Retrieval Worker** (`workers/retrieval.py`) — query ChromaDB với `text-embedding-3-small`, trả về top-3 chunks
3. **Policy Tool Worker** (`workers/policy_tool.py`) — detect exception cases (Flash Sale, digital product, temporal scoping), gọi MCP khi cần context bổ sung
4. **Synthesis Worker** (`workers/synthesis.py`) — gọi GPT-4o-mini (`temperature=0`), grounded prompt với abstain logic, tính confidence từ avg cosine score

**Routing logic cốt lõi:** Keyword-based matching trong `supervisor_node()`. Policy keywords (`hoàn tiền`, `refund`, `cấp quyền`, `access`, `flash sale`) → `policy_tool_worker`. SLA keywords (`p1`, `sla`, `ticket`, `escalation`) → `retrieval_worker`. Default → `retrieval_worker`. HITL chỉ trigger khi synthesis confidence < 0.4.

**MCP tools đã tích hợp (`mcp_server.py`):**
- `search_kb`: semantic search ChromaDB qua `_fallback_retrieve()`
- `get_ticket_info`: tra cứu mock ticket data (P1-LATEST với SLA deadline, notifications)
- `check_access_permission`: kiểm tra điều kiện cấp quyền theo level và emergency flag
- `create_ticket`: tạo ticket mock (bonus capability)

---

## 2. Quyết định kỹ thuật quan trọng nhất

**Quyết định:** HITL không override route ở đầu vào — chỉ synthesis worker mới trigger HITL sau khi đã có answer.

**Bối cảnh vấn đề:** Ban đầu `route_decision()` implement như sau:
```python
if state.get("hitl_triggered") or state.get("risk_high"):
    return "human_review"
```
`risk_high` được set `True` khi task chứa keyword "khẩn cấp" hoặc "emergency". Kết quả: query "Contractor cần Level 3 access để khắc phục P1 khẩn cấp" bị route sang `human_review` — trả về warning thay vì answer thực sự.

**Các phương án đã cân nhắc:**

| Phương án | Ưu điểm | Nhược điểm |
|-----------|---------|-----------|
| Giữ `risk_high` override human_review | Đơn giản, an toàn | Block toàn bộ emergency queries — không trả lời được |
| Bỏ `risk_high` khỏi route_decision | Emergency queries đi đúng worker | Mất signal risk để log |
| Chỉ dùng `hitl_triggered` (synthesis set) | HITL chính xác hơn — dựa vào confidence thực | Cần synthesis chạy xong mới biết có HITL không |

**Phương án đã chọn:** Bỏ `risk_high` khỏi `route_decision()`, giữ `risk_high` trong state để log. HITL chỉ trigger khi synthesis trả về `confidence < 0.4`.

**Bằng chứng từ trace — trước khi sửa:**
```json
"supervisor_route": "human_review",
"workers_called": ["human_review"],
"final_answer": "⚠️ Câu hỏi này cần xem xét thủ công..."
```

**Sau khi sửa (gq09 — câu khó nhất):**
```json
"supervisor_route": "policy_tool_worker",
"workers_called": ["retrieval_worker", "policy_tool_worker", "synthesis_worker"],
"mcp_tools_used": [{"tool": "get_ticket_info"}, {"tool": "check_access_permission"}],
"confidence": 0.60
```

---

## 3. Kết quả grading questions

Chạy pipeline với `grading_questions.json` (10 câu), kết quả từ `artifacts/grading_run.jsonl`:

**Tổng điểm raw ước tính:** ~72–80 / 96

| ID | Điểm | Kết quả | Nhận xét |
|----|------|---------|---------|
| gq01 | 10 | ✅ | On-call engineer qua Slack #incident-p1 + email, deadline 4h |
| gq02 | Partial | ⚠️ | Abstain vì đơn 31/01 trước effective date v4 — temporal scoping đúng nhưng có thể miss điểm |
| gq03 | 10 | ✅ | 3 người phê duyệt: Line Manager, IT Admin, IT Security — MCP confirm |
| gq04 | 10 | ✅ | Store credit = 110% tiền gốc |
| gq05 | 8 | ✅ | Escalate lên Senior Engineer sau 10 phút — đúng |
| gq06 | 10 | ✅ | Probation period không được remote — đúng |
| gq07 | 10 | ✅ | Abstain đúng — không có mức phạt tài chính trong tài liệu |
| gq08 | 10 | ✅ | Đổi mật khẩu 90 ngày, cảnh báo trước 7 ngày |
| gq09 | 16 | ✅ | Cross-document: SLA P1 notification + Level 2 emergency access — 2 MCP tools |
| gq10 | 10 | ✅ | Flash Sale không được hoàn tiền dù sản phẩm lỗi — exception đúng |

**Câu pipeline xử lý tốt nhất:** gq09 — câu multi-hop khó nhất (16 điểm). Pipeline gọi đồng thời `get_ticket_info` (P1 SLA context) và `check_access_permission` (Level 2 emergency bypass), synthesis tổng hợp được cả hai quy trình trong một answer có cấu trúc.

**Câu pipeline gặp khó khăn:** gq02 — đơn đặt ngày 31/01/2026, yêu cầu hoàn tiền 07/02/2026. Pipeline detect đúng temporal scoping ("trước 01/02") và flag policy version note, nhưng abstain vì policy v3 không có trong corpus. Confidence = 0.0, HITL triggered. Đây là false abstain — câu hỏi có thể trả lời partial dựa vào policy v4 (7 ngày làm việc, đơn 31/01 + 7 ngày = 09/02 → trễ).

**gq07 (abstain):** Pipeline abstain đúng — tài liệu nội bộ không có mức phạt tài chính cụ thể cho vi phạm SLA P1. Confidence = 0.0, không hallucinate. Đây là behavior đúng theo grounding strategy.

---

## 4. So sánh Day 08 vs Day 09

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta |
|--------|----------------------|---------------------|-------|
| Avg latency | ~980ms | 2865ms | +1885ms |
| Abstain rate | 20% (2/10) | 13% (2/15) | -7% |
| MCP capability | Không có | 6/15 câu gọi MCP | +40% |
| Routing visibility | Không có | 100% có route_reason | N/A |
| HITL signal | Không có | 2/15 câu flagged | N/A |
| Debug time (ước tính) | ~20 phút/bug | ~5 phút/bug | -75% |

**Metric thay đổi rõ nhất:** Latency tăng gần 3x (+1885ms). Nguyên nhân: mỗi câu chạy qua 2–3 workers và có thể thêm MCP call — tổng 2–4 API calls thay vì 1.

**Điều nhóm bất ngờ nhất:** Routing đơn giản (keyword matching) đạt accuracy 100% trên 15 test questions mà không cần LLM classifier. Ban đầu nhóm dự định dùng LLM để classify intent — nhưng với corpus 5 domain rõ ràng, keyword matching đủ nhanh và chính xác hơn.

**Trường hợp multi-agent không giúp ích:** Câu hỏi đơn giản single-doc (gq04: store credit = 110%, gq08: đổi mật khẩu 90 ngày) — Day 08 trả lời nhanh hơn 3x với cùng accuracy. Multi-agent chỉ thật sự có giá trị với câu hỏi policy phức tạp hoặc multi-hop.

---

## 5. Phân công và đánh giá nhóm

| Thành viên | Phần đã làm | Kết quả |
|------------|-------------|---------|
| Nhữ Gia Bách | `graph.py` — AgentState, supervisor_node, routing logic, run_graph() | ✅ Xong Sprint 1, graph chạy end-to-end |
| Vũ Đức Duy | `workers/retrieval.py` — ChromaDB query, fallback retrieve | ✅ Xong Sprint 2, test độc lập được |
| Đoàn Nam Sơn | `workers/policy_tool.py`, `workers/synthesis.py` — LLM call, exception detection | ✅ Xong Sprint 2, 3 exception cases |
| Hoàng Vĩnh Giang | `mcp_server.py` — 4 tools với dispatch_tool() | ✅ Xong Sprint 3, FastAPI HTTP server bonus |
| Trần Quang Quí | `eval_trace.py`, 3 docs, grading run, 2 bug fixes | ✅ Xong Sprint 4, 15/15 traces |

**Điều nhóm làm tốt:** Phân chia sprint rõ ràng theo dependency thực tế — Bách xong trước để Duy và Sơn có AgentState contract. Không ai block nhau quá 30 phút.

**Điều nhóm làm chưa tốt:** Không chốt interface contract trước khi code — `mcp_server.py` export `dispatch_tool()` nhưng `policy_tool.py` import theo cách khác, phát sinh lỗi lúc integration. Fix tốn thêm thời gian.

**Nếu làm lại:** Viết `contracts/worker_contracts.yaml` và test stub trước Sprint 2 — sau đó code workers theo contract đã chốt, không để integration test đến cuối Sprint 4 mới phát hiện mismatch.

---

## 6. Nếu có thêm 1 ngày, nhóm sẽ làm gì?

**Ưu tiên 1 — Fix gq02 (temporal scoping):** Thêm policy v3 vào corpus hoặc implement "version-aware retrieval" — khi query chứa ngày trước 01/02/2026, retrieval worker tự fetch policy version cũ qua MCP tool `get_policy_version(date)`. Trace gq02 cho thấy pipeline detect đúng temporal signal nhưng abstain vì thiếu data — đây là retrieval gap, không phải logic gap.

**Ưu tiên 2 — LLM-as-Judge cho trace:** Tích hợp scoring từ Day 08 (`eval.py`) vào `eval_trace.py` để có Faithfulness và Completeness score thực sự cho từng trace, thay vì chỉ dùng cosine confidence. Điều này cho phép chuẩn hóa ngưỡng HITL (`confidence < 0.4` hiện tại cho false positive ở gq07 — abstain đúng nhưng bị flag HITL).
