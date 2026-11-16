# Benchmark Day 7

**Trạng thái:** bản nháp ngày 2026-11-16, soạn **trước khi chạy bất kỳ retrieval hay agent nào của Day 7**. Học viên đọc lại, xác nhận rồi đổi dòng này thành `FROZEN <ngày>` trước khi chạy dev. Sau mốc đó không sửa câu test.

## 1. Thành phần

| Loại câu | Dev | Test | Yêu cầu tối thiểu |
|---|---:|---:|---|
| Có đáp án | 16 (d01–d16) | 6 (t01–t06) | 15 / 5 |
| Thiếu bằng chứng | 3 (dn01–dn03) | 3 (tn01–tn03) | 2 / 2 |
| **Tổng** | **19** | **9** | 17 / 7 |

- **Corpus:** `mbb-bctc-hn-q3-2026`, Báo cáo tài chính hợp nhất Quý III/2026 của MB. Có 59 trang nội dung (bản scan, đã OCR); 2 trang công văn công bố thông tin bị loại, giống Day 6. Nguồn và quyền sử dụng xem `data/manifest.json` của Day 6.
- **Câu có đáp án:** lấy nguyên từ benchmark Day 6 v1.0 (FROZEN 2026-11-14). Cả 22 evidence đã được đối chiếu với ảnh scan gốc, và evidence giữ nguyên văn OCR. Các loại câu: `truc_tiep`, `dien_dat_lai`, `dieu_kien_ngoai_le`, `bang`, `metadata_filter`.
- **Câu thiếu bằng chứng:** soạn mới cho Day 7 trong `unanswerable.json`. Chúng gần chủ đề và có trang "gây nhiễu" (`near_topic_pages`). Ví dụ dn02 hỏi số khách hàng, gần d02 (số chi nhánh) và d04 (số nhân viên); tn01 hỏi kế hoạch lợi nhuận, gần lợi nhuận thực hiện ở tr.6.
- **Chia dev/test theo chủ đề:** test dùng chủ đề không có câu dev tương ứng. Với câu thiếu bằng chứng, chủ đề dev (CAR, số khách hàng, lãi suất huy động) khác chủ đề test (kế hoạch lợi nhuận, giá cổ phiếu, nợ xấu công ty con).
- **Rủi ro rò rỉ** (kế thừa Day 6): t03 (mua nợ, tr.16) gần d12 (bán nợ, tr.17).
- **Tính độc lập của test:** Day 6 chỉ chạy test một lần, sau khi đã chốt chiến lược trên dev, và không chỉnh gì theo test. Kết quả retrieval test của Day 6 đã công bố (dense B/C Evidence Hit@3 6/6), nên người làm biết test tương đối dễ với dense. Ở Day 7, mọi lựa chọn chỉ dựa trên dev. Nếu lỡ dùng test để chỉnh, phải soạn test mới (RULES.md).

## 2. Cách kiểm tra câu thiếu bằng chứng

Không dựa vào top-k. `python -m src.benchmark validate` tìm từng thuật ngữ trong `absent_terms` (không phân biệt hoa thường, khớp ranh giới từ) trên **toàn bộ 61 trang OCR**, kể cả 2 trang bị loại. Kết quả hiện tại: 0/61 trang cho mọi thuật ngữ. `absence_reason` ghi phần gần chủ đề nhưng không trả lời được câu hỏi. Hai thuật ngữ ban đầu bị loại vì trùng nghĩa khác trong tài liệu:
- "tài sản có rủi ro" ở tr.20–21 là phân loại khoản phải thu;
- "chỉ tiêu" là tên dòng/cột bảng.

Giới hạn: tìm theo từ khóa trên OCR không bao quát mọi cách diễn đạt và có thể sót do lỗi OCR. Lý do vắng mặt cũng dựa trên hiểu biết về nội dung một BCTC quý. Người chấm nên xem lại `near_topic_pages` trên bản scan.

## 3. Định nghĩa metric (chốt trước khi chạy)

