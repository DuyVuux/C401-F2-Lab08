# Phân Công Công Việc — Lab Day 09: Multi-Agent Orchestration

**Nhóm:** C401-F2  
**Deadline code:** 18:00 hôm nay  
**Deadline report:** Sau 18:00 (vẫn được commit)

> **Nguyên tắc:** Không đổi biến đồng thời — fix graph trước, workers sau, MCP sau cùng.  
> **Khi push:** Viết commit message rõ role + sprint, ví dụ: `[gia-bach][sprint1] implement supervisor routing`

---

## Tổng quan phân vai

| Thành viên | Vai trò | Sprint chính | Files sở hữu |
|------------|---------|-------------|--------------|
| **Nhữ Gia Bách** | Supervisor / Graph Architect | Sprint 1 | `graph.py` |
| **Vũ Đức Duy** | Retrieval Worker | Sprint 2 | `workers/retrieval.py` |
| **Đoàn Nam Sơn** | Policy + Synthesis Worker | Sprint 2 | `workers/policy_tool.py`, `workers/synthesis.py`, `contracts/worker_contracts.yaml` |
| **Hoàng Vĩnh Giang** | MCP Capability | Sprint 3 | `mcp_server.py` |
| **Trần Quang Quí** | Trace & Docs | Sprint 4 | `eval_trace.py`, `artifacts/traces/`, `docs/` |

> Ai xong sớm → pull sang hỗ trợ sprint tiếp theo.

---

## Dependency giữa các sprint

```
Sprint 1 — Gia Bách (graph.py skeleton + routing)
    │
    ├── Sprint 2A — Đức Duy (retrieval.py)     ┐ Song song
    └── Sprint 2B — Nam Sơn (policy + synth)   ┘ sau sprint 1 xong
              │
              ├── Sprint 3 — Vĩnh Giang (mcp_server.py)   ┐ Song song
              └── Sprint 4 — Quang Quí (trace + eval)      ┘ sau sprint 2 xong
```

**Gia Bách phải xong trước** để Đức Duy và Nam Sơn biết `AgentState` có những field gì.

---

## Chi tiết từng người

---

### Nhữ Gia Bách — Supervisor / Graph Architect

**Files:** `graph.py`  
**Sprint:** 1 (60 phút đầu)

#### Việc cần làm

**Bước 1 — Hoàn thành `supervisor_node()`** (đã có skeleton, cần implement body):
```python
def supervisor_node(state: AgentState) -> AgentState:
    task = state["task"].lower()

    # Keyword-based routing (không cần LLM)
    POLICY_KEYWORDS = ["hoàn tiền", "refund", "flash sale", "cấp quyền", "access", "license", "digital"]
    SLA_KEYWORDS    = ["p1", "sla", "ticket", "escalation", "sự cố", "incident"]
    RISK_KEYWORDS   = ["emergency", "khẩn cấp", "err-", "không hoạt động"]

    needs_tool = any(k in task for k in POLICY_KEYWORDS)
    risk_high  = any(k in task for k in RISK_KEYWORDS)

    if any(k in task for k in POLICY_KEYWORDS):
        route = "policy_tool_worker"
        reason = f"task chứa policy keyword: {[k for k in POLICY_KEYWORDS if k in task]}"
    elif any(k in task for k in SLA_KEYWORDS):
        route = "retrieval_worker"
        reason = f"task chứa SLA keyword: {[k for k in SLA_KEYWORDS if k in task]}"
    else:
        route = "retrieval_worker"
        reason = "default route: không match keyword cụ thể"

    state["supervisor_route"] = route
    state["route_reason"]     = reason
    state["risk_high"]        = risk_high
    state["needs_tool"]       = needs_tool
    state["history"].append({"step": "supervisor", "route": route, "reason": reason})
    return state
```

**Bước 2 — Implement `route_decision()`**:
```python
def route_decision(state: AgentState) -> Literal["retrieval_worker", "policy_tool_worker", "human_review"]:
    if state["hitl_triggered"] or state["risk_high"]:
        return "human_review"
    return state["supervisor_route"]
```

**Bước 3 — Implement `human_review_node()` (stub)**:
```python
def human_review_node(state: AgentState) -> AgentState:
    state["final_answer"] = "⚠️ Câu hỏi này cần xem xét thủ công do rủi ro cao hoặc context không rõ."
    state["sources"] = []
    state["confidence"] = 0.0
    state["history"].append({"step": "human_review", "reason": state["route_reason"]})
    return state
```

