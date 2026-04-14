# System Architecture — Lab Day 09

**Nhóm:** C401-F2  
**Ngày:** 2026-04-14  
**Version:** 1.0

---

## 1. Tổng quan kiến trúc

**Pattern đã chọn:** Supervisor-Worker (Python thuần, không dùng LangGraph library)

**Lý do chọn pattern này (thay vì single agent Day 08):**  
RAG pipeline Day 08 gộp retrieve + policy check + generate vào một hàm. Khi pipeline trả lời sai, không rõ lỗi ở tầng nào. Supervisor-Worker tách vai rõ để: (1) test từng worker độc lập, (2) thêm MCP capability mà không sửa core pipeline, (3) có `route_reason` trong trace để debug nhanh.

---

## 2. Sơ đồ Pipeline

```
User Request
     │
     ▼
┌─────────────────────────────────┐
│         Supervisor              │
│  supervisor_node() — graph.py   │
│  ─────────────────────────────  │
│  • Phân tích task               │
│  • Detect keywords              │
│  • Set route, risk_high,        │
│    needs_tool vào AgentState    │
└──────────────┬──────────────────┘
               │ route_decision()
       ┌───────┴────────┐
       │                │
       ▼                ▼
 retrieval_worker  policy_tool_worker
 (SLA, FAQ, HR)    (refund, access,
                    license policy)
       │                │
       │            [MCP call nếu
       │             needs_tool=True]
       │                │
       │           ┌────┘
       │           │   mcp_server.py
       │           │   ├─ search_kb
       │           │   ├─ get_ticket_info
       │           │   └─ check_access_permission
       │           │
       └─────┬─────┘
             │
             ▼
    synthesis_worker
    workers/synthesis.py
    ─────────────────────
    • Gọi GPT-4o-mini (temp=0)
    • Grounded prompt + abstain
    • Tính confidence
    • Flag HITL nếu conf < 0.4
             │
             ▼
         AgentState
    (final_answer, sources,
     confidence, trace, history)
             │
             ▼
      save_trace() → artifacts/traces/
```

---

## 3. Vai trò từng thành phần

### Supervisor (`graph.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Phân tích task, quyết định route, không tự trả lời domain knowledge |
| **Input** | `task` (câu hỏi từ user) |
| **Output** | `supervisor_route`, `route_reason`, `risk_high`, `needs_tool` |
| **Routing logic** | Keyword matching: policy keywords → `policy_tool_worker`; SLA keywords → `retrieval_worker`; default → `retrieval_worker` |
| **HITL condition** | `hitl_triggered=True` (set bởi synthesis khi conf < 0.4) — không override route |

### Retrieval Worker (`workers/retrieval.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Query ChromaDB, trả về top-k chunks liên quan |
| **Embedding model** | `text-embedding-3-small` (OpenAI) |
| **Top-k** | 3 (mặc định) |
| **Fallback** | Tự detect collection name `rag_lab` / `day09_docs` |
| **Stateless?** | Yes — không đọc/ghi state ngoài contract |

### Policy Tool Worker (`workers/policy_tool.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **Nhiệm vụ** | Kiểm tra policy exceptions, gọi MCP khi cần context bổ sung |
| **MCP tools gọi** | `search_kb`, `get_ticket_info`, `check_access_permission` (theo context) |
| **Exception cases** | `flash_sale_exception`, `digital_product_exception`, `activated_product_exception` |
| **Temporal scoping** | Flag đơn trước 01/02/2026 → có thể thuộc policy v3 |

### Synthesis Worker (`workers/synthesis.py`)

| Thuộc tính | Mô tả |
|-----------|-------|
| **LLM model** | `gpt-4o-mini` (fallback: Gemini 1.5 Flash) |
| **Temperature** | 0 (deterministic, grounded) |
| **Grounding strategy** | System prompt: "CHỈ dùng CONTEXT được cung cấp, citation [source] bắt buộc" |
| **Abstain condition** | `retrieved_chunks=[]` và `mcp_tools_used=[]` → abstain phrase |
| **HITL flag** | `confidence < 0.4` → set `hitl_triggered=True` |

### MCP Server (`mcp_server.py`)

| Tool | Input | Output |
|------|-------|--------|
| `search_kb` | `query`, `top_k` | `chunks`, `sources`, `total_found` |
| `get_ticket_info` | `ticket_id` | ticket details, SLA deadline, notifications |
| `check_access_permission` | `access_level`, `requester_role`, `is_emergency` | `can_grant`, `required_approvers`, `emergency_override` |
| `create_ticket` | `priority`, `title`, `description` | `ticket_id`, `url` (MOCK) |

---

## 4. Shared State Schema

| Field | Type | Mô tả | Ai ghi |
|-------|------|-------|--------|
| `task` | str | Câu hỏi đầu vào | make_initial_state |
| `supervisor_route` | str | Worker được chọn | supervisor |
| `route_reason` | str | Lý do route (không để "unknown") | supervisor |
| `risk_high` | bool | Task có rủi ro cao không | supervisor |
| `needs_tool` | bool | Cần gọi MCP không | supervisor |
| `retrieved_chunks` | list | Evidence từ ChromaDB | retrieval_worker |
| `retrieved_sources` | list | Danh sách tên file nguồn | retrieval_worker |
| `policy_result` | dict | Kết quả kiểm tra policy + exceptions | policy_tool_worker |
| `mcp_tools_used` | list | Log các MCP tool calls | policy_tool_worker |
| `final_answer` | str | Câu trả lời cuối với citation | synthesis_worker |
| `confidence` | float | Avg cosine score của chunks (0–1) | synthesis_worker |
| `hitl_triggered` | bool | Flag cần human review | synthesis_worker |
| `workers_called` | list | Sequence của workers đã chạy | mỗi worker |
| `history` | list | Event log toàn flow | mỗi worker |
| `latency_ms` | int | Tổng thời gian xử lý | run_graph() |

---

## 5. Lý do chọn Supervisor-Worker so với Single Agent (Day 08)

| Tiêu chí | Single Agent (Day 08) | Supervisor-Worker (Day 09) |
|----------|----------------------|--------------------------|
| Debug khi sai | Không có trace — phải đọc toàn code | Xem `route_reason` + `workers_called` trong trace |
| Thêm capability mới | Sửa system prompt + retry logic | Thêm MCP tool trong `mcp_server.py` |
| Test một phần | Phải chạy toàn pipeline | `python workers/retrieval.py` độc lập |
| Routing visibility | Không có | `supervisor_route` + `route_reason` mọi run |
| HITL | Không có | Tự flag khi `confidence < 0.4` |

**Quan sát thực tế trong lab:** Bug routing "emergency query → human_review" được phát hiện và fix trong 5 phút nhờ trace. Không có trace thì phải đọc toàn bộ `graph.py` + `route_decision()` để tìm ra logic sai.

---

## 6. Giới hạn và điểm cần cải tiến

1. **Keyword-based routing không scale** — nếu thêm domain mới (e.g., finance, legal), phải cập nhật keyword list thủ công. Cải tiến: dùng LLM classifier nhỏ để route.
2. **BM25 chưa implement** — `retrieval_worker` hiện chỉ dùng dense search. Câu hỏi với exact keyword (mã lỗi, tên sản phẩm) có thể miss. Cải tiến: thêm BM25 + RRF như đã plan ở Day 08.
3. **MCP server là mock in-process** — `dispatch_tool()` gọi trực tiếp trong cùng Python process. Production cần HTTP server riêng (FastAPI) để tách deployment và scale độc lập.
