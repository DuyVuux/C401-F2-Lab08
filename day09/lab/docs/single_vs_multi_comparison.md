# Single Agent vs Multi-Agent Comparison — Lab Day 09

**Nhóm:** C401-F2  
**Ngày:** 2026-04-14

> So sánh Day 08 (single-agent RAG pipeline) với Day 09 (supervisor-worker).  
> Số liệu Day 08 từ scorecard `eval.py` đã chạy. Số liệu Day 09 từ `eval_trace.py` chạy 15 test questions.

---

## 1. Metrics Comparison

| Metric | Day 08 (Single Agent) | Day 09 (Multi-Agent) | Delta | Ghi chú |
|--------|----------------------|---------------------|-------|---------|
| Avg confidence | N/A (LLM-as-Judge 1–5) | 0.53 | N/A | Day 08 dùng judge score, Day 09 dùng cosine avg |
| Avg latency (ms) | ~980ms | 2865ms | +1885ms | Day 09 chạy 2–3 workers + MCP |
| Abstain rate | 20% (2/10 câu) | 13% (2/15 câu) | -7% | Day 09 ít abstain hơn vì policy worker hỗ trợ thêm context |
| Multi-hop accuracy | 1/1 đúng (gq06) | 2/2 đúng (q13, q15) | ±0 | Cả hai đều handle multi-hop tốt |
| Routing visibility | ✗ Không có | ✓ Có `route_reason` + `workers_called` | N/A | Key advantage của Day 09 |
| MCP tool usage | ✗ Không có | 6/15 câu gọi MCP (40%) | N/A | |
| HITL trigger | ✗ Không có | 2/15 câu (13%) | N/A | Low-confidence queries được flag |
| Faithfulness (LLM-Judge) | 4.10/5 | Chưa đo | N/A | |
| Context Recall (LLM-Judge) | 5.00/5 | Chưa đo | N/A | |

---

## 2. Phân tích theo loại câu hỏi

### 2.1 Câu hỏi đơn giản (single-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy (ước tính) | Cao | Cao |
| Latency | ~980ms | ~2100ms |
| Observation | 1 LLM call, trả lời nhanh | 2 worker calls + synthesis, chậm hơn |

**Kết luận:** Với câu hỏi đơn giản (single-doc), Day 08 **nhanh hơn đáng kể** (~2x). Multi-agent không mang lại lợi thế về accuracy mà còn tăng latency do overhead orchestration.

### 2.2 Câu hỏi multi-hop (cross-document)

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Accuracy | 1/1 (gq06, 12 điểm) | 2/2 (q13, q15 cả hai đúng) |
| Routing visible? | ✗ | ✓ — biết rõ worker nào xử lý phần nào |
| MCP support | ✗ | ✓ — gọi `check_access_permission` + `get_ticket_info` |
| Observation | Dense retrieval tự tổng hợp | Policy worker + MCP phân tách rõ vai trò |

**Kết luận:** Multi-agent **không tệ hơn** ở multi-hop và có thêm lợi thế trace rõ ràng. Khi answer sai trong Day 08, không biết lỗi ở retrieval hay generation. Day 09 xem trace là biết ngay.

### 2.3 Câu hỏi cần abstain

| Nhận xét | Day 08 | Day 09 |
|---------|--------|--------|
| Abstain rate | 2/10 (20%) | 2/15 (13%) |
| Hallucination cases | 0 | 0 |
| HITL flag | ✗ | ✓ (confidence=0.0 → hitl_triggered=True) |
| Observation | Model abstain đúng nhưng không có signal | Synthesis worker tự flag để review |

**Kết luận:** Cả hai đều abstain đúng (không hallucinate). Day 09 có thêm HITL signal — operator biết câu nào cần review thủ công mà không cần đọc từng answer.

---

## 3. Debuggability Analysis