**Bước 4 — Kết nối graph và implement `run_graph()`**:
```python
def run_graph(task: str) -> AgentState:
    import time
    state = make_initial_state(task)
    t0 = time.time()

    state = supervisor_node(state)
    route = route_decision(state)

    if route == "human_review":
        state = human_review_node(state)
    elif route == "policy_tool_worker":
        from workers.retrieval import run as retrieval_run
        from workers.policy_tool import run as policy_run
        from workers.synthesis import run as synthesis_run
        state = retrieval_run(state)
        state = policy_run(state)
        state = synthesis_run(state)
    else:  # retrieval_worker
        from workers.retrieval import run as retrieval_run
        from workers.synthesis import run as synthesis_run
        state = retrieval_run(state)
        state = synthesis_run(state)

    state["latency_ms"] = int((time.time() - t0) * 1000)
    return state
```

**Bước 5 — Test với 3 queries**:
```python
if __name__ == "__main__":
    tests = [
        "Ticket P1 lúc 22:47 — ai nhận thông báo đầu tiên?",
        "Khách hàng yêu cầu hoàn tiền sau Flash Sale 8 ngày",
        "ERR-403-AUTH là lỗi gì?",
    ]
    for q in tests:
        result = run_graph(q)
        print(f"\nQ: {q}")
        print(f"Route: {result['supervisor_route']} — {result['route_reason']}")
        print(f"Answer: {result['final_answer'][:100]}...")
```

**Definition of Done (tự kiểm tra trước khi push):**
- [ ] `python graph.py` chạy không lỗi
- [ ] 3 queries test đều có `supervisor_route` và `route_reason` khác "unknown"
- [ ] `AgentState` có đủ các fields: `supervisor_route`, `route_reason`, `risk_high`, `needs_tool`, `workers_called`, `history`
- [ ] `run_graph()` return state hoàn chỉnh (sẵn sàng cho Quang Quí dùng)

---

### Vũ Đức Duy — Retrieval Worker

**Files:** `workers/retrieval.py`  
**Sprint:** 2 (song song với Nam Sơn, sau khi Gia Bách push graph.py)

#### Bối cảnh

Retrieval worker là wrapper của `rag_answer.py` Day 08 — nhận `task` từ state, query ChromaDB, trả về chunks.

#### Việc cần làm

**Bước 1 — Implement `run(state)`**:

```python
# workers/retrieval.py
import sys
from pathlib import Path
from datetime import datetime
from typing import Any

# Thêm Day 08 vào path để dùng lại retrieve_dense
_ROOT = str(Path(__file__).parents[5])  # /Users/.../C401-F2-Lab08
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

TOP_K = 3

def run(state: dict) -> dict:
    task = state.get("task", "")
    log_entry = {
        "worker": "retrieval_worker",
        "input": {"task": task, "top_k": TOP_K},
        "timestamp": datetime.now().isoformat(),
    }

    try:
        from day08.lab.src.retrieval.rag_answer import retrieve_dense
        chunks = retrieve_dense(task, top_k=TOP_K)
    except Exception as e:
        # Fallback nếu Day 08 không load được
        chunks = _fallback_retrieve(task)
        log_entry["warning"] = f"Day08 import failed, using fallback: {e}"

    sources = list({c["metadata"].get("source", "unknown") for c in chunks})
    log_entry["output"] = {"chunks_count": len(chunks), "sources": sources}

    state["retrieved_chunks"]  = chunks
    state["retrieved_sources"] = sources
    state["workers_called"]    = state.get("workers_called", []) + ["retrieval_worker"]
    state["history"].append({"step": "retrieval_worker", **log_entry})

    if not hasattr(state.get("worker_io_logs"), "append"):
        state["worker_io_logs"] = []
    state["worker_io_logs"].append(log_entry)

    return state


def _fallback_retrieve(task: str) -> list:
    """Fallback: đọc trực tiếp ChromaDB local nếu Day 08 import fail."""
    try:
        import chromadb
        from pathlib import Path
        import os
        from openai import OpenAI

        db_path = Path(__file__).parents[2] / "chroma_db"
        client = chromadb.PersistentClient(path=str(db_path))
        col = client.get_collection("day09_docs")

        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        embedding = openai_client.embeddings.create(
            input=task, model="text-embedding-3-small"
        ).data[0].embedding

        results = col.query(query_embeddings=[embedding], n_results=3,
                            include=["documents", "metadatas", "distances"])
        chunks = []
        for doc, meta, dist in zip(results["documents"][0],
                                   results["metadatas"][0],
                                   results["distances"][0]):
            chunks.append({"text": doc, "metadata": meta, "score": round(1 - dist, 4)})
        return chunks
    except Exception:
        return []
```

