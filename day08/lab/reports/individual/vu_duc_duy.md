# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Vũ Đức Duy
**Vai trò trong nhóm:** Retrieval Owner
**Ngày nộp:** 13/04/2026
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

Trong vai trò Retrieval Owner và Eval Owner, tôi đã trực tiếp xây dựng và hoàn thiện luồng truy xuất dữ liệu (Retrieval Pipeline) trải dài từ Sprint 1 đến Sprint 4. Cụ thể, tôi bắt đầu bằng việc thiết lập Baseline Dense Retrieval, sau đó nhận diện hạn chế của nó để tích cực triển khai cấu trúc Hybrid Search (kết hợp nhúng Vector Dense và Sparse BM25) với kỹ thuật gộp điểm Reciprocal Rank Fusion (RRF). 

Bên cạnh đó, tôi cũng implement module Cross-Encoder/LLM Reranking ở cuối phễu để sàng lọc lại top tài liệu thực sự liên quan trước khi đẩy ngữ cảnh vào LLM tổng hợp. Nhằm đảm bảo mọi sự thay đổi đều có thước đo, tôi đã thiết lập công cụ đánh giá Scorecard cũng như kiến trúc Error Tree giúp debug dễ dàng nguyên nhân nằm ở Indexing, Retrieval hay Generation. Các pipeline này liên kết chặt chẽ và cung cấp nền tảng nguyên liệu đầu vào đúng đắn nhất, hỗ trợ trực tiếp phần Generation của đồng đội không bị rơi vào ảo giác (hallucination) hay từ chối trả lời (abstain).

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

Khái niệm tôi thực sự "thấm" sau lab này chính là sự cần thiết của cơ chế **Hybrid Retrieval và quá trình Reranking**. 

Trước đây tôi từng nghĩ dùng Embeddings Vector phân tích ngữ nghĩa là đủ bao quát mọi câu hỏi. Nhưng qua ứng dụng thực tế, mô hình Vector (Dense) lại cực kỳ kém và dễ bỏ qua các từ khóa kỹ thuật cứng (hard keywords) chắp vá như mã lỗi (VD: `ERR-403`). Lúc này, BM25 (Sparse) lại thể hiện sức mạnh nhận diện từ vựng rất tốt. Việc dùng RRF gộp thứ hạng của cả Dense và Sparse bù trừ cho nhau tạo ra tập ứng viên tuyệt vời.

Dù vậy, khi ghép hai dách sách ứng viên lại, số lượng kết quả sẽ dễ bị dư thừa "rác" không cần thiết. Đưa toàn bộ vào LLM tạo sinh sẽ tốn kém token và làm loãng ngữ cảnh. Đó là lý do bước Reranking lại đóng vai trò là "màng lọc tinh" cuối cùng, chấm lại điểm mức độ liên quan trực tiếp của bộ tài liệu so với câu hỏi gốc, lôi top 3 tài liệu chính xác nhất lên đầu. Ngữ cảnh (Context) vì thế trở nên cô đọng, chất lượng trả lời tăng vọt.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

Điều ngạc nhiên lớn nhất đối với tôi quá trình đi tìm nguyên nhân tại sao LLM thường xuyên đưa ra phản hồi Abstain (từ chối trả lời do không tìm thấy hướng dẫn). Ban đầu, giả thuyết của tôi là do chunking text bị cắt đứt giữa chừng điều khoản nội dung quan trọng làm ngắt quãng ý nghĩa. 

Thực tế qua phân tích Error Tree lại chứng minh, lỗi tốn thời gian debug nhất hoàn toàn nằm ở khâu Retrieval: mô hình Vector thuần túy bị nhiễu ngữ nghĩa (nhiễu tokenizer) khi phân giải các dải IP hay mã lỗi. Điểm Context Recall lúc đó được Scorecard báo cáo cực kỳ thấp (chỉ 3.5/5). Dense retrieval đã ném mất các từ khóa bí mật, khiến mảnh ghép thông tin (evidence) gửi cho khung Prompt Generation chẳng chứa thứ gì cả nên mô hình từ chối sinh ra output sai sự thật (một dạng Graceful Fallback). Nhờ hiểu ra nút thắt đó, tôi lập tức đổi qua hệ Hybrid để vá lỗ hổng.

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi:** q07 ("Làm thế nào để xin cấp quyền Level 3 (Admin)?")

**Phân tích:**
- Ở phiên bản Baseline (Dense Search), câu trả lời do phía hệ thống Generation trả về hoàn toàn thất bại, hệ thống rơi vào trạng thái đánh Abstain. Lý do đo lường được là điểm Context Recall bằng 0/5.
- Khi truy ngược nguyên nhân từ bảng lỗi, sự cố rõ ràng phát sinh từ khâu **Retrieval**. Thuật toán Dense bị lúng túng trong các từ khóa phân biệt chính xác loại "Level 3" (thiên về exact alias/keyword). Do Vector Search trượt Top 3 khi sắp xếp, ngữ cảnh thực trả về không có hướng dẫn xin cấp quyền Admin nên LLM buộc phải chọn Fallback. Điều này chứng minh rằng Prompt tuy bắt rất chặt việc ngăn chặn sinh bừa (grounded context) nhưng công cụ Retrieval thì lại thực hiện quá tồi nhan sắc tìm kiếm.
- Khi chuyển sang sử dụng Variant 1 (Hybrid + Reranker), mọi thứ được giải quyết vô cùng sắc bén. Điểm mạnh của Sparse (BM25) là bắt chặt luồng keyword chính xác, gộp cả Reranker OpenAI lên hỗ trợ dồn những tài liệu tốt nhất lên hạng nhất. Điểm Context Recall của toàn hệ thống tăng từ 3.5 lên 4.6/5, và riêng câu q07 được ghi nhận bắt trúng 100% lượng đoạn văn bản Context cần thiết. Tính Faithful và Answer Relevance lúc này đều đạt gần mức tuyệt đối 4.9/5.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

Nếu có thêm thời gian, tôi muốn triển khai thử nghiệm module tính năng **Query Transformation (HyDE hoặc Decomposition)**.
Kết quả từ dữ liệu Eval Scorecard đã chỉ ra rằng ngay cả khi có Rerank và Hybrid, các dạng câu hỏi được gõ theo cách cụt ngủn hoặc ngữ pháp viết tắt nửa vời từ phía user đôi lúc vẫn gây ra sai số tìm kiếm. Tích hợp Query Transformation nhằm tái phân tích, viết lại và mở rộng ý nghĩa câu hỏi trước khi rẽ nhánh truy xuất sẽ giúp hệ pipeline có khả năng chống chịu cao hơn hẳn trước các truy vấn mập mờ trong thực tế.

---