"""
workers/policy_tool.py — Policy & Tool Worker
Sprint 2B: Đoàn Nam Sơn

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: context từ retrieval_worker
    - needs_tool: True nếu supervisor quyết định cần tool call

Output (vào AgentState):
    - policy_result: {policy_applies, policy_name, exceptions_found, source, policy_version_note}
    - mcp_tools_used: list of tool calls đã thực hiện
    - worker_io_logs: log

Gọi độc lập để test:
    python workers/policy_tool.py
"""

import os
from datetime import datetime

WORKER_NAME = "policy_tool_worker"

# ─────────────────────────────────────────────
# Exception keyword mapping (rule-based, không cần LLM)
# ─────────────────────────────────────────────

EXCEPTION_RULES = [
    {
        "type": "flash_sale_exception",
        "keywords": ["flash sale", "khuyến mãi đặc biệt", "flash_sale"],
        "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, policy_refund_v4).",
        "source": "policy_refund_v4.txt",
        "policy_applies": False,
    },
    {
        "type": "digital_product_exception",
        "keywords": ["sản phẩm số", "kỹ thuật số", "license key", "license", "subscription", "activation code"],
        "rule": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền (Điều 3).",
        "source": "policy_refund_v4.txt",
        "policy_applies": False,
    },
    {
        "type": "activated_product_exception",
        "keywords": ["đã kích hoạt", "already activated", "đã đăng ký", "đã sử dụng"],
        "rule": "Sản phẩm đã kích hoạt hoặc đăng ký tài khoản không được hoàn tiền (Điều 3).",
        "source": "policy_refund_v4.txt",
        "policy_applies": False,
    },
]

# Keywords cảnh báo temporal scoping — đơn trước effective date của v4
TEMPORAL_SCOPE_SIGNALS = ["31/01", "30/01", "29/01", "trước 01/02", "trước ngày 01/02"]


# ─────────────────────────────────────────────
# MCP Client
# ─────────────────────────────────────────────

def _call_mcp_tool(tool_name: str, tool_input: dict) -> dict:
    """Gọi MCP tool qua dispatch_tool() từ mcp_server.py."""
    try:
        from mcp_server import dispatch_tool
        result = dispatch_tool(tool_name, tool_input)
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": result,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": None,
            "error": {"code": "MCP_CALL_FAILED", "reason": str(e)},
            "timestamp": datetime.now().isoformat(),
        }


# ─────────────────────────────────────────────
# Policy Analysis
# ─────────────────────────────────────────────

def analyze_policy(task: str, chunks: list) -> dict:
    """
    Phân tích policy dựa trên task text và retrieved context.

    Logic:
    1. Rule-based exception detection từ task keywords (nhanh, không cần LLM)
    2. Cross-check với context chunks nếu cần
    3. Flag temporal scoping nếu đơn trước 01/02/2026

    Returns:
        dict: policy_applies, policy_name, exceptions_found, source, policy_version_note
    """
    task_lower = task.lower()
    context_text = " ".join(c.get("text", "") for c in chunks).lower()

    exceptions_found = []

    # Kiểm tra từng exception rule
    for rule in EXCEPTION_RULES:
        hit_in_task = any(kw in task_lower for kw in rule["keywords"])
        hit_in_context = any(kw in context_text for kw in rule["keywords"])
        if hit_in_task or hit_in_context:
            exceptions_found.append({
                "type": rule["type"],
                "rule": rule["rule"],
                "source": rule["source"],
                "detected_from": "task_text" if hit_in_task else "context",
            })

    # policy_applies = False nếu có bất kỳ blocking exception nào
    policy_applies = len(exceptions_found) == 0

    # Temporal scoping check
    policy_version_note = ""
    if any(signal in task_lower for signal in TEMPORAL_SCOPE_SIGNALS):
        policy_version_note = (
            "⚠️ Đơn hàng có thể đặt trước ngày 01/02/2026 — "
            "áp dụng policy v3, không phải v4. "
            "Tài liệu hiện tại chỉ có v4. CS Team cần xác nhận với policy v3."
        )

    sources = list({c.get("source", "unknown") for c in chunks if c.get("source")})
    if not sources:
        sources = ["policy_refund_v4.txt"]  # default nếu không có chunks

    return {
        "policy_applies": policy_applies,
        "policy_name": "refund_policy_v4",
        "exceptions_found": exceptions_found,
        "source": sources,
        "policy_version_note": policy_version_note,
    }


# ─────────────────────────────────────────────
# Worker Entry Point
# ─────────────────────────────────────────────