**Bước 2 — Test độc lập**:
```bash
cd day09/lab
python -c "
from workers.retrieval import run
state = {'task': 'SLA ticket P1 deadline là bao lâu?', 'history': [], 'workers_called': []}
result = run(state)
print(f'Chunks: {len(result[\"retrieved_chunks\"])}')
print(f'Sources: {result[\"retrieved_sources\"]}')
"
```

**Definition of Done:**
- [ ] `run(state)` test độc lập trả về ít nhất 1 chunk cho query SLA/refund
- [ ] `retrieved_sources` là list tên file (không phải full path)
- [ ] `workers_called` có "retrieval_worker" sau khi chạy
- [ ] Nếu ChromaDB trống → `retrieved_chunks = []`, không crash

---

### Đoàn Nam Sơn — Policy + Synthesis Worker

**Files:** `workers/policy_tool.py`, `workers/synthesis.py`, `contracts/worker_contracts.yaml`  
**Sprint:** 2 (song song với Đức Duy)

#### Việc cần làm — Policy Tool Worker

**Bước 1 — Implement `run(state)` trong `workers/policy_tool.py`**:

```python
# workers/policy_tool.py
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

EXCEPTION_KEYWORDS = {
    "flash_sale": ["flash sale", "khuyến mãi đặc biệt"],
    "digital_product": ["sản phẩm số", "license", "key", "activation"],
    "activated_product": ["đã kích hoạt", "already activated"],
}

def run(state: dict) -> dict:
    task       = state.get("task", "")
    chunks     = state.get("retrieved_chunks", [])
    needs_tool = state.get("needs_tool", False)
    log_entry  = {"worker": "policy_tool_worker",
                  "input": {"task": task, "chunks_count": len(chunks)},
                  "timestamp": datetime.now().isoformat()}

    # Detect exceptions từ task text
    exceptions_found = []
    for exc_type, keywords in EXCEPTION_KEYWORDS.items():
        if any(k in task.lower() for k in keywords):
            exceptions_found.append({"type": exc_type, "detected_from": "task_text"})

    # Gọi MCP nếu needs_tool
    mcp_tools_used = []
    if needs_tool:
        try:
            from mcp_server import MCPServer
            mcp = MCPServer()
            result = mcp.dispatch_tool("search_kb", {"query": task, "top_k": 3})
            mcp_tools_used.append({"tool": "search_kb", "result_chunks": len(result.get("chunks", []))})
            # Merge MCP chunks vào retrieved_chunks
            for c in result.get("chunks", []):
                if c not in chunks:
                    chunks.append(c)
        except Exception as e:
            mcp_tools_used.append({"tool": "search_kb", "error": str(e)})

    # Xác định policy_applies dựa trên chunks
    policy_applies = bool(chunks)
    sources = list({c["metadata"].get("source", "") for c in chunks if "metadata" in c})

    policy_result = {
        "policy_applies": policy_applies,
        "exceptions_found": exceptions_found,
        "source": sources,
        "policy_version_note": "",
    }

    log_entry["output"] = {"policy_applies": policy_applies, "exceptions": len(exceptions_found)}

    state["policy_result"]   = policy_result
    state["mcp_tools_used"]  = state.get("mcp_tools_used", []) + mcp_tools_used
    state["retrieved_chunks"] = chunks
    state["workers_called"]  = state.get("workers_called", []) + ["policy_tool_worker"]
    state["history"].append({"step": "policy_tool_worker", **log_entry})
    return state
```

**Bước 2 — Implement `run(state)` trong `workers/synthesis.py`**:

