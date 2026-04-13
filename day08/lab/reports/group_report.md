# Báo Cáo Nhóm — Lab Day 08: RAG Pipeline

**Nhóm:** C401-F2  
**Ngày nộp:** 2026-04-13  

---

## 1. Tổng quan hệ thống

Nhóm xây dựng **trợ lý nội bộ cho khối CS và IT Helpdesk** — trả lời câu hỏi về chính sách hoàn tiền, SLA ticket, quy trình cấp quyền truy cập, và FAQ bằng chứng cứ retrieve có kiểm soát từ 5 tài liệu nội bộ.

Pipeline hoàn chỉnh gồm 3 tầng:
1. **Indexing** (`index.py`): Preprocess → Chunk theo section/paragraph → Embed → Lưu ChromaDB
2. **Retrieval + Generation** (`rag_answer.py`): Query → Dense/Hybrid Retrieve → Rerank → Grounded Answer
3. **Evaluation** (`eval.py`): LLM-as-Judge chấm 4 metrics → Scorecard → A/B Comparison

---

## 2. Phân công nhiệm vụ

| Thành viên | Vai trò | Sprint chính | Files |
|------------|---------|-------------|-------|
| Hoàng Vĩnh Giang | Data Processing Engineer | Sprint 1 | `data_ingestor.py` |
| Nhữ Gia Bách | Core AI Engineer | Sprint 1–2 | `index.py` |
| Vũ Đức Duy | Search & Relevance Engineer | Sprint 2–3 | `rag_answer.py` (retrieval) |
| Đoàn Nam Sơn | LLM Ops & Prompt Engineer | Sprint 2–3 | `rag_answer.py` (generation) |
| Trần Quang Quí | Evaluation Automation Engineer | Sprint 1–4 | `eval.py`, `test_questions.json` |

---

## 3. Quyết định kỹ thuật quan trọng

### Chunking
- **Strategy:** Heading-based trước (split theo `=== Section ===`), sau đó paragraph-based nếu section quá dài
- **Chunk size:** 400 tokens (~1600 ký tự), Overlap: 80 tokens (~320 ký tự)
- **Lý do:** Tài liệu có cấu trúc heading rõ ràng → cắt theo heading tránh mất ngữ cảnh giữa các điều khoản. Overlap đảm bảo câu hỏi liên section vẫn retrieve được đủ context.

### Retrieval Variant — Hybrid (Dense + BM25)
- **Lý do chọn Hybrid:** Corpus chứa cả câu văn tự nhiên (chính sách hoàn tiền) lẫn keyword/mã chuyên ngành (`P1`, `ERR-403`, `Level 3`). Dense search giỏi paraphrase; BM25 giỏi exact match. Kết hợp qua Reciprocal Rank Fusion (RRF) cho kết quả tốt hơn cả hai đơn lẻ.

### Evaluation — LLM-as-Judge
- **Lý do chọn LLM-as-Judge:** Chấm thủ công 10 câu × 2 configs × 4 metrics = 80 judgements — không khả thi trong 60 phút. LLM-as-Judge với `temperature=0` cho kết quả nhất quán và tự động hóa được.

---

## 4. Scorecard — Kết quả

Chạy `eval.py` với 10 câu hỏi trong `data/test_questions.json`, LLM-as-Judge (GPT-4o-mini, temperature=0).

### Baseline (Dense, no rerank)

| Metric | Average |
|--------|---------|
| Faithfulness | 4.10/5 |
| Answer Relevance | 4.20/5 |
| Context Recall | 5.00/5 |
| Completeness | 4.30/5 |

### Variant (Hybrid + LLM Rerank + Recency Penalty)

Variant sử dụng dense retrieval kết hợp LLM rerank (GPT-4o-mini chấm lại top-3) và recency penalty (phạt tài liệu cũ theo `effective_date`). BM25 sparse chưa build được index nên fallback về dense.

| Metric | Average | Delta vs Baseline |
|--------|---------|------------------|
| Faithfulness | 4.20/5 | +0.10 |
| Answer Relevance | 4.20/5 | ±0.00 |
| Context Recall | 5.00/5 | ±0.00 |
| Completeness | 4.10/5 | -0.20 |

### Phân tích per-question

