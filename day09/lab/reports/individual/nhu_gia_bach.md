# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Nhữ Gia Bách  
**Vai trò trong nhóm:** Supervisor / Graph Architect  
**Ngày nộp:** 14/04/2026

---

## 1. Tôi phụ trách phần nào?

**Module/file tôi chịu trách nhiệm:**
- File chính: `day09/lab/graph.py`
- Functions tôi implement: `make_initial_state`, `supervisor_node`, `route_decision`, `human_review_node`, `_import_worker_run`, `build_graph`, `run_graph`, `save_trace`

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Sprint 1 chuẩn hóa `AgentState`, routing bằng keyword và trace output để Sprint 2 (retrieval/policy/synthesis) biết phải đọc `needs_tool`, `risk_high`, `history` và `supervisor_route`. Cả trace file mà tôi lưu ra (`artifacts/traces/run_20260414_150026.json`) lẫn entry history đều là nguồn dữ kiện cho `eval_trace` và đội docs.

**Bằng chứng:**
- Lệnh kiểm thử: `GRAPH_FORCE_PLACEHOLDERS=1 python3 graph.py` chạy 3 query mẫu, hiển thị route/reason/workers/answer/confidence và ghi trace JSON tương ứng.  
- Code: `state["history"].append({"step": "supervisor", "route": route, "reason": reason})` & `save_trace()` đảm bảo metadata trace đầy đủ.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Triển khai keyword-based routing ở `supervisor_node` thay vì gọi LLM.

**Lý do:** Sprint 1 cần logic nhanh gọn, không phụ thuộc vào day08/OpenAI. Với bộ từ khóa `POLICY_KEYWORDS`, `SLA_KEYWORDS`, `RISK_KEYWORDS`, tôi quyết định gán trực tiếp `route_reason`, `needs_tool`, `risk_high`, `supervisor_route` để routing có thể giải thích được, rồi lưu entry history dạng dict để trace đọc được. `route_decision` sau đó sẽ buộc sang `human_review` nếu `risk_high` hoặc `hitl_triggered`.

**Trade-off đã chấp nhận:** Keyword routing thiếu nuance so với LLM nhưng đổi lại latency gần 0ms (xem trace) và dễ kiểm thử theo sprint timeline. Khi sprint 2 xong, đội mới cân nhắc LLM nâng cấp.

**Bằng chứng từ trace/code:**
```
state["history"].append({"step": "supervisor", "route": route, "reason": reason})
```
Trace `artifacts/traces/run_20260414_150026.json` ghi:
```
"route_reason": "task chứa policy keyword: ['cấp quyền'] | human review override"
```
Phù hợp với kỳ vọng.

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** Trace/ký lục của graph trước đó chỉ ghi chuỗi text, không có boolean `needs_tool`, `risk_high`, và `route_decision` không xét `hitl_triggered`.

**Symptom (pipeline làm gì sai?):** Downstream không biết khi nào cần gọi worker, trace không chứa metadata để `eval_trace` dùng, và route human review luôn bị bỏ qua mặc dù có `risk_high` từ policy.

**Root cause:** Supervisor chỉ cập nhật history dạng chuỗi và `route_decision` trả về `state["supervisor_route"]` mà không kiểm soát flag HTIL/risk. Lỗi nằm ở routing logic mà tôi chịu trách nhiệm.

**Cách sửa:**
- Định nghĩa rõ `POLICY_KEYWORDS`, `SLA_KEYWORDS`, `RISK_KEYWORDS` và gán `needs_tool`, `risk_high`, `route_reason`, `supervisor_route`.  
- `route_decision` trả về `human_review` nếu `risk_high` hoặc `hitl_triggered`.  
- `human_review_node` cài `final_answer`, `confidence`, `sources`, `workers_called`, đồng thời ghi history dict để trace có ngang hàng.  
- Các entry history giờ là dict, tạo điều kiện cho `eval_trace` đọc `step`/`route`/`event`/`latency_ms`.

**Bằng chứng trước/sau:**
Trace `artifacts/traces/run_20260414_150026.json` hiện tại chứa:
```
"history": [
  {"step": "supervisor", "route": "policy_tool_worker", ...},
  {"step": "human_review", "reason": "..."},
  {"step": "graph", "event": "completed", "route": "human_review", "latency_ms": 0}
]
```
so với trước kia chỉ có chuỗi text và thiếu `needs_tool`/`risk_high`, nên bug đã được khắc phục.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào?**
Xây được state chuẩn và trace có cấu trúc giúp cả graph lẫn workers biết điểm neo chung để đọc metadata, routing và latency; trace còn tạo nền tảng cho `eval_trace` và docs vận hành.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Chưa tích hợp các worker thật, hiện vẫn phụ thuộc `GRAPH_FORCE_PLACEHOLDERS`; cần phối hợp để bật `workers/retrieval.py`, `policy_tool`, `synthesis` hoạt động. Chưa có test đa dạng hơn ngoài 3 query.

**Nhóm phụ thuộc vào tôi ở đâu?**
Workers cần `needs_tool`, `risk_high`, `history`, `workers_called` mà tôi chuẩn hóa, nên nếu graph chưa xong thì retrieval/policy/synthesis không thể chạy đúng hoặc trace không có dữ liệu.

**Phần tôi phụ thuộc vào thành viên khác:**
Cần Sprint 2 (Duy/Sơn) hoàn thiện `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py` và MCP server để bật lại pipeline thật.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ tích hợp các worker thực vào `build_graph()` và chạy `python3 graph.py` không dùng `GRAPH_FORCE_PLACEHOLDERS`, vì trace hiện tại cho thấy human-review được trigger (`risk_high`) nên cần kiểm chứng routing vẫn chính xác khi trả về nội dung thật (không phải placeholder) và cập nhật trace JSON mới.