```python
# workers/synthesis.py
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ABSTAIN_PHRASE = "Xin lỗi, hệ thống không có đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này."

SYSTEM_PROMPT = """Bạn là trợ lý nội bộ cho bộ phận CS và IT Helpdesk.
Chỉ trả lời dựa trên CONTEXT được cung cấp. KHÔNG dùng kiến thức bên ngoài.
Nếu context không đủ → trả lời đúng một câu: "{abstain}"
Khi trả lời, thêm citation [tên_file] sau mỗi thông tin quan trọng.""".format(abstain=ABSTAIN_PHRASE)

def run(state: dict) -> dict:
    task   = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    policy = state.get("policy_result", {})
    log_entry = {"worker": "synthesis_worker",
                 "input": {"task": task, "chunks_count": len(chunks)},
                 "timestamp": datetime.now().isoformat()}

    if not chunks:
        state["final_answer"] = ABSTAIN_PHRASE
        state["sources"]      = []
        state["confidence"]   = 0.0
        state["workers_called"] = state.get("workers_called", []) + ["synthesis_worker"]
        log_entry["output"] = {"abstained": True}
        state["history"].append({"step": "synthesis_worker", **log_entry})
        return state

    # Build context string
    context_parts = []
    for i, chunk in enumerate(chunks[:5], 1):
        src = chunk.get("metadata", {}).get("source", "unknown")
        context_parts.append(f"[{i}] Source: {src}\n{chunk['text']}")

    # Thêm policy exceptions nếu có
    exceptions = policy.get("exceptions_found", [])
    if exceptions:
        exc_note = "Lưu ý exceptions: " + ", ".join(e["type"] for e in exceptions)
        context_parts.append(exc_note)

    context = "\n\n---\n\n".join(context_parts)
    user_msg = f"Context:\n{context}\n\nCâu hỏi: {task}"

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp   = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    )
    answer = resp.choices[0].message.content.strip()

    sources    = list({c.get("metadata", {}).get("source", "") for c in chunks})
    confidence = min(1.0, max(0.0, sum(c.get("score", 0.5) for c in chunks) / len(chunks)))

    log_entry["output"] = {"answer_length": len(answer), "confidence": round(confidence, 2)}

    state["final_answer"]   = answer
    state["sources"]        = sources
    state["confidence"]     = round(confidence, 2)
    state["workers_called"] = state.get("workers_called", []) + ["synthesis_worker"]
    state["history"].append({"step": "synthesis_worker", **log_entry})
    return state
```

**Bước 3 — Update `contracts/worker_contracts.yaml`**:  
Tìm phần `actual_implementation` của `policy_tool_worker` và `synthesis_worker`, đổi `status: "TODO Sprint 2"` → `status: "done"`.

**Definition of Done:**
- [ ] Policy worker detect đúng Flash Sale exception từ task text
- [ ] Synthesis worker abstain đúng khi `retrieved_chunks = []`
- [ ] Synthesis answer có citation `[tên_file]`
- [ ] `workers_called` có "policy_tool_worker" và/hoặc "synthesis_worker"

---

### Hoàng Vĩnh Giang — MCP Capability

**Files:** `mcp_server.py`  
**Sprint:** 3 (sau khi workers xong)

#### Bối cảnh

MCP Server expose tools qua `dispatch_tool()`. Policy worker sẽ gọi `mcp.dispatch_tool("search_kb", {...})`. Không cần HTTP server — mock class Python là đủ.

#### Việc cần làm

**Bước 1 — Implement MCPServer class với ít nhất 2 tools**:

File `mcp_server.py` đã có skeleton. Implement phần còn thiếu:

