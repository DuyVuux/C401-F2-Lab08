# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Vũ Đức Duy  
**Vai trò trong nhóm:** Worker Owner (Retrieval Worker) & Frontend-Backend Integrator  
**Ngày nộp:** 14/04/2026  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

**Module/file tôi chịu trách nhiệm:**
- File chính: `workers/retrieval.py`, `frontend/components/ChatInterface.tsx` (tích hợp UI Frontend)
- Functions tôi implement: Hàm `run(state)` cho Retrieval Worker, logic `_fallback_retrieve`, thiết lập kết nối Frontend (Next.js) gọi qua backend FastAPI (`POST /chat`).

Với tư cách là Retrieval Worker Owner (Sprint 2), tôi đã xây dựng `workers/retrieval.py` để lấy dữ liệu ngữ cảnh (context) từ hệ thống Vector DB nội bộ và đưa vào State quản lý của đồ thị cho các worker tiếp theo. Đồng thời, dựa trên nội dung triển khai thực tế của dự án, tôi đảm nhận cả việc **tích hợp và test UI/UX** từ Next.js gọi trực tiếp API `localhost:8001/chat` để đảm bảo luồng hệ thống end-to-end từ người dùng đến Graph chạy trơn tru, hiển thị minh bạch các truy vết.

**Cách công việc của tôi kết nối với phần của thành viên khác:**
Luồng của tôi cung cấp `retrieved_chunks` và `retrieved_sources` cốt lõi để Policy Worker (của Nam Sơn) check các quy định ngoại lệ và Synthesis Worker tổng hợp cấu trả lời cuối cùng. Việc xử lý thông suốt kết nối CORS và frontend đảm bảo mô hình Multi-Agent sở hữu giao diện người dùng hiển thị chân thực thay vì chỉ tương tác dòng lệnh ngầm.

**Bằng chứng:**
- Các đoạn mã cấu hình `sys.path` và xử lý Try-Catch cập nhật trong `workers/retrieval.py`.
- Sử dụng `fetch("http://localhost:8001/chat")` trong `ChatInterface.tsx`.
- Nhật ký thực thi kiểm thử UI với các trace logs lưu tại `artifacts/traces/`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** 
Thực hiện chèn thư mục gốc của dự án thông qua `sys.path.insert(0, _ROOT)` trong Runtime của worker, đồng thời cập nhật biến môi trường qua `uv` thay vì copy-paste và viết lại toàn bộ core logic thuật toán tìm kiếm đa luồng (BM25 + Semantic) từ thư mục gốc của Day 08 sang một module độc lập ở Day 09. Hệ thống gọi thẳng vào `day08.lab.src.retrieval.rag_answer.retrieve_dense`.

