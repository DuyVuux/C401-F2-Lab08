# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Vũ Đức Duy  
**Vai trò:** Embed Owner (Verify embed + eval baseline) — Sprint 2b & 3  
**Ngày nộp:** 2026-04-15

---

## 1. Tôi phụ trách phần nào?

**Nhiệm vụ và môi trường:**

- Phụ trách chính việc kiểm chứng **ChromaDB Ingestion** (`day10_kb`), bảo đảm các bản ghi sạch từ ETL pipeline được đẩy vào vector store ổn định.
- Chạy Pipeline và thực hiện kịch bản test **Idempotency** (đảm bảo việc run nhiều lần một pipeline không làm tăng duplicate chunks, ghi đè metadata chính xác).
- Chạy và đánh giá Retrieval Baseline bằng script `eval_retrieval.py` cho cả kịch bản dữ liệu sạch `clean-baseline` (Sprint 2) và kịch bản `inject-bad` (Sprint 3 / Stress test).

**Kết nối với thành viên khác:**  
Tôi phụ thuộc cực lớn vào output của team Data Pipeline (những người làm Ingestion và Cleaning/Expectation) để có file data đầu vào chuẩn. Nhiệm vụ của tôi là kiểm định chốt chặn cuối cùng (Vector DB) trước khi handover thông tin, báo cáo before/after evidencce cho Hoàng Vĩnh Giang (Sprint 3 Owner) và Trần Quang Quí (Report/Docs Owner).

**Bằng chứng:** Thực thi thành công các run_id `clean-baseline`, `idempotent-test` và `inject-bad`. Xuất ra thành công các file `artifacts/eval/before_after_eval.csv` và `artifacts/eval/after_inject_bad.csv`. 

---

## 2. Một quyết định kỹ thuật

**Quyết định: Dọn dẹp collection DB thay vì sửa đổi logic code của pipeline khi gặp xung đột Embedding Model.**

Khi tiến hành chạy `etl_pipeline.py` lần đầu, tôi phát hiện pipeline bị crash do `ChromaDB` đang cố gắng sử dụng `openai` thay vì `sentence-transformers` theo như fix code cứng ở Sprint trước. Có hai ngã rẽ:

1. Sửa trực tiếp file `etl_pipeline.py` để đổi tên collection (vd: `day10_kb_v2`) phòng tránh chạm vào đồ cũ.
2. Quản lý ở cấp hệ điều hành/môi trường bằng cách xóa `chroma_db` cục bộ để làm sạch không gian.

Tôi đã quyết định chọn **cách 2** — Dọn dẹp (`rm -rf ./chroma_db`) để hệ thống chạy lại từ đầu.  
**Trade-off:** Cách này tuân thủ nguyên tắc tuyệt đối "không sửa code, không đụng vào sprint của người khác" dành cho role của tôi, thể hiện sự rạch ròi về role (tôi là Execution/Verification - không phải Code Maintainer của phần này). Tuy làm mất history testing tạm của bạn trước đó, nó đổi lại được một baseline evaluation đúng nghĩa và sạch.

---

## 3. Một lỗi đã xử lý

**Lỗi: System ImportError & ValueError (Embedding function conflict)**

- **Thiếu module:** Máy thiếu thư viện `sentence-transformers`. Hệ thống chỉ cho phép cài đặt qua bộ quản lý môi trường (uv/venv).
- **Function Conflict:** Như đã nêu trên, khi chạy sinh ra lỗi `ValueError: An embedding function already exists... new: sentence_transformer vs persisted: openai`.

**Fix:** Thay vì làm phiền các thành viên khác sửa lỗi, tôi tự dùng `uv pip install sentence-transformers` vào môi trường ảo hiện tại. Tiếp đó tự phát hiện đường dẫn ChromaDB thông qua `os.environ.get("CHROMA_DB_PATH")` trong code và dùng command terminal clear hoàn toàn data cũ rác. Lỗi được giải quyết gọn gàng ở môi trường Terminal (Operations) thay bì đè Source Code.

---

## 4. Bằng chứng trước / sau

Tôi đã thực thi qua kịch bản đánh giá chất lượng Retrieval:

**Trước (Tình huống rủi ro / Stress test với Data bẩn — `after_inject_bad.csv`):**
```
q_refund_window, Khách hàng có bao nhiêu... → top1_doc_id: policy_refund_v4 → hits_forbidden=yes
```
*(Chạy cờ `--no-refund-fix --skip-validate`, chunk bị lỗi policy (14 ngày) vẫn lọt vào, dẫn tới query bị kéo theo rác).*

**Sau (kịch bản chuẩn sạch Baseline — `before_after_eval.csv`):**
```
q_refund_window, Khách hàng có bao nhiêu... → top1_doc_id: it_helpdesk_faq → hits_forbidden=no
```
*(Rule của pipeline bắt lỗi và loại chunk "14 ngày làm việc", `day10_kb` hoàn toàn sạch).*

Điều này cung cấp minh chứng rõ ràng việc thiết lập **Expectations / Data Quality** ảnh hưởng lớn như thế nào đến Retrieval (RAG) đầu ra. Nó khẳng định tầm quan trọng của Pipeline ETL phòng thủ.

---

## 5. Cải tiến tiếp theo

Nếu có thêm thời gian phát triển vòng lặp tới, tôi đề xuất:
1. **Cô lập Embedding Scope thông qua `.env`:** Quy định sử dụng environment variables (`EMBEDDING_MODEL`...) nghiêm ngặt hơn và yêu cầu team thiết kế thêm kịch bản fall-back tạo collection mới tự động khi model embeddings bị override.
2. **Auto-Eval ở đuôi Pipeline:** Đưa logic kiểm thử eval (`eval_retrieval.py`) vào chạy auto như một bước cuối cùng trong CI thay vì là một dòng bash command rời. Chặn release model index nếu `hits_forbidden=yes` bị trigger.