```python
class MCPServer:
    def list_tools(self) -> list:
        """Trả về danh sách tools available — format MCP chuẩn."""
        return [
            {
                "name": "search_kb",
                "description": "Tìm kiếm trong Knowledge Base nội bộ",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 3}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_ticket_info",
                "description": "Lấy thông tin ticket theo ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string"}
                    },
                    "required": ["ticket_id"]
                }
            },
            {
                "name": "check_access_permission",
                "description": "Kiểm tra điều kiện cấp quyền truy cập",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "access_level": {"type": "integer"},
                        "requester_role": {"type": "string"},
                        "is_emergency": {"type": "boolean", "default": False}
                    },
                    "required": ["access_level", "requester_role"]
                }
            }
        ]

    def dispatch_tool(self, tool_name: str, inputs: dict) -> dict:
        """Route tool call đến handler tương ứng."""
        handlers = {
            "search_kb":               self._tool_search_kb,
            "get_ticket_info":         self._tool_get_ticket_info,
            "check_access_permission": self._tool_check_access_permission,
        }
        if tool_name not in handlers:
            return {"error": {"code": "TOOL_NOT_FOUND", "reason": f"Tool '{tool_name}' không tồn tại"}}
        try:
            return handlers[tool_name](inputs)
        except Exception as e:
            return {"error": {"code": "TOOL_EXECUTION_ERROR", "reason": str(e)}}

    def _tool_search_kb(self, inputs: dict) -> dict:
        """Tìm kiếm ChromaDB — reuse logic từ retrieval worker."""
        query = inputs.get("query", "")
        top_k = inputs.get("top_k", 3)
        try:
            # Thử dùng Day 08 retrieve
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parents[4]))
            from day08.lab.src.retrieval.rag_answer import retrieve_dense
            chunks = retrieve_dense(query, top_k=top_k)
        except Exception:
            chunks = []
        sources = list({c.get("metadata", {}).get("source", "") for c in chunks})
        return {"chunks": chunks, "sources": sources, "total_found": len(chunks)}

    def _tool_get_ticket_info(self, inputs: dict) -> dict:
        """Mock ticket data — không cần DB thật."""
        ticket_id = inputs.get("ticket_id", "")
        mock_tickets = {
            "P1-LATEST": {
                "ticket_id": "P1-20260413-001",
                "priority": "P1",
                "status": "open",
                "assignee": "IT On-call",
                "created_at": "2026-04-13T22:47:00",
                "sla_deadline": "2026-04-14T02:47:00",
                "notifications_sent": ["on-call engineer", "IT Manager via PagerDuty"],
            }
        }
        return mock_tickets.get(ticket_id, {
            "ticket_id": ticket_id,
            "status": "not_found",
            "note": "Ticket không tồn tại trong mock data",
        })

    def _tool_check_access_permission(self, inputs: dict) -> dict:
        """Mock access control rules từ access-control-sop."""
        level     = inputs.get("access_level", 1)
        role      = inputs.get("requester_role", "unknown")
        emergency = inputs.get("is_emergency", False)
        if emergency and level <= 2:
            return {
                "can_grant": True,
                "required_approvers": ["IT Admin on-call", "Tech Lead verbal approval"],
                "emergency_override": True,
                "notes": ["Phải log vào Security Audit", "Revoke trong 24h"],
                "source": "access-control-sop.txt",
            }
        return {
            "can_grant": level == 1,
            "required_approvers": ["IT Admin"] if level == 1 else ["IT Admin", "Department Head", "Security Officer"],
            "emergency_override": False,
            "notes": [],
            "source": "access-control-sop.txt",
        }
```

**Bước 2 — Test MCPServer**:
```bash
cd day09/lab
python -c "
from mcp_server import MCPServer
mcp = MCPServer()
print('Tools:', [t['name'] for t in mcp.list_tools()])
r = mcp.dispatch_tool('get_ticket_info', {'ticket_id': 'P1-LATEST'})
print('Ticket:', r)
r2 = mcp.dispatch_tool('check_access_permission', {'access_level': 2, 'requester_role': 'contractor', 'is_emergency': True})
print('Access:', r2)
r3 = mcp.dispatch_tool('unknown_tool', {})
print('Error handling:', r3)
"
```

**Bước 3 — Update `contracts/worker_contracts.yaml`**:  
Tìm `mcp_server.actual_implementation.status` → đổi thành `"done"`.

**Definition of Done:**
- [ ] `list_tools()` trả về ít nhất 2 tools với đúng schema
- [ ] `dispatch_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})` trả về mock data đúng
- [ ] `dispatch_tool("check_access_permission", {..., "is_emergency": True})` trả về `emergency_override: True`
- [ ] `dispatch_tool("unknown_tool", {})` trả về `{"error": {...}}` (không crash)
- [ ] Policy worker `policy_tool.py` gọi được MCPServer thành công

---

### Trần Quang Quí — Trace & Docs

**Files:** `eval_trace.py`, `artifacts/traces/`, `docs/routing_decisions.md`, `docs/single_vs_multi_comparison.md`, `docs/system_architecture.md`  
**Sprint:** 4 (sau khi sprint 2+3 xong)

