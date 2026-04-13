# Chiến lược Phân công Nhiệm vụ & Quy trình Dự án RAG (5 Members)

Dựa trên phân tích sâu chuỗi hệ thống Pipeline 3 khối (Indexing → Retrieval → Generation) từ bài giảng Day 08 (`lecture-08.html`), tài liệu này tái cấu trúc quy chuẩn nguyên bản (vốn 4 người) thành 5 phân hệ kỹ thuật chuyên sâu để đảm bảo **tất cả 5 thành viên đều trực tiếp lập trình (code-intensive)** và chịu tải lượng task công bằng.

## 1. Data Processing Engineer (Preprocess & Metadata)

**Nhiệm vụ trọng tâm:** Quản lý làm sạch dữ liệu đầu vào và cấu trúc hóa metadata từ bộ quy định CS & Helpdesk. Như bài giảng nhấn mạnh: *"Chất lượng retrieval bắt đầu từ lúc chuẩn bị tài liệu"*.
*   **Chịu trách nhiệm (Files):** `data_ingestor.py` (tách từ `index.py`), thư mục `data/docs/`
*   **Chi tiết theo Sprints:**
    *   **Sprint 1:** Lập trình pipeline "Preprocess" (Clean, extract, normalize) loại bỏ OCR lỗi, bảng vỡ, ký tự rác.
    *   **Sprint 2:** Lập trình quy tắc trích xuất 3 metadata bắt buộc: `source`, `section`, `effective_date`.
    *   **Sprint 3:** Xây dựng cơ chế Freshness update liên tục tài liệu, sẵn sàng ứng phó với tài liệu thay đổi phiên bản (alias).
    *   **Sprint 4:** Thực thi "Chunking Clinic", phối hợp cùng Vector DB Eng sửa lỗi chia đoạn text sai. Báo cáo chất lượng data.
*   **Kết quả đầu ra (DoD):** Dữ liệu output không chứa text mù, không bị đứt tại biên (boundary), có tag schema minh bạch.

## 2. Core AI Engineer (Vector DB & Chunking)

**Nhiệm vụ trọng tâm:** Quản lý quy trình cắt chunk và nhúng vector (Embed + Store), tránh tình trạng *Chunking tồi* (cắt giữa điều khoản, đánh rơi ngữ cảnh).
*   **Chịu trách nhiệm (Files):** `index.py`, `vector_store_manager.py`
*   **Chi tiết theo Sprints:**
    *   **Sprint 1:** Lập trình giải thuật chia cụm theo Semantic/Heading. Thiết lập *Chunk size* (300–500 tokens) và *Overlap* (50–80 tokens).
    *   **Sprint 2:** Khởi tạo ChromaDB, viết hàm gọi API Embed model (Text-embedding/BGE) và kiểm soát lưu trùng lặp (`upsert`).
    *   **Sprint 3:** Tự động hóa luồng đưa Text + Vector + Metadata hợp nhất vào vector store ổn định.
    *   **Sprint 4:** Diagnostics qua "Error Tree" (nhánh: Chunk có đúng không? Metadata có đủ không?). Viết báo cáo đánh giá.
*   **Kết quả đầu ra (DoD):** Index chạy mượt, 10-20 doc nhỏ hợp nhất chứa đầy đủ Metadata truy xuất được.

## 3. Search & Relevance Engineer (Retrieval & Rerank Funnel)

**Nhiệm vụ trọng tâm:** Lệnh tìm kiếm tối cao. Triển khai mô hình tìm kiếm thông qua *Retrieval Funnel* của slide: "Search rộng -> Rerank -> Select hẹp".
*   **Chịu trách nhiệm (Files):** `rag_answer.py` (Retrieval module)
*   **Chi tiết theo Sprints:**
    *   **Sprint 1 (Baseline):** Tổ chức truy vấn Top-K qua Dense Search (câu tự nhiên paraphrase).
    *   **Sprint 2:** Triển khai truy vấn Sparse Search phục vụ xử lý mã ticket (`ERR-403`, `P1`).
    *   **Sprint 3 (Tuning):** Xây dựng chiến lược kết hợp hệ sinh thái Hybrid, chèn Cross-Encoder tạo luồng phễu (Top-20 ➝ Rerank Top-6 ➝ Select Top-3).
    *   **Sprint 4:** Gỡ lỗi qua "Error Tree" (nhánh: Retrieve sai doc cũ/mới, sót expected sources). Nộp báo cáo latency/precision.
*   **Kết quả đầu ra (DoD):** Pipeline `retrieve_documents()` luôn bắt trúng đích 100% tài liệu mà hệ thống kì vọng.

## 4. LLM Ops & Prompt Engineer (Grounded Generation)

**Nhiệm vụ trọng tâm:** Tổ chức mô hình Answer generation. Điển hình *Prompt Surgery* để bắt model nói sự thật, tuân theo các nguyên tắc evidence-only.
*   **Chịu trách nhiệm (Files):** `rag_answer.py` (Gen module), `prompt_templates.txt`
*   **Chi tiết theo Sprints:**
    *   **Sprint 1:** Quản lý luồng gọi LLM và xây dựng cấu trúc Prompt sườn. Canh đo *Token Budget* (Instructions, Context, Question, Headroom).
    *   **Sprint 2:** Ràng buộc output sinh ra buộc chứa Citations (khối trích dẫn minh chứng, tựa `[1]`).
    *   **Sprint 3:** Ép luồng "Graceful Fallback / Abstain", Model sẽ bẩm báo "Không đủ dữ liệu" thay vì cố sinh câu trả lời bịa đặt khi trích dẫn đưa vào bị nghẽn (hallucination).
    *   **Sprint 4:** Diagnostics thông qua nhánh cuối của "Error Tree". Tối giản token API và báo cáo. 
*   **Kết quả đầu ra (DoD):** Câu trả lời logic (Short, clear, stable), bám sát nội dung trích xuất.

## 5. Evaluation Automation Engineer (Metrics & Scorecards)

**Nhiệm vụ trọng tâm:** Chấm RAG qua code, không bằng cảm giác. Ứng dụng "LLM-As-A-Judge" và hệ nguyên lý "A/B rule" từ slide (chỉ đổi MỘT biến số mỗi lần chạy).
*   **Chịu trách nhiệm (Files):** `eval.py`, `docs/tuning-log.md`, `data/test_questions.json`
*   **Chi tiết theo Sprints:**
    *   **Sprint 1:** Thu thập và lên dàn 10 Test questions kèm the Expected Answers (Ground Truth).
    *   **Sprint 2:** Khởi tạo bộ máy chấm điểm chuẩn qua 4 thang đo điểm: *Faithfulness, Relevance, Context recall, Completeness.*
    *   **Sprint 3:** Chạy baseline automation qua Python, chiết xuất scorecard Baseline.
    *   **Sprint 4:** Thử nghiệm thay đổi thông số "A/B Comparison" tự động (Đổi size chunk, Đổi DB Reranker). Kết xuất Variant report. 
*   **Kết quả đầu ra (DoD):** Sản xuất được bảng Điểm Scorecard đối chiếu sự thay đổi chất lượng giữa Baseline RAG và Tuned RAG. `docs/architecture.md` chuẩn chỉnh.

---