| ID | Category | Baseline F/R/Rc/C | Variant F/R/Rc/C | Better? |
|----|----------|-------------------|------------------|---------|
| q01 | SLA | 5/5/5/4 | 5/5/5/4 | Tie |
| q02 | Refund | 5/5/5/5 | 5/5/5/5 | Tie |
| q03 | Access Control | 5/5/5/5 | 5/5/5/5 | Tie |
| q04 | Refund | 5/5/5/5 | 5/5/5/5 | Tie |
| q05 | IT Helpdesk | 5/5/5/5 | 5/5/5/5 | Tie |
| q06 | SLA | 5/5/5/5 | 5/5/5/5 | Tie |
| q07 | Access Control | **4**/5/5/**5** | **5**/5/5/**3** | Baseline |
| q08 | HR Policy | 5/5/5/5 | 5/5/5/5 | Tie |
| q09 | Insufficient Context | 1/1/N/A/3 | 1/1/N/A/3 | Tie |
| q10 | Refund | 1/1/5/1 | 1/1/5/1 | Tie |

> **Ghi chú q07:** LLM rerank thay đổi thứ tự chunks → answer variant cover tốt hơn về Faithfulness (5 vs 4) nhưng bị giảm Completeness (3 vs 5). Đây là trade-off của reranking: ưu tiên chunk grounded nhất nhưng có thể bỏ qua chunk chứa thông tin bổ sung.  
> **Ghi chú q09/q10:** Model abstain đúng → Faithfulness=1 là artifact của LLM-as-Judge, không phải lỗi pipeline.

---

## 5. Grading Questions — Kết quả

Chạy pipeline `dense` với `grading_questions.json`. Kết quả: **9/10 câu đúng**.

| ID | Điểm | Kết quả | Nhận xét |
|----|------|---------|----------|
| gq01 | 10 | ✅ | Nêu đúng 4h (hiện tại) và 6h (cũ), có citation version |
| gq02 | 10 | ✅ | Retrieve đúng 2 docs: VPN bắt buộc + tối đa 2 thiết bị |
| gq03 | 10 | ✅ | Nêu đủ 2 ngoại lệ: Flash Sale và sản phẩm đã kích hoạt |
| gq04 | 8 | ✅ | Đúng 110%, nêu rõ tùy chọn không bắt buộc |
| gq05 | 10 | ❌ | **False abstain** — retrieve đúng doc nhưng top-3 chunks không cover Section 1 (scope contractor) |
| gq06 | 12 | ✅ | Cross-document thành công: on-call IT Admin, 24h, log Security Audit |
| gq07 | 10 | ✅ | Abstain đúng — không bịa mức phạt khi không có trong tài liệu |
| gq08 | 10 | ✅ | Phân biệt đúng 2 ngữ cảnh "3 ngày": nghỉ phép năm vs nghỉ ốm |
| gq09 | 8 | ✅ | Đúng: 90 ngày, nhắc 7 ngày trước, có SSO portal link |
| gq10 | 10 | ✅ | Đúng: không áp dụng đơn trước 01/02/2026, đề cập v3 |

**Phân tích gq05 — False Abstain (câu thất bại):**

Pipeline retrieve đúng `it/access-control-sop.md` nhưng vẫn trả về abstain. Nguyên nhân: `top_k_select=3` chỉ giữ 3 chunks cao nhất — Section 1 (phạm vi áp dụng cho contractor) và Level 4 detail nằm ở các chunks thấp hơn, không vào prompt. Model thấy context thiếu → abstain thay vì trả lời.

**Fix tiềm năng:** Tăng `top_k_select` từ 3 lên 5, hoặc implement rerank để ưu tiên chunk có keyword "contractor/Level 4" vào top-3.

**Phân tích gq06 — Cross-document thành công (câu khó nhất, 12 điểm):**

Dense retrieval tự nhiên retrieve được cả `access-control-sop.md` (emergency escalation) và `sla-p1-2026.pdf` (on-call process) vào cùng một lần query. Grounded prompt tổng hợp được: on-call IT Admin, phê duyệt Tech Lead bằng lời, 24 giờ, log Security Audit.

---

## 6. Bài học và hạn chế

### Điều hoạt động tốt
- **Dense retrieval + ChromaDB**: Context Recall đạt 5.00/5 — embedding model `text-embedding-3-small` retrieve đúng source cho gần như mọi câu hỏi.
- **Grounded prompt + abstain logic**: q09 (ERR-403-AUTH) và q10 (VIP refund) model từ chối đúng thay vì hallucinate — cơ chế abstain hoạt động hiệu quả.
- **LLM-as-Judge tự động hóa**: Đánh giá 20 runs × 4 metrics = 80 judgements trong ~3 phút, nhất quán và reproducible.

### Hạn chế còn lại
- **Hybrid/BM25 chưa implement**: Variant fallback về dense nên A/B comparison không phản ánh lợi thế của hybrid thực sự. q07 (alias "Approval Matrix" → "Access Control SOP") là use case điển hình sẽ được cải thiện bằng BM25.
- **LLM-as-Judge bias với abstain**: Câu q09 model abstain đúng nhưng Faithfulness bị chấm 1/5 vì không có chunks grounded. Cần rule đặc biệt: *nếu answer là abstain và expected_sources rỗng → skip faithfulness*.
- **Chunk overlap chưa tối ưu**: q01 và q08 completeness chỉ 4/5 — một số chi tiết nhỏ bị cắt giữa chunk boundaries.

### Nếu có thêm thời gian
- Implement BM25 + RRF thực sự để test q07 alias case
- Thêm rule xử lý abstain trong scoring (Faithfulness = N/A khi answer = abstain phrase)
- Thêm câu calibration vào test set để kiểm tra bias của judge
- Thử HyDE (Hypothetical Document Embeddings) cho query transformation
