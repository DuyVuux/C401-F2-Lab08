"""
workers/synthesis.py — Synthesis Worker
Sprint 2B: Đoàn Nam Sơn

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: evidence từ retrieval_worker
    - policy_result: kết quả từ policy_tool_worker (optional)

Output (vào AgentState):
    - final_answer: câu trả lời cuối với citation [source_name]
    - sources: danh sách nguồn được cite
    - confidence: 0.0 - 1.0

Gọi độc lập để test:
    python workers/synthesis.py
"""

import os
from datetime import datetime

WORKER_NAME = "synthesis_worker"

ABSTAIN_PHRASE = (
    "Xin lỗi, hệ thống không có đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này. "
    "Vui lòng liên hệ IT Helpdesk (ext. 9000) hoặc CS Team (ext. 1234) để được hỗ trợ trực tiếp."
)

SYSTEM_PROMPT = f"""Bạn là trợ lý IT Helpdesk và CS nội bộ.

QUY TẮC NGHIÊM NGẶT — vi phạm sẽ bị trừ điểm:
1. CHỈ trả lời dựa vào CONTEXT được cung cấp bên dưới. TUYỆT ĐỐI không dùng kiến thức ngoài.
2. Nếu context không đủ để trả lời → trả lời đúng một câu sau, không thêm bớt:
   "{ABSTAIN_PHRASE}"
3. Sau mỗi thông tin quan trọng, thêm citation dạng [tên_file] ở cuối câu đó.
4. Nếu có POLICY EXCEPTIONS → nêu exceptions TRƯỚC, rồi mới kết luận.
5. Trả lời súc tích, có cấu trúc. Không dài dòng, không hallucinate.
6. Số liệu cụ thể (thời gian, %, tên người) phải có citation ngay sau."""


# ─────────────────────────────────────────────
# LLM Call
# ─────────────────────────────────────────────

def _call_llm(messages: list) -> str:
    """
    Gọi LLM. Thử OpenAI trước, fallback sang Gemini, cuối cùng là rule-based abstain.
    Temperature=0 để grounded, không sáng tác.
    """
    # Option A: OpenAI gpt-4o-mini
    try:
        from openai import OpenAI
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        pass  # fall through

    # Option B: Google Gemini 1.5 Flash
    try:
        import google.generativeai as genai
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not set")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        # Flatten messages into a single string (Gemini simple API)
        combined = "\n\n".join(
            f"[{m['role'].upper()}]\n{m['content']}" for m in messages
        )
        response = model.generate_content(combined)
        return response.text.strip()
    except Exception as e:
        pass  # fall through

    # Fallback: không hallucinate, trả về abstain thay vì bịa
    return ABSTAIN_PHRASE + " (LLM không khả dụng — kiểm tra API key trong .env)"


# ─────────────────────────────────────────────
# Context Builder
# ─────────────────────────────────────────────

def _build_context(chunks: list, policy_result: dict, mcp_tools_used: list) -> str:
    """Xây dựng context string từ chunks, policy exceptions, và MCP results."""
    parts = []

    if chunks:
        parts.append("=== TÀI LIỆU NỘI BỘ ===")
        for i, chunk in enumerate(chunks[:6], 1):  # tối đa 6 chunks
            source = chunk.get("source", "unknown")
            text = chunk.get("text", "").strip()
            score = chunk.get("score", 0)
            if text:
                parts.append(f"[{i}] {source} (relevance: {score:.2f})\n{text}")

    # Thêm MCP tool results nếu có
    for mcp in mcp_tools_used:
        if mcp.get("output") and not mcp.get("error"):
            tool = mcp.get("tool", "")
            out = mcp["output"]
            if tool == "get_ticket_info" and out.get("ticket_id"):
                parts.append(
                    f"\n=== TICKET INFO (MCP: get_ticket_info) ===\n"
                    f"Ticket: {out.get('ticket_id')} | Priority: {out.get('priority')} | "
                    f"Status: {out.get('status')}\n"
                    f"Created: {out.get('created_at')} | SLA deadline: {out.get('sla_deadline')}\n"
                    f"Notifications: {', '.join(out.get('notifications_sent', []))}"
                )
            elif tool == "check_access_permission" and "can_grant" in out:
                parts.append(
                    f"\n=== ACCESS PERMISSION CHECK (MCP: check_access_permission) ===\n"
                    f"Level: {out.get('access_level')} | Can grant: {out.get('can_grant')}\n"
                    f"Required approvers: {', '.join(out.get('required_approvers', []))}\n"
                    f"Emergency override: {out.get('emergency_override')}\n"
                    f"Notes: {'; '.join(out.get('notes', []))}"
                )

    # Policy exceptions (nêu rõ trước khi kết luận)
    if policy_result and policy_result.get("exceptions_found"):
        parts.append("\n=== POLICY EXCEPTIONS ===")
        for ex in policy_result["exceptions_found"]:
            parts.append(f"- [{ex.get('source', '')}] {ex.get('rule', '')}")

    if policy_result and policy_result.get("policy_version_note"):
        parts.append(f"\n=== LƯU Ý PHIÊN BẢN POLICY ===\n{policy_result['policy_version_note']}")

    return "\n\n".join(parts) if parts else ""


# ─────────────────────────────────────────────
# Confidence Estimation
# ─────────────────────────────────────────────

def _estimate_confidence(chunks: list, answer: str, policy_result: dict) -> float:
    """
    Ước tính confidence:
    - Abstain phrase → 0.0
    - Không có chunks → 0.1
    - Có exceptions → penalty nhỏ
    - Dựa vào avg chunk score
    """
    if ABSTAIN_PHRASE[:30] in answer or "LLM không khả dụng" in answer:
        return 0.0

    if not chunks:
        return 0.1

    avg_score = sum(c.get("score", 0.5) for c in chunks) / len(chunks)
    exception_penalty = 0.04 * len(policy_result.get("exceptions_found", []))
    confidence = min(0.97, avg_score - exception_penalty)
    return round(max(0.05, confidence), 2)


