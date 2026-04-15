# Báo cáo cá nhân — Hoàng Vĩnh Giang

**Họ và tên:** Hoàng Vĩnh Giang  
**Vai trò:** Inject Corruption & Before/After Eval  
**Độ dài:** ~450 từ

---

## 1. Phụ trách

Tôi phụ trách việc thiết kế và triển khai quy trình inject corruption vào dữ liệu (dirty data) và thực hiện đánh giá before/after để kiểm chứng chất lượng pipeline. Cụ thể, tôi phát triển hàm `inject_corruption` trong `quality/inject_corruption.py` để tự động tạo ra các lỗi phổ biến (missing date, duplicate, encoding error, empty content) và xây dựng hàm `run_before_after_eval` để so sánh kết quả trả lời giữa dữ liệu sạch và dữ liệu đã bị inject lỗi. Tôi phối hợp với nhóm để đảm bảo dirty pipeline sinh ra đúng file eval và manifest phục vụ so sánh.

**Bằng chứng:** commit file `inject_corruption.py`, kết quả file `artifacts/eval/eval_inject_bad.csv`, `artifacts/manifests/manifest_inject-bad.json`.

---

## 2. Quyết định kỹ thuật

**Inject bằng CLI:** Tôi chọn phương án inject lỗi thông qua CLI flag (`--no-refund-fix --skip-validate`) thay vì viết script riêng, giúp quy trình kiểm thử linh hoạt và dễ tái lập. Dirty records được sinh ra đúng chuẩn contract, không làm thay đổi logic core của pipeline.

**Eval before/after:** Hàm eval tự động ghi nhận kết quả trả lời của từng query trên cả clean và dirty, giúp nhóm dễ dàng so sánh và truy vết nguyên nhân khi có expectation fail.

---

## 3. Sự cố / anomaly

Trong quá trình inject, tôi phát hiện nếu không prune vector store đúng cách, chunk "14 ngày làm việc" vẫn có thể xuất hiện trong top-k dù cleaned đã đúng. Đã phối hợp với nhóm để bổ sung bước prune sau khi inject nhằm đảm bảo tính idempotent và kết quả eval chính xác.

---

## 4. Before/after

**Log:** Expectation `refund_no_stale_14d_window` (E3) PASS trên pipeline sạch, FAIL (violations=1) khi inject lỗi (log run_id=inject-bad).

**CSV:** Dòng `q_refund_window` có `hits_forbidden=no` trong `before_after_eval.csv`, chuyển thành `hits_forbidden=yes` trong `eval_inject_bad.csv`.

---

## 5. Cải tiến thêm 2 giờ

Nếu có thêm thời gian, tôi sẽ tự động sinh bảng so sánh metric_impact và tích hợp kiểm tra contract/data_contract.yaml vào expectation để đảm bảo rule luôn đồng bộ giữa code và contract.