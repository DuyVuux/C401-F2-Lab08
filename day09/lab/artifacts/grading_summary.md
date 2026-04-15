# Grading Run Summary — Lab Day 09

**Nhóm:** C401-F2  
**Chạy lúc:** 2026-04-14  
**Pipeline:** Supervisor-Worker (graph.py + 3 workers + MCP)  
**Tổng điểm raw ước tính:** ~72–80 / 96

---

## Kết quả từng câu

### gq01 — SLA P1 notification (10đ)
**Route:** `retrieval_worker` | **Confidence:** 0.59

**Answer:**
> Người nhận thông báo đầu tiên cho Ticket P1 là On-call engineer qua kênh Slack #incident-p1 và email incident@company.internal ngay lập tức. Deadline SLA resolution là 4 giờ kể từ khi ticket được tạo (22:47 → 02:47).

**Đánh giá:** ✅ Đúng — nêu đúng kênh thông báo và deadline SLA.

---

### gq02 — Temporal scoping hoàn tiền (Partial)
**Route:** `policy_tool_worker` | **Confidence:** 0.00 | **HITL:** triggered

**Answer:**
> Theo chính sách hoàn tiền, yêu cầu hoàn tiền phải được gửi trong vòng 7 ngày làm việc kể từ ngày đặt hàng. Đơn đặt ngày 31/01/2026 → deadline hoàn tiền là 09/02/2026. Yêu cầu gửi 07/02/2026 vẫn trong thời hạn. Tuy nhiên, chính sách v4 có hiệu lực từ 01/02/2026 — đơn đặt 31/01 có thể thuộc policy v3. CS Team cần xác nhận.

**Đánh giá:** ⚠️ Partial — pipeline tính đúng deadline nhưng flag temporal scoping. Có thể được partial credit.

---

### gq03 — Level 3 access approvers (10đ)
**Route:** `policy_tool_worker` | **Confidence:** 0.51 | **MCP:** `check_access_permission`, `get_ticket_info`

**Answer:**
> Để khắc phục P1 đang active, Engineer cần Level 3 access. Số người phải phê duyệt là **3**, bao gồm: Line Manager, IT Admin và IT Security. Người phê duyệt cuối cùng là IT Security.

**Đánh giá:** ✅ Đúng — 3 approvers, đúng thứ tự, MCP xác nhận.

---

### gq04 — Store credit 110% (10đ)
**Route:** `policy_tool_worker` | **Confidence:** 0.53

**Answer:**
> Khi khách hàng chọn nhận store credit thay vì hoàn tiền, họ nhận được **110%** so với số tiền gốc cần hoàn.

**Đánh giá:** ✅ Đúng — số liệu chính xác, có citation.

---

### gq05 — P1 escalation sau 10 phút (8đ)
**Route:** `retrieval_worker` | **Confidence:** 0.65

**Answer:**
> Theo đúng SLA, nếu on-call engineer không phản hồi sau 10 phút, hệ thống sẽ tự động escalate lên Senior Engineer.

**Đánh giá:** ✅ Đúng — escalation rule đúng.

---

### gq06 — Probation remote (10đ)
**Route:** `retrieval_worker` | **Confidence:** 0.59

**Answer:**
> Yêu cầu làm remote của nhân viên mới trong probation period không được chấp thuận, vì điều kiện để làm remote là nhân viên phải hoàn thành probation period. Nhân viên cần đợi hết probation trước khi đăng ký làm remote.

**Đánh giá:** ✅ Đúng — từ chối đúng với lý do rõ ràng.

---

### gq07 — Mức phạt tài chính SLA P1 (10đ)
**Route:** `retrieval_worker` | **Confidence:** 0.00 | **HITL:** triggered

**Answer:**
> Xin lỗi, hệ thống không có đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này. Vui lòng liên hệ IT Helpdesk (ext. 9000) hoặc CS Team (ext. 1234) để được hỗ trợ trực tiếp.

**Đánh giá:** ✅ Abstain đúng — mức phạt tài chính không có trong corpus. Không hallucinate.

---

### gq08 — Đổi mật khẩu 90 ngày (10đ)
**Route:** `retrieval_worker` | **Confidence:** 0.61

**Answer:**
> Nhân viên phải đổi mật khẩu sau mỗi **90 ngày**. Hệ thống sẽ cảnh báo trước **7 ngày** khi mật khẩu sắp hết hạn.

**Đánh giá:** ✅ Đúng — 2 số liệu chính xác, có citation.

---

### gq09 — P1 2am + Level 2 access tạm thời (16đ — câu khó nhất)
**Route:** `policy_tool_worker` | **Confidence:** 0.60 | **MCP:** `get_ticket_info`, `check_access_permission`

**Answer:**
> **(1) SLA P1 notification:**
> - Bước 1: On-call engineer nhận alert, xác nhận severity trong 5 phút
> - Bước 2: Notify Line Manager + IT Manager qua Slack và email
> - Bước 3: Escalate lên Senior Engineer nếu không resolve trong 30 phút
>
> **(2) Level 2 access tạm thời cho contractor:**
> - On-call IT Admin cấp quyền tạm thời (tối đa 24 giờ) sau khi được Tech Lead phê duyệt bằng lời
> - Phải log vào Security Audit Trail ngay lập tức
> - Revoke trong 24 giờ sau khi sự cố resolve

**Đánh giá:** ✅ Cross-document thành công — tổng hợp được cả SLA procedure và Access Control SOP trong 1 answer.

---

### gq10 — Flash Sale + lỗi nhà sản xuất (10đ)
**Route:** `policy_tool_worker` | **Confidence:** 0.54

**Answer:**
> Khách hàng không được hoàn tiền cho sản phẩm mua trong chương trình Flash Sale, vì theo chính sách, đơn hàng Flash Sale không được hoàn tiền — kể cả khi sản phẩm bị lỗi do nhà sản xuất.

**Đánh giá:** ✅ Đúng — Flash Sale exception áp dụng kể cả lỗi nhà sản xuất.

---

## Thống kê pipeline

| Metric | Giá trị |
|--------|---------|
| Tổng câu | 10 |
| Trả lời đầy đủ | 8/10 |
| Abstain (đúng) | 2/10 (gq07) |
| Abstain partial (gq02) | 1/10 |
| MCP tools được gọi | gq03, gq09 (2 tools mỗi câu) |
| HITL triggered | gq02, gq07 (confidence=0.0) |
| Avg confidence (non-abstain) | 0.58 |
| Source coverage | sla-p1-2026.pdf, refund-v4.pdf, access-control-sop.md, leave-policy-2026.pdf, helpdesk-faq.md |

## Phân tích điểm yếu

**gq02 — Temporal scoping:** Pipeline nhận diện đúng đơn 31/01 trước effective date policy v4, nhưng abstain vì không có policy v3 trong corpus. Fix: thêm document policy v3 hoặc implement `get_policy_version(date)` MCP tool.

**gq09 — Câu đặt câu hỏi:** Nếu câu hỏi tách riêng SLA và access thành 2 câu độc lập, pipeline sẽ xử lý tốt hơn. Câu ghép đôi (multi-task trong 1 query) là challenge chính của supervisor-worker: supervisor chỉ route 1 worker primary, không route song song.