def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.

    Flow:
    1. Nếu chưa có chunks và needs_tool → gọi MCP search_kb để lấy thêm context
    2. Phân tích policy dựa trên chunks
    3. Nếu task liên quan ticket/P1 và needs_tool → gọi MCP get_ticket_info thêm
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    needs_tool = state.get("needs_tool", False)

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state.setdefault("mcp_tools_used", [])
    state.setdefault("worker_io_logs", [])

    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "needs_tool": needs_tool,
        },
        "output": None,
        "error": None,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Step 1: Nếu không có chunks và needs_tool → MCP search_kb
        if not chunks and needs_tool:
            mcp_result = _call_mcp_tool("search_kb", {"query": task, "top_k": 3})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append({
                "step": WORKER_NAME,
                "event": "mcp_call",
                "tool": "search_kb",
                "success": mcp_result["error"] is None,
            })
            if mcp_result.get("output") and mcp_result["output"].get("chunks"):
                chunks = mcp_result["output"]["chunks"]
                state["retrieved_chunks"] = chunks

        # Step 2: Phân tích policy
        policy_result = analyze_policy(task, chunks)
        state["policy_result"] = policy_result

        # Step 3: Gọi MCP get_ticket_info nếu task liên quan ticket/P1
        task_lower = task.lower()
        if needs_tool and any(kw in task_lower for kw in ["ticket", "p1", "jira", "incident", "22:47"]):
            mcp_result = _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append({
                "step": WORKER_NAME,
                "event": "mcp_call",
                "tool": "get_ticket_info",
                "success": mcp_result["error"] is None,
            })

        # Step 4: check_access_permission nếu task liên quan cấp quyền
        if needs_tool and any(kw in task_lower for kw in ["cấp quyền", "access level", "level 2", "level 3"]):
            # Extract level từ task
            level = 3
            if "level 2" in task_lower:
                level = 2
            elif "level 1" in task_lower:
                level = 1
            is_emergency = any(kw in task_lower for kw in ["khẩn cấp", "emergency", "p1", "2am"])
            mcp_result = _call_mcp_tool(
                "check_access_permission",
                {"access_level": level, "requester_role": "contractor", "is_emergency": is_emergency}
            )
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append({
                "step": WORKER_NAME,
                "event": "mcp_call",
                "tool": "check_access_permission",
                "success": mcp_result["error"] is None,
            })

        worker_io["output"] = {
            "policy_applies": policy_result["policy_applies"],
            "exceptions_count": len(policy_result.get("exceptions_found", [])),
            "mcp_calls": len(state["mcp_tools_used"]),
            "policy_version_note": bool(policy_result.get("policy_version_note")),
        }

        state["history"].append({
            "step": WORKER_NAME,
            "event": "completed",
            "policy_applies": policy_result["policy_applies"],
            "exceptions": [e["type"] for e in policy_result.get("exceptions_found", [])],
        })

    except Exception as e:
        worker_io["error"] = {"code": "POLICY_CHECK_FAILED", "reason": str(e)}
        state["policy_result"] = {"error": str(e), "policy_applies": False, "exceptions_found": []}
        state["history"].append({"step": WORKER_NAME, "event": "error", "reason": str(e)})

    state["worker_io_logs"].append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("Policy Tool Worker — Standalone Test (Sprint 2B)")
    print("=" * 55)

    test_cases = [
        {
            "name": "Flash Sale exception",
            "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
            "retrieved_chunks": [
                {"text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.91}
            ],
        },
        {
            "name": "Digital product exception",
            "task": "Khách hàng muốn hoàn tiền license key đã kích hoạt.",
            "retrieved_chunks": [
                {"text": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.88}
            ],
        },
        {
            "name": "Valid refund",
            "task": "Khách hàng yêu cầu hoàn tiền trong 5 ngày, sản phẩm lỗi nhà sản xuất, chưa kích hoạt.",
            "retrieved_chunks": [
                {"text": "Yêu cầu trong 7 ngày làm việc, sản phẩm lỗi nhà sản xuất, chưa dùng.", "source": "policy_refund_v4.txt", "score": 0.85}
            ],
        },
        {
            "name": "Temporal scoping (policy v3 edge case)",
            "task": "Đơn hàng đặt ngày 31/01/2026, yêu cầu hoàn tiền ngày 07/02/2026, sản phẩm lỗi.",
            "retrieved_chunks": [
                {"text": "Chính sách này áp dụng cho đơn hàng từ 01/02/2026.", "source": "policy_refund_v4.txt", "score": 0.80}
            ],
        },
    ]

    for tc in test_cases:
        print(f"\n▶ [{tc['name']}]")
        print(f"  Task: {tc['task'][:80]}")
        state = {
            "task": tc["task"],
            "retrieved_chunks": tc.get("retrieved_chunks", []),
            "needs_tool": False,
            "history": [],
            "workers_called": [],
            "mcp_tools_used": [],
        }
        result = run(state)
        pr = result.get("policy_result", {})
        print(f"  policy_applies:  {pr.get('policy_applies')}")
        if pr.get("exceptions_found"):
            for ex in pr["exceptions_found"]:
                print(f"  exception:       {ex['type']} — {ex['rule'][:60]}...")
        if pr.get("policy_version_note"):
            print(f"  version_note:    {pr['policy_version_note'][:80]}...")
        print(f"  workers_called:  {result['workers_called']}")

    print("\n✅ policy_tool_worker test done.")