#### Việc cần làm

**Bước 1 — Implement `eval_trace.py`**:

```python
# eval_trace.py
import json
import csv
import time
from pathlib import Path
from datetime import datetime
from graph import run_graph  # import từ Gia Bách

TRACES_DIR = Path("artifacts/traces")
TRACES_DIR.mkdir(parents=True, exist_ok=True)

def run_test_questions(questions_path: str = "data/test_questions.json") -> list:
    """Chạy pipeline với tất cả test questions, lưu trace."""
    with open(questions_path, encoding="utf-8") as f:
        questions = json.load(f)

    results = []
    for q in questions:
        print(f"Running {q['id']}: {q['question'][:60]}...")
        t0 = time.time()
        try:
            state   = run_graph(q["question"])
            latency = int((time.time() - t0) * 1000)
            record  = {
                "id":               q["id"],
                "question":         q["question"],
                "expected_sources": q.get("expected_sources", []),
                "answer":           state["final_answer"],
                "sources":          state["sources"],
                "supervisor_route": state["supervisor_route"],
                "route_reason":     state["route_reason"],
                "workers_called":   state["workers_called"],
                "mcp_tools_used":   state.get("mcp_tools_used", []),
                "confidence":       state["confidence"],
                "hitl_triggered":   state.get("hitl_triggered", False),
                "latency_ms":       latency,
                "timestamp":        datetime.now().isoformat(),
                "status":           "ok",
            }
        except Exception as e:
            record = {
                "id": q["id"], "question": q["question"],
                "answer": f"PIPELINE_ERROR: {e}",
                "status": "error", "timestamp": datetime.now().isoformat(),
            }
        results.append(record)

    # Lưu trace file
    trace_path = TRACES_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    with open(trace_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nTrace saved: {trace_path}")
    return results


def run_grading(questions_path: str = "data/grading_questions.json"):
    """Chạy grading questions, lưu grading_run.jsonl theo format SCORING.md."""
    results = run_test_questions(questions_path)
    out_path = Path("artifacts/grading_run.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Grading run saved: {out_path}")
    return results


def analyze_trace(trace_path: str) -> dict:
    """Đọc trace file, tính metrics cơ bản."""
    records = []
    with open(trace_path, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))

    total    = len(records)
    ok_count = sum(1 for r in records if r.get("status") == "ok")
    abstains = sum(1 for r in records if "không có đủ thông tin" in r.get("answer", "").lower())
    hitl     = sum(1 for r in records if r.get("hitl_triggered", False))

    route_dist = {}
    for r in records:
        route = r.get("supervisor_route", "unknown")
        route_dist[route] = route_dist.get(route, 0) + 1

    avg_latency = sum(r.get("latency_ms", 0) for r in records if r.get("latency_ms")) / max(ok_count, 1)
    avg_conf    = sum(r.get("confidence", 0) for r in records if r.get("confidence")) / max(ok_count, 1)

    metrics = {
        "total":            total,
        "success_rate":     f"{ok_count/total:.1%}",
        "abstain_rate":     f"{abstains/total:.1%}",
        "hitl_rate":        f"{hitl/total:.1%}",
        "avg_latency_ms":   round(avg_latency),
        "avg_confidence":   round(avg_conf, 2),
        "route_distribution": route_dist,
    }

    print("\n=== Trace Analysis ===")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    return metrics


def compare_single_vs_multi(trace_path: str, day08_scorecard: dict = None):
    """So sánh Day 08 single agent vs Day 09 multi-agent."""
    metrics = analyze_trace(trace_path)

    # Day 08 baseline (từ scorecard thực tế)
    if day08_scorecard is None:
        day08_scorecard = {
            "faithfulness": 4.10,
            "answer_relevance": 4.20,
            "context_recall": 5.00,
            "completeness": 4.30,
            "abstain_rate": "20%",
            "avg_latency_ms": 980,
        }

    print("\n=== Single (Day 08) vs Multi-Agent (Day 09) ===")
    print(f"{'Metric':<25} {'Day 08':>12} {'Day 09':>12}")
    print("-" * 50)
    print(f"{'Abstain rate':<25} {day08_scorecard['abstain_rate']:>12} {metrics['abstain_rate']:>12}")
    print(f"{'Avg latency (ms)':<25} {day08_scorecard['avg_latency_ms']:>12} {metrics['avg_latency_ms']:>12}")
    print(f"{'Route visibility':<25} {'None':>12} {'Full trace':>12}")
    print(f"{'Debuggability':<25} {'Low':>12} {'High':>12}")
    return metrics


if __name__ == "__main__":
    print("=== Running 15 test questions ===")
    results = run_test_questions("data/test_questions.json")

    # Tìm trace file mới nhất
    traces = sorted(TRACES_DIR.glob("*.jsonl"))
    if traces:
        print("\n=== Analyzing latest trace ===")
        metrics = compare_single_vs_multi(str(traces[-1]))
```

