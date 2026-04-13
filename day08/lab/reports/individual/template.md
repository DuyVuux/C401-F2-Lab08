# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Hoàng Vinh Giang  
**Vai trò trong nhóm:** Data Engineer / Metadata Specialist 
**Ngày nộp:** 13/04/2026 
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

> Trong dự án này, tôi chịu trách nhiệm chính ở giai đoạn Data Ingestion (Sprint 1) và Optimization (Sprint 3 & 4). Tôi đã thiết kế và triển khai hàm preprocess_document để chuẩn hóa dữ liệu thô từ các file .txt. Quyết định quan trọng nhất của tôi là thay đổi cơ chế quét metadata từ "ngắt sớm" sang "quét toàn diện" để xử lý các tài liệu có Heading nằm ngay dòng đầu tiên, đảm bảo không bỏ sót thông tin department và effective_date. Công việc của tôi đóng vai trò là "nguyên liệu đầu vào sạch" cho Vector DB Engineer. Nếu tôi không trích xuất chính xác section và heading, các thành viên khác sẽ gặp khó khăn trong việc định danh nguồn gốc của câu trả lời (groundedness) và không thể thực hiện cơ chế cập nhật phiên bản tài liệu (freshness update).


---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

> Sau lab này, tôi hiểu sâu sắc hơn về khái niệm Contextual Chunking và Metadata Inheritance. Trước đây, tôi nghĩ đơn giản là chỉ cần cắt nhỏ văn bản là xong. Tuy nhiên, thực tế cho thấy mỗi chunk nếu đứng độc lập sẽ trở nên "vô nghĩa" nếu mất đi thông tin ngữ cảnh. Tôi đã học được cách cho mỗi chunk "thừa kế" metadata từ tài liệu gốc (như ngày hiệu lực, phòng ban) và bổ sung thêm metadata đặc trưng (tên Section). Điều này giúp hệ thống Retrieval không chỉ tìm đúng đoạn văn mà còn biết đoạn đó nằm ở mục nào trong quy trình lớn. Ngoài ra, tôi nhận ra việc viết hoa toàn bộ Heading không chỉ để đẹp, mà còn là một "điểm neo" kỹ thuật quan trọng giúp bộ chia đoạn (Splitter) hoạt động chính xác hơn, tránh cắt đôi các ý quan trọng.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

> Điều làm tôi mất nhiều thời gian debug nhất chính là logic dừng quét metadata. Ban đầu, tôi giả định metadata luôn nằm trên cùng và kết thúc khi gặp Heading đầu tiên. Nhưng thực tế trong các file SOP, tiêu đề chính thường viết hoa và nằm ở dòng 1, khiến code của tôi hiểu nhầm đó là điểm kết thúc header và bỏ qua toàn bộ Department phía dưới. Tôi đã phải đập đi xây lại logic, loại bỏ biến flag chặn và chuyển sang cơ chế nhận diện theo pattern Key: Value. Một khó khăn khác là "nhiễu" từ các thẻ citation như ``. Nếu không xóa sạch chúng trong bước preprocess, khi sang bước chunking, các con số này bị xé lẻ và làm sai lệch vector embedding, dẫn đến việc tìm kiếm bị "hallucination" (ảo giác).

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi:** `q09` — *"ERR-403-AUTH là lỗi gì và cách xử lý?"*

**Kết quả thực tế (từ scorecard):** Faithfulness=1, Relevance=1, Context Recall=N/A, Completeness=4

**Phân tích:**
Đây là một câu hỏi quan trọng nhằm kiểm tra khả năng Abstain (từ chối trả lời khi thiếu dữ liệu) của hệ thống. Trong file test_questions.json, câu hỏi này có expected_sources: [], nghĩa là thông tin về mã lỗi này hoàn toàn không tồn tại trong tập tài liệu hiện có. Thực tế, Pipeline đã hoạt động cực kỳ chính xác khi trả về thông báo: "Xin lỗi, hệ thống hiện không có đủ dữ liệu trong tài liệu để trả lời câu hỏi này."

Tuy nhiên, kết quả Scorecard gây bất ngờ với điểm Faithfulness = 1 và Relevance = 1 (mức thấp nhất). Qua phân tích, tôi nhận định đây là một lỗi Artifact của LLM-as-Judge. Bộ chấm điểm tự động đã mặc định rằng: "Nếu câu trả lời không chứa thông tin từ các chunk được truy xuất (retrieved chunks) thì đó là lỗi Faithfulness". Trong trường hợp này, vì không có chunk nào liên quan được tìm thấy và câu trả lời là một câu từ chối, Judge đã "nhầm lẫn" sự vắng mặt của thông tin là sự thiếu trung thực.

Ngược lại, điểm Completeness đạt 4/5, chứng tỏ Judge vẫn nhận diện được sự tương đồng giữa câu trả lời thực tế và expected_answer (cũng là một câu từ chối).

Bài học rút ra: Chúng ta cần tinh chỉnh lại Scorer Prompt. Nếu expected_sources rỗng và hệ thống thực hiện hành vi từ chối (Abstain), bộ chấm điểm nên đánh dấu là N/A hoặc cho điểm tối đa thay vì mặc định bằng 1. Đây là vấn đề thuộc về thiết kế Framework Evaluation, không phải lỗi ở tầng Indexing hay Retrieval của Pipeline.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

> Nếu có thêm thời gian, tôi sẽ xây dựng một Automated Data Validator để báo cáo chất lượng dữ liệu ngay sau bước Preprocess. Cụ thể, tôi muốn thử nghiệm tính năng tự động phát hiện các tài liệu bị thiếu effective_date hoặc có cấu trúc Heading không tuân thủ quy tắc viết hoa. Kết quả Evaluation cho thấy các chunk "unknown" metadata thường gây ra lỗi khi AI cần trích dẫn nguồn, vì vậy việc tự động hóa khâu kiểm soát chất lượng này sẽ giúp pipeline ổn định hơn khi scale lên hàng nghìn tài liệu.

---

*Lưu file này với tên: `reports/individual/[ten_ban].md`*
*Ví dụ: `reports/individual/nguyen_van_a.md`*
