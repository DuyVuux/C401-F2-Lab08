# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Đoàn Nam Sơn  
**Vai trò trong nhóm:** LLM Ops & Prompt Engineer (Generation Owner)  
**Ngày nộp:** 2026-04-13  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

Với vai trò LLM Ops & Prompt Engineer, tôi đảm nhận việc phát triển phần Generation cho pipeline (xử lý cuối `rag_answer.py`). Nhiệm vụ của tôi bao gồm:
- **Xây dựng Grounded Prompting:** Tôi hiện thực hóa các hàm `build_grounded_prompt` và `call_llm` để đảm bảo hệ thống có những phản hồi tuân thủ nguyên tắc Evidence-only, từ chối trả lời (Abstain) nếu context bị thiếu, và có format trích dẫn rõ ràng. 
- **Quy chuẩn Ops/Template:** Xóa bỏ hardcode các đoạn nội dung lớn trong code và đẩy System Directions ra ngoài tại `prompt_templates.txt`, giúp linh hoạt khi nâng cấp.
- **Diagnostics (Sprint 4):** Xây dựng module tính toán ước lượng Token Budget (dựa vào công thức `count // 4`) và gắn logger vào hàm sinh câu trả lời để bắn cảnh báo khi pipeline nạp quá số token cho phép, hoặc log lại quá trình khi mô hình đánh chặn thành công các yêu cầu không có tài liệu (Graceful Fallback). 

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

Điều tôi ngộ ra lớn nhất là sự khác biệt giữa mô hình sinh văn bản phổ thông (như ChatGPT) và mô hình LLM dùng trong hệ thống RAG doanh nghiệp. 

Ban đầu tôi nghĩ RAG chỉ là việc truyền thêm Context cho LLM đọc. Nhưng khi thiết kế hệ thống Prompt, việc tạo "Grounded Prompt" nghĩa là tôi phải khóa cứng (lock) toàn bộ sự "sáng tạo" của LLM bằng việc set `temperature=0` và bổ sung rule ràng buộc khắt khe: chỉ được phép dùng đúng kiến thức trong văn bản, và cực kỳ quan trọng là phải biết "Nói không" (Graceful Fallback). Qua lab này, thay vì dạy mô hình trả lời thế nào cho hay, tôi thấy Prompt Engineer trong RAG chủ yếu là dạy mô hình cách phòng thủ sự ảo giác (Hallucination) để bảo vệ hệ thống trước những truy vấn sai của người dùng.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

Điều khó khăn nhất tôi đối mặt trong quy trình ops quản lý Generation này là việc định lượng Token Budget trước khi gọi API mở (headroom). Để tránh các lỗi Context Limit hoặc hiệu ứng "Lost in the middle", tôi thiết lập Logger theo dõi cho `build_grounded_prompt`. Vì không muốn cài cắm library `tiktoken` tăng sức nặng, tôi phải xấp xỉ bằng character count.

Ngoài ra, khiến mô hình thực sự ngoan ngoãn từ chối hay không sợ trả lời sai là một bài toán khó. Nếu Prompt lỏng tay, LLM thường có xu hướng "muốn làm hài lòng user" mà đoán bừa nội dung, hay có xu hướng "sợ sai" nên không dám trả lời vì không tìm được từ khoá chính xác khi người dùng đưa vào prompt có chứa các từ khóa liên quan đến nội dung không có trong tài liệu.

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi:** `gq05` (Grading Question) — *"Contractor muốn vào hệ thống CMS làm thì theo quy định nào?"*

**Phân tích:**
Đây là một ca cực kì xuất sắc khi nhìn từ lăng kính của Generation Team (dấu hiệu False Abstain):
- Pipeline Dense đã lôi về đúng văn bản `access-control-sop.md`. Lẽ ra là thành công.
- Tuy nhiên do `top_k_select=3` chỉ giữ 3 chunk có điểm số vector cao nhất. Chunk chứa thông tin Scope áp dụng cho đối tượng Contractor nằm ở các chunk có độ lớn ưu tiên thấp hơn nên bị trượt mất khỏi array gửi tới vòng cuối.
- Kết quả: Khi thông tin vào Prompt của LLM, nội dung gửi vào bị thiếu mất phần Contractor. Nhờ vào cấn trúc Grounded Prompt mạnh mẽ tôi đã giới hạn, mô hình đã dứt khoát đưa ra phản hồi Abstain: *Xin lỗi, hệ thống hiện không có đủ dữ liệu...* thay vì cố ngụy tạo bịa câu trả lời.

Việc này cho thấy cơ chế phòng ngự của Prompt Engineer hoàn toàn hoạt động ổn định. Nó không những chặn ảo giác, mà còn phơi bày điểm yếu ở lớp trước đó: Retrieval đưa chưa đủ Context.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

Nếu có thêm thời lượng, tôi sẽ áp dụng hẳn thư viện đếm token chuẩn xác như `tiktoken` thay vì phép xấp xỉ `len // 4` để tính toán chính xác Headroom dự trữ. 
Thứ hai, tôi sẽ áp dụng thêm kỹ thuật Few-Shot Prompting, đưa vài ví dụ tích cực về cách định dạng tài liệu IT Helpdesk vào hẳn `prompt_templates.txt` để output được bọc Markdown table đẹp mắt và có xưng hô tông giọng đúng mực với nhân sự nội bộ hơn.