# ─────────────────────────────────────────────
# Main synthesis logic
# ─────────────────────────────────────────────

def synthesize(task: str, chunks: list, policy_result: dict, mcp_tools_used: list) -> dict:
    """
    Tổng hợp câu trả lời cuối.

    Returns:
        {answer, sources, confidence}
    """
    # Abstain ngay nếu không có bất kỳ context nào
    if not chunks and not mcp_tools_used:
        return {
            "answer": ABSTAIN_PHRASE,
            "sources": [],
            "confidence": 0.0,
        }

    context = _build_context(chunks, policy_result, mcp_tools_used)

    if not context.strip():
        return {
            "answer": ABSTAIN_PHRASE,
            "sources": [],
            "confidence": 0.0,
        }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Câu hỏi: {task}\n\n{context}\n\nHãy trả lời câu hỏi dựa hoàn toàn vào tài liệu trên.",
        },
    ]

    answer = _call_llm(messages)
    sources = list({c.get("source", "unknown") for c in chunks if c.get("source")})
    confidence = _estimate_confidence(chunks, answer, policy_result)

    return {"answer": answer, "sources": sources, "confidence": confidence}


# ─────────────────────────────────────────────
# Worker Entry Point
# ─────────────────────────────────────────────

def run(state: dict) -> dict:
    """Worker entry point — gọi từ graph.py."""
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    policy_result = state.get("policy_result", {})
    mcp_tools_used = state.get("mcp_tools_used", [])

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state.setdefault("worker_io_logs", [])
    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "has_policy_result": bool(policy_result),
            "mcp_tools_count": len(mcp_tools_used),
        },
        "output": None,
        "error": None,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        result = synthesize(task, chunks, policy_result, mcp_tools_used)

        state["final_answer"] = result["answer"]
        state["sources"] = result["sources"]
        state["confidence"] = result["confidence"]

        # Flag HITL nếu confidence thấp (< 0.4)
        if result["confidence"] < 0.4 and not state.get("hitl_triggered"):
            state["hitl_triggered"] = True
            state["history"].append({
                "step": WORKER_NAME,
                "event": "hitl_flagged",
                "reason": f"Low confidence: {result['confidence']}",
            })

        worker_io["output"] = {
            "answer_length": len(result["answer"]),
            "sources": result["sources"],
            "confidence": result["confidence"],
            "abstained": result["answer"].startswith(ABSTAIN_PHRASE[:30]),
        }

        state["history"].append({
            "step": WORKER_NAME,
            "event": "completed",
            "confidence": result["confidence"],
            "sources": result["sources"],
        })

    except Exception as e:
        worker_io["error"] = {"code": "SYNTHESIS_FAILED", "reason": str(e)}
        state["final_answer"] = f"SYNTHESIS_ERROR: {e}"
        state["sources"] = []
        state["confidence"] = 0.0
        state["history"].append({"step": WORKER_NAME, "event": "error", "reason": str(e)})

    state["worker_io_logs"].append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("Synthesis Worker — Standalone Test (Sprint 2B)")
    print("=" * 55)

    # Test 1: Câu trả lời bình thường
    state1 = {
        "task": "SLA ticket P1 là bao lâu?",
        "retrieved_chunks": [
            {
                "text": "Ticket P1: Phản hồi ban đầu 15 phút. Xử lý 4 giờ. Escalate lên Senior Engineer nếu không phản hồi trong 10 phút.",
                "source": "sla_p1_2026.txt",
                "score": 0.92,
            }
        ],
        "policy_result": {},
        "mcp_tools_used": [],
        "history": [],
        "workers_called": [],
    }
    print("\n▶ Test 1: SLA query (có chunks)")
    r1 = run(state1.copy())
    print(f"  Answer:     {r1['final_answer'][:120]}...")
    print(f"  Sources:    {r1['sources']}")
    print(f"  Confidence: {r1['confidence']}")

    # Test 2: Flash Sale exception
    state2 = {
        "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì lỗi nhà sản xuất.",
        "retrieved_chunks": [
            {
                "text": "Ngoại lệ Flash Sale: không được hoàn tiền theo Điều 3.",
                "source": "policy_refund_v4.txt",
                "score": 0.88,
            }
        ],
        "policy_result": {
            "policy_applies": False,
            "exceptions_found": [
                {"type": "flash_sale_exception", "rule": "Flash Sale không được hoàn tiền (Điều 3).", "source": "policy_refund_v4.txt"}
            ],
        },
        "mcp_tools_used": [],
        "history": [],
        "workers_called": [],
    }
    print("\n▶ Test 2: Flash Sale exception")
    r2 = run(state2.copy())
    print(f"  Answer:     {r2['final_answer'][:120]}...")
    print(f"  Confidence: {r2['confidence']}")

    # Test 3: Abstain (không có context)
    state3 = {
        "task": "ERR-403-AUTH là lỗi gì?",
        "retrieved_chunks": [],
        "policy_result": {},
        "mcp_tools_used": [],
        "history": [],
        "workers_called": [],
    }
    print("\n▶ Test 3: Abstain (không có chunks)")
    r3 = run(state3.copy())
    print(f"  Answer:     {r3['final_answer'][:120]}")
    print(f"  Confidence: {r3['confidence']}")
    print(f"  HITL:       {r3.get('hitl_triggered', False)}")

    print("\n✅ synthesis_worker test done.")