### Day 08 — Debug workflow
```
Khi answer sai:
  → Không có trace → phải đọc toàn bộ pipeline code
  → Không biết lỗi ở: indexing? chunking? embedding? retrieval? generation?
  → Phải re-run từng bước thủ công
Thời gian ước tính: 15–20 phút / bug
```

### Day 09 — Debug workflow
```
Khi answer sai → đọc trace (artifacts/traces/run_*.json):
  → supervisor_route sai? → sửa routing keywords trong supervisor_node()
  → retrieved_chunks rỗng? → test retrieval_worker độc lập
  → policy_result sai? → test policy_tool.py --standalone
  → synthesis answer sai dù chunks đúng? → kiểm tra SYSTEM_PROMPT
Thời gian ước tính: 3–5 phút / bug
```

**Câu cụ thể nhóm đã debug trong lab:** Routing bug với query "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp" — ban đầu route sang `human_review` vì `risk_high=True` override. Nhìn trace thấy ngay `supervisor_route=human_review` và `route_reason` chứa "human review override" → fix trong `route_decision()` trong vòng 5 phút.

---

## 4. Extensibility Analysis

| Scenario | Day 08 | Day 09 |
|---------|--------|--------|
| Thêm 1 tool/API mới | Phải sửa system prompt + retry logic | Thêm tool vào `mcp_server.py` + route rule |
| Thêm 1 domain mới | Phải re-prompt toàn bộ | Thêm 1 worker file mới, không đụng worker cũ |
| Thay đổi retrieval strategy | Sửa trực tiếp trong pipeline | Sửa `workers/retrieval.py` độc lập, test riêng |
| A/B test một phần | Khó — phải clone toàn pipeline | Dễ — swap worker trong `graph.py` |

**Nhận xét:** Trong lab này, việc Vũ Đức Duy sửa `retrieval.py` không ảnh hưởng gì đến `policy_tool.py` hay `synthesis.py` — đây là lợi thế rõ ràng của worker isolation.

---

## 5. Cost & Latency Trade-off

| Scenario | Day 08 LLM calls | Day 09 LLM calls |
|---------|-----------------|-----------------|
| Simple query (retrieval) | 1 (generation) | 2 (retrieval embed + synthesis) |
| Complex query (policy) | 1 (generation) | 3 (retrieval embed + MCP check + synthesis) |
| MCP tool call | N/A | +1 nếu search_kb gọi embedding |

**Nhận xét về cost-benefit:** Day 09 tốn ~2–3x LLM calls so với Day 08 cho cùng 1 câu hỏi. Với 15 câu, chi phí API cao hơn rõ rệt. Trade-off này hợp lý khi hệ thống cần **debuggability và extensibility** hơn là tối ưu chi phí — phù hợp với production helpdesk nội bộ, không phù hợp với high-volume consumer chatbot.

---

## 6. Kết luận

**Multi-agent tốt hơn single agent ở:**

1. **Debuggability** — trace rõ ràng (`route_reason`, `workers_called`, `mcp_tools_used`) giảm thời gian debug từ ~20 phút xuống ~5 phút
2. **Extensibility** — thêm MCP tool hoặc worker mới mà không cần sửa code của các phần khác
3. **HITL signal** — tự động flag câu hỏi confidence thấp để human review, thay vì pass answer sai cho user

**Multi-agent không tốt hơn hoặc kém hơn ở:**

1. **Latency** — chậm hơn ~2–3x (2865ms vs ~980ms) do overhead orchestration và nhiều LLM calls
2. **Simple query accuracy** — không cải thiện accuracy với câu hỏi single-doc đơn giản

**Không nên dùng multi-agent khi:**  
Use case có latency budget thấp (<500ms), corpus nhỏ và ít domain, hoặc team chưa có tooling để monitor trace.

**Nếu tiếp tục phát triển:**  
Implement BM25 + RRF hybrid retrieval trong `retrieval_worker`, thêm calibration test set để đo judge bias, và implement MCP HTTP server thật (FastAPI) để tách `mcp_server` ra service độc lập có thể scale riêng.
