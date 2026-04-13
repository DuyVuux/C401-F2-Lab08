# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Trần Quang Quí  
**Vai trò trong nhóm:** Evaluation Automation Engineer (Metrics & Scorecards)  
**Ngày nộp:** 2026-04-13  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi đã làm gì trong lab này? (100-150 từ)

Trong lab này, tôi phụ trách toàn bộ tầng evaluation của pipeline — bao gồm `eval.py`, `data/test_questions.json`, và `docs/tuning-log.md`.

Cụ thể, tôi implement ba scoring function theo cơ chế LLM-as-Judge: `score_faithfulness()`, `score_answer_relevance()`, và `score_completeness()`. Cả ba hàm đều gọi chung qua một helper `_call_judge()` — gửi prompt có cấu trúc tới `gpt-4o-mini` với `temperature=0` để đảm bảo kết quả chấm điểm nhất quán, và parse JSON trả về với xử lý lỗi rõ ràng. Metric thứ tư `score_context_recall()` đã có sẵn trong template và tôi review để đảm bảo logic partial-match đúng với format `source` trong tài liệu. Ngoài ra, tôi uncomment phần variant và `compare_ab()` trong `main` để khi team hoàn thành Sprint 3, chỉ cần chạy `python3 eval.py` là ra toàn bộ scorecard baseline, variant, và bảng delta A/B.

---

## 2. Điều tôi hiểu rõ hơn sau lab này (100-150 từ)

Trước lab này, tôi nghĩ "đánh giá RAG" nghĩa là xem câu trả lời có đúng không. Sau khi implement 4 metric, tôi nhận ra đây là bốn câu hỏi hoàn toàn khác nhau, mỗi cái đo một tầng khác nhau trong pipeline:

- **Context Recall** đo retriever: có mang về đúng tài liệu không?
- **Faithfulness** đo grounding: model có bịa thêm gì ngoài context không?
- **Answer Relevance** đo generation: model có trả lời đúng câu hỏi không?
- **Completeness** đo so với ground truth: có thiếu điều kiện ngoại lệ, con số quan trọng nào không?

Khi test với mock data, tôi thấy rõ điều này: answer "SLA P1 là 4 giờ" nhận Relevance=5 (đúng chủ đề) nhưng Faithfulness=1 (không grounded đầy đủ, bỏ qua "15 phút first response") và Completeness=3 (thiếu thông tin so với expected). Một câu trả lời có thể "nghe đúng" nhưng thực sự kém ở nhiều chiều khác nhau.

---

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn (100-150 từ)

Điều tôi không ngờ nhất là LLM-as-Judge khắt khe hơn tôi nghĩ với Faithfulness. Trong mock test, answer chỉ nói "4 giờ" mà bỏ qua "15 phút first response" — tôi nghĩ judge sẽ cho khoảng 3/5 vì phần lớn vẫn grounded. Nhưng judge cho 1/5 với lý do: thông tin trong answer không sai, nhưng không đại diện đầy đủ cho context đã retrieve, tức là model đã "chọn lọc" thông tin theo cách có thể gây hiểu nhầm.

Điều này cho thấy Faithfulness không chỉ kiểm tra "có bịa không" mà còn kiểm tra "có cherry-pick thông tin một cách sai lệch không". Đây là một failure mode tinh tế hơn hallucination thông thường — và chính xác là lý do cần đo bằng code thay vì đọc tay.

Khó khăn kỹ thuật là xử lý JSON parse error từ LLM: đôi khi model trả về text thừa bao quanh JSON. Tôi giải quyết bằng cách thêm `strip()` và `try/except` rõ ràng thay vì để crash.

---

## 4. Phân tích một câu hỏi trong scorecard (150-200 từ)

**Câu hỏi:** `q09` — *"ERR-403-AUTH là lỗi gì và cách xử lý?"*

**Kết quả thực tế (từ scorecard):** Faithfulness=1, Relevance=1, Context Recall=N/A, Completeness=4

**Phân tích:**

Đây là câu hỏi kiểm tra khả năng **abstain** — thông tin về `ERR-403-AUTH` không có trong bất kỳ tài liệu nào (`expected_sources: []`). Pipeline đã trả về đúng: *"Xin lỗi, hệ thống hiện không có đủ dữ liệu trong tài liệu để trả lời câu hỏi này."*

Tuy nhiên, scorecard cho Faithfulness=1 và Relevance=1 — điểm thấp nhất trong toàn bộ test set. Đây là **artifact của LLM-as-Judge**: judge chấm Faithfulness dựa trên "answer có grounded trong retrieved chunks không" — khi answer là câu từ chối và không có chunks, judge tự động cho điểm 1. Đây là false negative, không phải lỗi pipeline.

Điều thú vị là Completeness=4: judge nhận ra rằng câu từ chối phù hợp với expected answer (cũng là từ chối — "Không tìm thấy thông tin về ERR-403-AUTH..."), nên chấm tương đối cao.

Bài học: cần thêm rule trong scorer — *nếu answer khớp abstain phrase và expected_sources rỗng → đánh dấu Faithfulness=N/A thay vì 1*. Đây là vấn đề thiết kế evaluation, không phải RAG.

---

## 5. Nếu có thêm thời gian, tôi sẽ làm gì? (50-100 từ)

Tôi sẽ thêm **câu hỏi calibration** vào test set: một câu biết chắc pipeline trả lời đúng và một câu biết chắc sai — để kiểm tra xem judge có nhất quán không (nếu câu rõ ràng đúng mà judge cho 3/5 thì judge bị bias). 

Ngoài ra, tôi muốn thử chạy cùng một câu qua judge **ba lần** để đo variance — nếu score dao động nhiều, cần tăng context trong prompt hoặc đổi model mạnh hơn cho tầng judge.
