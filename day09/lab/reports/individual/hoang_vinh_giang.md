# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Hoàng Vĩnh Giang  
**Vai trò trong nhóm:** MCP Owner  
**Ngày nộp:** 14/04/2026  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

Tôi chịu trách nhiệm chính cho module MCP server, cụ thể là file `day09/lab/mcp_server.py`. Tôi đã implement toàn bộ các function liên quan đến dispatch tool, mock các MCP tool (search_kb, get_ticket_info, check_access_permission, create_ticket) và đặc biệt là phần mở rộng HTTP server với FastAPI để expose API `/tools/list` và `/tools/call`. Tôi cũng đảm bảo các schema input/output của từng tool đúng chuẩn, giúp các thành viên khác dễ dàng tích hợp agent hoặc worker với MCP server. Công việc của tôi là cầu nối giữa agent (graph.py) và các worker, giúp mọi thành viên có thể gọi tool qua HTTP hoặc import trực tiếp. 

**Module/file tôi chịu trách nhiệm:**
- File chính: `mcp_server.py`
- Functions tôi implement: `dispatch_tool`, `list_tools`, các tool mock (`tool_search_kb`, `tool_get_ticket_info`, ...), phần FastAPI HTTP server

**Cách công việc của tôi kết nối với phần của thành viên khác:**
- Agent (graph.py) gọi trực tiếp `dispatch_tool` hoặc qua HTTP server tôi viết.
- Các worker có thể thêm tool mới chỉ cần đăng ký vào registry.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**
- Xem các đoạn code có comment MCP server, HTTP server, và commit ngày 14/04/2026.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Tôi chọn implement HTTP server cho MCP bằng FastAPI thay vì chỉ để dạng mock class nội bộ.

**Lý do:**
- FastAPI đơn giản, dễ mở rộng, có thể chạy song song với test CLI.
- Cho phép các thành viên khác (hoặc hệ thống ngoài) tích hợp qua HTTP API chuẩn REST, không bị phụ thuộc import Python.
- FastAPI hỗ trợ tự động sinh docs, dễ test API.

**Trade-off đã chấp nhận:**
- Phải cài thêm package (fastapi, uvicorn), có thể phát sinh lỗi môi trường nếu chưa cài.
- Nếu chỉ dùng nội bộ Python thì HTTP server là dư thừa, nhưng nhóm mình cần thử nghiệm tích hợp đa agent nên chấp nhận.

**Bằng chứng từ trace/code:**
```python
# HTTP Server with FastAPI (Bonus Option)
if __name__ == "__main__":
    ...
    if args.http:
        from fastapi import FastAPI, Request
        ...
        app = FastAPI(...)
        @app.get("/tools/list")
        async def api_list_tools():
            return list_tools()
        @app.post("/tools/call")
        async def api_call_tool(request: Request):
            ...
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** Khi chạy `python mcp_server.py --http` lần đầu bị lỗi ImportError do thiếu FastAPI/uvicorn.

**Symptom (pipeline làm gì sai?):**
- Server không khởi động, báo lỗi "No module named 'fastapi'" hoặc "No module named 'uvicorn'".

**Root cause (lỗi nằm ở đâu — indexing, routing, contract, worker logic?):**
- Lỗi nằm ở phần import package ngoài (FastAPI, uvicorn) trong block `if args.http:`.

**Cách sửa:**
- Thêm try/except để báo lỗi rõ ràng và hướng dẫn cài đặt đúng package.

**Bằng chứng trước/sau:**
- Trước: Traceback lỗi ImportError, server dừng ngay.
- Sau: In ra "FastAPI/uvicorn chưa được cài đặt. Cài bằng: pip install fastapi uvicorn" và exit code 1.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**
- Chủ động mở rộng MCP server thành HTTP API, giúp nhóm dễ test và tích hợp.
- Đảm bảo schema rõ ràng, code dễ đọc, dễ mở rộng tool mới.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
- Chưa kết nối được với ChromaDB thực, tool search_kb vẫn dùng mock nếu worker chưa hoàn thiện.
- Chưa có test coverage tự động cho HTTP API.

**Nhóm phụ thuộc vào tôi ở đâu?**
- Nếu MCP server chưa chạy, agent và các worker không thể test end-to-end.

**Phần tôi phụ thuộc vào thành viên khác:**
- Cần worker retrieval và policy_tool hoàn thiện để tool MCP trả về kết quả thực.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Tôi sẽ bổ sung test tự động cho HTTP API (dùng pytest + httpx) và hoàn thiện kết nối thực với ChromaDB cho tool `search_kb`. Lý do: hiện tại trace cho thấy các kết quả search vẫn là mock, chưa truy vấn được dữ liệu thật, làm giảm giá trị tích hợp end-to-end.

---