- **Hit** (giữ nguyên định nghĩa Day 6): một chunk là hit khi `source_id` và `page` khớp một phần tử `gold`, và chunk chứa **trọn** `evidence` sau khi chuẩn hóa (NFC, gộp khoảng trắng, không phân biệt hoa thường). Các phần tử `gold` là evidence thay thế (`gold_mode: any`); chỉ d16 có 2 phần tử (tr.56 hoặc tr.59).
- **Hit@1 / Evidence Hit@3:** top-1 / top-3 có ít nhất một hit. Mẫu số là số câu có đáp án (dev 16, test 6). Pipeline dùng top-k khác 3 vẫn phải xuất top-3 theo thứ hạng cuối cùng. Với pipeline nhiều bước, lấy ranking của lượt đầu tiên với query gốc, còn pipeline đầy đủ báo riêng.
- **Context Evidence Rate:** câu được tính khi context cuối gửi model chứa trọn evidence (đã chuẩn hóa), nằm trong đoạn có nhãn nguồn và trang khớp `gold`. Mẫu số là số câu có đáp án. Đơn vị context budget là ký tự (gồm nhãn nguồn); báo thêm token đầu vào của model.
- **Câu thiếu bằng chứng** không vào mẫu số của các metric retrieval/context.
- **Filter:** trường `filter` (chỉ `section`, có ở d15, d16, t05, t06) là input giả định người dùng đưa trước. Cấu hình có dùng filter phải ghi rõ, và không được suy filter từ gold.
- **Agent** (chấm thủ công, theo BENCHMARK.md §3):

| Metric | Cách chấm |
|---|---|
| Tool use | Số câu có ít nhất 1 lượt retrieval / số câu chạy thành công. Báo phân bố số lượt gọi. |
| Grounded answer | 0 = sai/thiếu evidence; 1 = đúng một phần (thiếu điều kiện, đơn vị); 2 = đúng và đủ so với `expected_answer`. Câu có đáp án mà agent từ chối thì chấm 0. |
| Citation hợp lệ | Citation có trong context **và** người chấm đọc thấy nó hỗ trợ câu trả lời / tổng citation. |
| Abstention | Số câu thiếu bằng chứng được từ chối mà không kèm khẳng định vô căn cứ / số câu thiếu bằng chứng. Báo thêm số câu có đáp án bị từ chối nhầm. |
| Context 0/1/2 | Chấm ít nhất 5 câu test có đáp án cho baseline và cấu hình chọn: 0 = không có evidence; 1 = có nhưng thiếu điều kiện hoặc nguồn; 2 = đủ. |

Lỗi model hoặc vector store ghi `status: error`, báo riêng và không thay bằng kết quả giả.

## 4. Tiêu chí chọn cấu hình trên dev (đề xuất, chốt trước khi chạy)

1. Trung bình grounded answer (/2) trên 16 câu dev có đáp án.
2. Ràng buộc: abstention dev ≥ 2/3 và từ chối nhầm ≤ 2/16. Cấu hình vi phạm bị loại.
3. Nếu hòa: Context Evidence Rate dev, rồi Evidence Hit@3 dev, rồi Hit@1 dev.
4. Nếu vẫn hòa: chọn cấu hình có trung vị thời gian mỗi câu và chi phí thấp hơn.

Chạy test đúng một lần cho baseline và cấu hình đã chọn.

## 5. File và lệnh

| File | Nội dung |
|---|---|
| `unanswerable.json` | Nguồn soạn tay của 6 câu thiếu bằng chứng |
| `questions.json` | Benchmark chuẩn (28 câu, schema `data/README.md`); sinh bằng `build` |
| `cases.json` | `id/split/answerable` dùng cho `starter/agent_metrics.py` |
| `starter/data/day6/questions.json` | Bản cho `starter/baseline.py`: chỉ câu có đáp án, evidence là chuỗi nguyên văn trong chunk (không commit) |

```bash
python -m src.day6 export        # cần DB Day 6 (xem src/README.md)
python -m src.benchmark build    # ghép Day 6 + unanswerable.json, rồi validate
python -m src.benchmark validate
```
