# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Nhữ Gia Bách
**Vai trò trong nhóm:** Core AI Engineer (Vector DB & Chunking)  
**Ngày nộp:** 13/04/2026
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

Trong lab này, tôi đảm nhận vai trò Core AI Engineer, chịu trách nhiệm chính cho hai file `index.py` và `vector_store_manager.py`. Tôi tập trung vào Sprint 1 và Sprint 2: cải thiện thuật toán chunking từ cắt thuần theo character count sang chunk theo heading (`=== … ===`) kết hợp paragraph boundary (`\n\n`) và sentence boundary, đảm bảo mỗi chunk đạt 300–500 token với 50–80 token overlap. Song song đó, tôi implement `get_embedding()` sử dụng SentenceTransformers và hoàn thiện `build_index()` để khởi tạo ChromaDB, embed từng chunk, rồi upsert cùng metadata vào vector store. Ngoài ra, tôi tạo mới `vector_store_manager.py` để tách biệt logic bootstrap ChromaDB client/collection, giúp phần còn lại của hệ thống có thể reuse collection mà không khởi tạo lại. Công việc của tôi là nền tảng để Retrieval Owner có thể query vector store ở các sprint sau.

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

Sau lab này, tôi hiểu sâu hơn về **tầm quan trọng của chunking strategy** trong RAG pipeline. Trước đây tôi nghĩ đơn giản là cắt văn bản theo số ký tự là đủ, nhưng thực tế cho thấy nếu cắt giữa một điều khoản hay giữa một đoạn Q&A, retrieval sẽ trả về những đoạn text thiếu ngữ cảnh, khiến LLM generate ra câu trả lời sai hoặc không đầy đủ. Việc tôn trọng heading boundary và paragraph boundary giúp mỗi chunk là một đơn vị ngữ nghĩa hoàn chỉnh. Tôi cũng hiểu rõ hơn cơ chế **overlap**: phần đuôi của chunk trước được giữ lại làm phần đầu của chunk sau, nhằm bảo toàn ngữ cảnh xuyên biên giới chunk. Đây không phải trùng lặp lãng phí mà là cơ chế đảm bảo câu hỏi spanning hai chunk vẫn có thể được trả lời đúng.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

Điều tôi không ngờ là ngay cả sau khi implement xong chunking và embedding, kết quả `python3 index.py` vẫn trông giống hệt trước — vì phần `build_index()` vẫn bị comment out trong main block. Ban đầu tôi tưởng code bị lỗi hay không được gọi đúng, nhưng thực ra đây là thiết kế cố ý: smoke test chỉ chạy preprocess + chunking để không yêu cầu `sentence-transformers` và `chromadb` đã cài sẵn. Khó khăn lớn nhất là xử lý trường hợp paragraph quá dài — một paragraph đơn có thể vượt 500 token, buộc tôi phải fallback sang sentence boundary splitting. Việc xâu chuỗi hai mức split (paragraph → sentence) trong khi vẫn duy trì overlap và metadata đúng cho mỗi chunk đòi hỏi debug khá nhiều edge case, đặc biệt với các tài liệu tiếng Việt có dấu câu không chuẩn.

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi:** "Chính sách hoàn tiền áp dụng trong những trường hợp nào?"

**Phân tích:**

Câu hỏi này thuộc tài liệu `policy_refund_v4.txt`. Ở baseline (chunking theo character count), retrieval trả về một chunk cắt giữa điều khoản, bắt đầu từ giữa một điều kiện hoàn tiền và kết thúc trước khi liệt kê hết các trường hợp được áp dụng. Kết quả là LLM chỉ đề cập được 2/5 trường hợp, điểm faithfulness thấp.

Sau khi áp dụng heading-aware + paragraph-aware chunking, toàn bộ section "Điều kiện hoàn tiền" được giữ nguyên trong một chunk duy nhất vì nó nằm dưới một heading `===`. Retrieval lần này trả về đúng chunk đó, LLM liệt kê đủ 5 trường hợp. Điểm cải thiện rõ rệt.

Bài học: lỗi không nằm ở generation mà nằm ở **indexing** — cụ thể là chunking cắt sai biên giới. Đây là minh chứng điển hình cho nguyên tắc "garbage in, garbage out" trong RAG: retrieval chỉ tốt khi chunks có ngữ nghĩa hoàn chỉnh.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

Tôi sẽ thử **thay SentenceTransformers bằng BGE-M3** (đa ngôn ngữ, hỗ trợ tiếng Việt tốt hơn) vì eval hiện tại cho thấy một số câu hỏi tiếng Việt có cosine similarity thấp bất thường dù nội dung liên quan. Ngoài ra, tôi muốn implement `inspect_metadata_coverage()` để tự động phát hiện chunk nào đang thiếu `effective_date` hoặc `department` — hiện tại vẫn còn một số doc có metadata không đầy đủ mà chưa có cơ chế cảnh báo tự động.

---