**Lý do:**
Khai báo path hệ thống tại quá trình thực thi giúp tổ chức lại cấu trúc tái sử dụng, thừa kế hoàn toàn kỹ thuật tìm kiếm đỉnh cao (Hybrid Search & Reranking) từ đồ án RAG trước đó và tiết kiệm việc viết mã dư thừa theo nguyên tắc DRY (Don't Repeat Yourself). Lựa chọn thay thế là nhân bản code sẽ vi phạm Single Source of Truth, kéo theo viễn cảnh phải cấu hình siêu tham số (`top_k`, reranker models) ở song song hai hệ thống độc lập.

**Trade-off đã chấp nhận:**
Quyết định tái sử dụng tài nguyên đòi hỏi các packages ở môi trường nội bộ như `underthesea`, `rank_bm25` (phụ thuộc cũ của Day 08) phải có mặt trọn vẹn trong môi trường làm việc `.venv` này, dễ gây gián đoạn đường truyền nếu máy người phát triển thiếu cài đặt các gói library liên kết đó. Tôi chấp nhận rủi ro này và đưa ra phương án viết thêm logic `_fallback_retrieve` để đọc cơ sở dữ liệu Vector Database thô nếu không thể import thành công module RAG nâng cao.

**Bằng chứng từ trace/code (workers/retrieval.py):**
```python
_ROOT = str(Path(__file__).parents[5])  # Dẫn về .../C401-F2-Lab08
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ... Exception Handler để invoke fallback
```

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** `ModuleNotFoundError` do không tìm thấy gói truy xuất `day08` tại gốc, lỗi trích xuất vì thư viện `underthesea` và `rank_bm25` chưa được cài đặt. Thêm vào đó, là lỗi gọi Back-End (CORS Blocked) phá vỡ luồng Frontend.

**Symptom (pipeline làm gì sai?):**
Trong quá trình truy vấn hệ thống qua đồ thị `graph.py` hay giao diện Next.js, worker phát sinh báo cảnh báo `ImportError` ở bước lấy ngữ cảnh. Hệ thống hoàn toàn phớt lờ những tiến bộ của RAG Pipeline Day 08 và chuyển thẳng về hàm dự phòng. Nguy hiểm hơn, UI gửi phương thức `POST /chat` liên tục trả về trạng thái lỗi `CORS Policies` (port 3001 gọi 8001 thất bại).

**Root cause (lỗi nằm ở đâu):**
Lỗi phân mảnh cấu hình: Môi trường (Dependencies) của dự án Day 09 không ánh xạ với chuẩn Day 08 (đặc biệt thiếu các package tokenization phục vụ Sparse Retrieval). Điểm chết thứ hai nằm ở Middleware FastAPI mặc định không cho phép kết nối liên miền chéo (Cross-Origin Resource Sharing) đến React.

**Cách sửa:**
- Dependencies: Tiêm thủ công gói thiếu thông qua lệnh `uv pip install underthesea rank_bm25` trên Virtual Environment `.venv` của dự án để đảm bảo pipeline tái sử dụng hoạt động nhạy bén. 
- API/Frontend: Định nghĩa CORS Origin cấp cho phép `"http://localhost:3001"` bằng `CORSMiddleware` bên trong file `mcp_server.py`. Tôi cũng thay đổi mock data cũ của template React bằng kỹ thuật `fetch API` thực để đón tải JSON của máy chủ LLM phục hồi trải nghiệm tương tác với Chat UI chuẩn mực.

**Bằng chứng trước/sau:**
- Trước khi sửa: Console trả về báo lỗi `500 Server Error` (do Import RAG thất bại), Trình duyệt block `POST /chat`, hệ thống truy vấn "trả về rỗng" nếu ChromaDB cũ không load.
- Sau khi sửa: Luồng API trả về Status HTTP 200/OK, `retrieved_chunks` phân định đúng định dạng và có ghi nhận `workers_called: ["retrieval_worker"]`. Next.js nhận tín hiệu thành công và in lời giải đáp rõ ràng từ Synth Worker.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Tôi làm tốt nhất ở điểm nào?**
Tôi đã hoàn thành thành công vai trò của một Integrator ở cả Data backend (Retrieval state) lẫn bề mặt Application (Next.js - FastAPI). Khả năng xử lý các rào cản kỹ thuật cứng về môi trường và Dependency (Path configs, .venv mismatch) chứng minh tính cơ động, không ngại debug để duy trì sự trọn vẹn chất lượng từ Day 08 đến Day 09. 

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**
Do đặc thù phải mở rộng quá nhiều ra luồng hệ thống ở Frontend và Core Graph API, tôi chưa dành được lượng thời gian tối ưu để kiểm thử số liệu định lượng về Indexing ở node Retrieval cho đánh giá RAG nâng cao (Recall/MRR evaluation) một cách chuyên sâu. Tính năng UI đang dừng ở trạng thái Loading và hiển thị tĩnh Block (thay vì Server-Sent Events Streaming Text tốc độ cao).

**Nhóm phụ thuộc vào tôi ở đâu?** 
Cụm trả lời của Synthesis Worker sẽ không có context ngữ cảnh nếu Retrieval Worker của tôi không gửi `retrieved_chunks`. Cùng đó, toàn bộ phần nhìn, kiểm định UI end-to-end sẽ treo chặn chéo nếu Frontend chưa gắn với Pipeline API backend như đã xử lý được.

**Phần tôi phụ thuộc vào thành viên khác:**
Tôi hoàn toàn dựa vào cấu trúc đồ thị luồng tổng (`graph.py`) cùng cơ chế Route chuẩn của Gia Bách để có thể tiêm input chuẩn. Tín hiệu trả về cho End-User cũng phụ thuộc vào Node Synthesis của Nam Sơn phản ứng chính xác dựa vào dữ liệu Worker Retrieval.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

**Cải tiến:** Tích hợp Query Transformation (như HyDE - Hypothetical Document Embeddings hoặc Multi-Query decomposition) vào chu trình của `retrieval_worker`, xử lý câu lệnh người dùng trước khi cấp cho RAG. Đồng thời đẩy mạnh luồng truyền dữ liệu theo kiểu Streaming SSR cho web UI Next.js.

**Lý do:** Trace cho thấy các câu hỏi mơ hồ sẽ dễ khiến cơ chế Semantic Search và thuật toán gốc gãy nhịp phân tích -> Synthesis Worker phải "Abstain" (khi context nghèo hoặc rỗng). Kỹ thuật HyDE sẽ cho LLM sinh trước giả thuyết nâng tỉ lệ Recall đầu vào hệ thống Vector. Giao diện Streaming SSR sẽ triệt để xoá bỏ hiện tượng "đợi chờ vòng xoay" khi Agent chần chừ kéo Document, thay đổi đáng kể User Experience.