**Bước 2 — Điền 3 docs templates**:

Xem trace thực tế từ kết quả chạy, sau đó điền vào:
- [docs/routing_decisions.md](docs/routing_decisions.md) — lấy ít nhất 3 routing decisions thực tế từ trace
- [docs/single_vs_multi_comparison.md](docs/single_vs_multi_comparison.md) — điền metrics từ `compare_single_vs_multi()`
- [docs/system_architecture.md](docs/system_architecture.md) — mô tả kiến trúc

**Bước 3 — Chạy grading_questions.json lúc 17:00**:
```bash
python eval_trace.py  # hoặc:
python -c "from eval_trace import run_grading; run_grading('data/grading_questions.json')"
```

**Definition of Done:**
- [ ] `python eval_trace.py` chạy không crash với 15 test questions
- [ ] `artifacts/traces/` có ít nhất 1 `.jsonl` file
- [ ] `artifacts/grading_run.jsonl` có đủ fields: `id`, `answer`, `supervisor_route`, `route_reason`, `workers_called`, `timestamp`
- [ ] 3 docs files điền xong với số liệu thực (không để placeholder)
- [ ] Báo cáo cá nhân viết xong tại `reports/individual/tran_quang_qui.md`

---

## Timeline & Sync points

```
T+0h00   Gia Bách bắt đầu graph.py skeleton
T+0h45   Gia Bách push graph.py → Đức Duy + Nam Sơn bắt đầu workers
T+1h30   Đức Duy + Nam Sơn push workers → Vĩnh Giang bắt đầu MCP
T+2h00   Quang Quí bắt đầu eval_trace.py (dùng graph + workers đã có)
T+2h30   Vĩnh Giang push mcp_server.py → Nam Sơn integrate MCP vào policy_tool
T+3h00   Full integration test: python graph.py với 3 queries phức tạp
T+3h30   Quang Quí chạy 15 test questions, bắt đầu điền docs
T+4h00   Tất cả commit + push code trước 17:00
T+4h00   Chờ grading_questions.json public lúc 17:00
T+4h30   Quang Quí chạy grading_questions, commit grading_run.jsonl trước 18:00
After    Mỗi người viết báo cáo cá nhân (sau 18:00 vẫn được commit)
```

---

## Checklist nhóm trước 18:00

- [ ] `python graph.py` chạy không lỗi
- [ ] `python eval_trace.py` chạy end-to-end, tạo được trace file
- [ ] `artifacts/grading_run.jsonl` có đủ 10 câu grading
- [ ] `contracts/worker_contracts.yaml` — tất cả `actual_implementation.status = "done"`
- [ ] `docs/system_architecture.md` — điền xong
- [ ] `docs/routing_decisions.md` — có ít nhất 3 routing decisions thực tế
- [ ] `docs/single_vs_multi_comparison.md` — có ít nhất 2 metrics so sánh
- [ ] `reports/group_report.md` — điền xong

---

## Câu hỏi thường gặp

**Import Day 08 bị lỗi?**  
→ Dùng `_fallback_retrieve()` trong `workers/retrieval.py` — tự query ChromaDB local.

**ChromaDB chưa có data?**  
→ Build nhanh index: `cd day09/lab && python -c "from workers.retrieval import _fallback_retrieve; print(_fallback_retrieve('test'))"` — nếu lỗi thì copy `chroma_db/` từ `day08/lab/`.

**MCP chưa xong mà cần test synthesis?**  
→ Set `needs_tool=False` trong state, policy worker sẽ skip MCP call.

**Graph chưa xong mà cần test worker?**  
→ Test worker với mock state: `state = {"task": "...", "history": [], "workers_called": []}`.
