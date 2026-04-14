# Báo Cáo Cá Nhân — Sprint 2: Retrieval Worker

**Họ và tên:** Vũ Đức Duy  
**Vai trò:** Retrieval Worker Owner  
**Sprint phụ trách:** Sprint 2 (Core Workers)  

---

## 1. Tóm tắt công việc đã thực hiện

Trong vai trò là người chịu trách nhiệm cho module Retrieval Worker, tôi đã hoàn thiện file `workers/retrieval.py` để đóng gói logic truy xuất ngữ cảnh từ Day 08 thành một Worker hoạt động chuẩn chỉnh theo kiến trúc State Graph của Day 09. Cụ thể:

- **Khởi tạo wrapper function (`run`):** Tiếp nhận `AgentState`, trích xuất thông tin `task` và bọc hàm tìm kiếm `retrieve_dense` từ thư viện nhóm đã viết trước đó ở Day 08.
- **Quản lý dữ liệu State & Truy vết (Traceability):** Đảm bảo bổ sung vào trường `workers_called` tên định danh `retrieval_worker`, trích xuất file nguồn vào danh sách `retrieved_sources` để Policy/Synthesis worker phía sau có thể trích dẫn. Các thông tin I/O cũng được push vào `worker_io_logs` và `history` để Quang Quí (Sprint 4) phục vụ việc đánh giá logic chạy (routing).
- **Cơ chế Fallback (Tính bền bỉ):** Trong trường hợp `day08/lab` không thể được tải hoặc import gặp lỗi do path, tôi đã viết một hàm `_fallback_retrieve` để tự động load biến môi trường thông qua `dotenv`, mã hóa câu hỏi bằng `OpenAI` (`text-embedding-3-small`), và truy vấn trực tiếp vào database Vector ở local (`chroma_db`). Điều này đảm bảo Retrieval Worker không bao giờ break toàn bộ luồng chương trình.
- **Kiểm thử độc lập:** Đã chạy thử độc lập file `workers/retrieval.py` trong `.venv` để chắc chắn nó xử lý chuẩn chỉnh cả 2 cấu hình (khi có và không có data), trong phương thức standalone return đúng số lượng `Chunks` và `Sources` cho SLA tickets.

## 2. Thách thức kỹ thuật & Cách giải quyết

**Vấn đề 1: Lỗi thư viện và Import Path chéo giữa các thư mục (Dependency Hell)**  
Day 08 và Day 09 được phát triển trên các hệ quy chiếu khác nhau (standalone vs Multi-Agent). Do đó, khi import `src.retrieval.rag_answer` từ Day 08, Python kernel throw `ModuleNotFoundError` và không tìm thấy môi trường `.venv` gốc chứa các biến `OPENAI_API_KEY`.
**Giải pháp:** Tôi đã thiết lập một `.venv` dùng chung tại Root và tự viết lại logic `fallback` (sử dụng OpenAI thuần mà loại bỏ sự phụ thuộc `sentence-transformers` theo cấu hình mới của người dùng). Cơ chế bắt lỗi `try-except` trên đầu file worker đã giúp điều hướng luồng khi xảy ra lỗi. 

**Vấn đề 2: Tương thích Component State**  
LangGraph yêu cầu truyền data liên hoàn nhưng nếu database rỗng, worker có thể trả về lỗi index `Out of range` hoặc làm ứng dụng crash. 
**Giải pháp:** Trả về danh sách chunks rỗng `[]` và không làm crash hệ thống. Điều này để cho phép `synthesis.py` (của Nam Sơn) ghi nhận và đưa ra câu trả lời abstain.

## 3. Kiến thức học được (Key Learnings)

1. **State Injection trong Orchestration:** Việc bọc một tính năng cũ vào mô hình tác tử (Agent pattern) không chỉ là copy-paste mà còn phải đảm nhiệm tính toán log, error catching, và cập nhật I/O chuẩn định dạng mà Supervisor quy định.
2. **Nguyên tắc "Fail Gracefully":** Luôn phải dự phòng phương án "hỏng hóc" (Fallback DB) hoặc nạp mock-data tạm để đảm bảo các worker sau chặn không bị treo chờ dữ liệu. Việc này rất quan trọng trong thiết kế Distributed System hoặc Microservices.
3. **Traceability:** Quản lý nhật ký `state["history"]` ở từng trạm dừng đóng vai trò sống còn trong việc dò lỗi đường đi của Agent thay vì debug thủ công từng hàm.

## 4. Góp ý cải tiến RAG Pipeline (Nếu có thêm thời gian)

- **Tích hợp Reranker nội tại vào Worker:** Thay vì chỉ kéo `retrieve_dense`, tôi sẽ implement thêm Cross-Encoder ngay tại Retrieval Worker để điểm số độ chính xác (Relevance Score) trả về cho State cao hơn, giúp Synthesis phân biệt được nhiễu.
- **Tách biệt Metadata Vector Search:** Dùng query LLM để tách entity (như hạn mức tiền, SLA) trước khi query vào ChromaDB để tăng filter chính xác (Smart metadata filtering tool - MCP Tool) thay vì chỉ Semantic Search đơn thuần.
