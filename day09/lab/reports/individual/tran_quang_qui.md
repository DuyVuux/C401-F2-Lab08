# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Trần Quang Quí  
**Vai trò trong nhóm:** Trace & Docs Owner (Sprint 4)  
**Ngày nộp:** 2026-04-14

---

## 1. Tôi phụ trách phần nào?

Trong lab này, tôi phụ trách toàn bộ Sprint 4 — tầng quan sát và đánh giá của pipeline:

- **`eval_trace.py`**: chạy 15 test questions qua `run_graph()`, lưu trace từng câu vào `artifacts/traces/`, tính metrics tổng hợp (`avg_confidence`, `avg_latency`, `routing_distribution`, `mcp_usage_rate`), xuất `eval_report.json`.
- **`artifacts/traces/`**: 15 trace files từ lần chạy chính thức với toàn bộ fields bắt buộc.
- **`docs/routing_decisions.md`**, **`docs/single_vs_multi_comparison.md`**, **`docs/system_architecture.md`**: điền từ số liệu trace thực tế — không dùng ước đoán.
- **Tích hợp MCP**: phát hiện và fix bug `search_kb` trong `mcp_server.py` của Hoàng Vĩnh Giang (function gọi `retrieve_dense` không tồn tại) để MCP trả về chunks thật thay vì mock data.
- **Fix routing bug** trong `graph.py`: `route_decision()` ban đầu dùng `risk_high=True` để override sang `human_review`, block mọi query emergency. Tôi phát hiện qua trace và sửa để chỉ `hitl_triggered` mới override.

Công việc của tôi kết nối trực tiếp với output của Nhữ Gia Bách (`graph.py`) và Vũ Đức Duy (`retrieval.py`) — `eval_trace.py` import `run_graph()` từ `graph.py` và trace phản ánh toàn bộ output của các workers.

**Bằng chứng:** commit `3615f56` (routing fix), `b36aca4` (MCP fix + traces), `0775a7f` (3 docs).

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Không để `risk_high=True` override route sang `human_review` trong `route_decision()`.

Ban đầu logic trong `graph.py` là:
```python
if state.get("hitl_triggered") or state.get("risk_high"):
    return "human_review"
```

Khi chạy thử query "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp", trace cho thấy:
```json
"supervisor_route": "human_review",
"route_reason": "task chứa policy keyword: ['cấp quyền'] | human review override",
"workers_called": ["human_review"],
"final_answer": "⚠️ Câu hỏi này cần xem xét thủ công..."
```

Câu trả lời sai hoàn toàn — query này nên đi qua `policy_tool_worker` để retrieve access control SOP và gọi MCP `check_access_permission`. Nguyên nhân: `risk_high=True` được set vì task chứa "khẩn cấp", nhưng "khẩn cấp" không có nghĩa là không trả lời được — chỉ cần thêm context từ policy worker.

Tôi sửa thành:
```python
if state.get("hitl_triggered"):
    return "human_review"
return state.get("supervisor_route", "retrieval_worker")
```

HITL chỉ được trigger khi synthesis worker tự set sau khi đã có answer (confidence thấp), không phải ở routing đầu vào.

**Trade-off:** `risk_high` không còn block route — nếu sau này cần hard-block một số loại query ngay từ đầu, phải thêm điều kiện riêng thay vì dùng `risk_high`. Tôi chấp nhận trade-off này vì `risk_high` hiện tại chỉ dùng để log, không có semantic rõ ràng về "không trả lời được".

**Bằng chứng sau khi sửa** — trace query cùng loại:
```json
"supervisor_route": "policy_tool_worker",
"workers_called": ["retrieval_worker", "policy_tool_worker", "synthesis_worker"],
"mcp_tools_used": [{"tool": "check_access_permission"}, {"tool": "get_ticket_info"}],
"confidence": 0.63
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `mcp_server.search_kb` trả về mock data thay vì chunks thật từ ChromaDB.

**Symptom:** Sau khi Hoàng Vĩnh Giang push `mcp_server.py`, tôi chạy test:
```
search_kb chunks: 1 | source: ['mock_data']
```
Kết quả là chunk giả `"[MOCK] Không thể query ChromaDB"` thay vì tài liệu thật.

**Root cause:** `tool_search_kb()` trong `mcp_server.py` gọi:
```python
from workers.retrieval import retrieve_dense
```
Nhưng `workers/retrieval.py` chỉ export function `run(state)` — không có `retrieve_dense`. Khi import fail, code rơi vào `except` và trả về mock data mà không log error rõ ràng.

**Cách sửa:** Thay bằng `_fallback_retrieve()` đã có sẵn trong `retrieval.py`, thêm bước transform output về format MCP chuẩn:
```python
from workers.retrieval import _fallback_retrieve
raw = _fallback_retrieve(query)
chunks = [{"text": c["text"], "source": c["metadata"].get("source", "unknown"),
           "score": c["score"]} for c in raw[:top_k]]
```

**Bằng chứng sau khi sửa:**
```
search_kb chunks: 2 | sources: ['support/sla-p1-2026.pdf']
sample: v2026.1 (2026-01-15): Cập nhật SLA P1 resolution từ 6 giờ xuống 4 giờ...
```

---

## 4. Tôi tự đánh giá đóng góp của mình

**Tôi làm tốt nhất ở điểm nào:** Debug bằng trace. Cả hai bug (routing và MCP search_kb) tôi tìm ra bằng cách đọc trace output — không cần đọc toàn bộ code của người khác. Đây đúng là giá trị của tầng trace mà tôi phụ trách.

**Tôi làm chưa tốt:** Không viết unit test cho `eval_trace.py` trước khi chạy chính thức. Nếu `run_graph()` crash ở giữa 15 câu, tôi mất toàn bộ kết quả. May mắn là pipeline chạy 15/15 thành công lần đầu.

**Nhóm phụ thuộc vào tôi ở đâu:** Toàn bộ `artifacts/traces/` và 3 docs (`routing_decisions`, `single_vs_multi_comparison`, `system_architecture`) là deliverables bắt buộc theo SCORING.md — nếu tôi chưa xong thì nhóm thiếu 10 điểm documentation. Ngoài ra, 2 bug fix của tôi ảnh hưởng trực tiếp đến accuracy của grading run.

**Phần tôi phụ thuộc vào thành viên khác:** Tôi cần `graph.py` của Nhữ Gia Bách export `run_graph()` hoạt động được và `mcp_server.py` của Hoàng Vĩnh Giang có `dispatch_tool()` — cả hai đều có, chỉ cần fix nhỏ là dùng được.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ implement **LLM-as-Judge cho Day 09 trace** — tương tự `eval.py` ở Day 08. Trace hiện tại có `confidence` từ cosine similarity, nhưng chỉ đo độ gần về embedding, không đo answer quality thực sự. Câu q07 (digital product) có `confidence=0.39` và trigger HITL, nhưng answer thực ra đúng — đây là false positive của HITL logic. Nếu có LLM judge chấm Faithfulness và Completeness cho từng trace, tôi có thể chuẩn hóa ngưỡng HITL (`hitl_triggered` khi judge score < 3/5 thay vì cosine < 0.4), giảm false positive rate và có bộ số liệu so sánh thực sự với Day 08 scorecard.
