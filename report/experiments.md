# Nhật ký thử nghiệm (dev)

Mọi thử nghiệm chạy trên dev (16 câu có đáp án, 3 câu thiếu bằng chứng) với `gpt-4.1-mini`, temperature 0, index B, top-3, tối đa 4 lượt search, ngân sách 6000 ký tự, trừ khi ghi khác. Giả thuyết được ghi **trước khi chạy**.

## Baseline (prompt v1), 2026-11-16, nhãn đã được học viên xác nhận

| Agent + retriever | Grounded 0/1/2 (mean) | Từ chối đúng | Từ chối nhầm | Citation hợp lệ | invalid_citations | Trung vị | Chi phí |
|---|---|---|---|---|---|---|---|
| dense | 4/1/11 (1.44) | 3/3 | 3/16 | 11/14 | 9 | 4.3 s | $0.037 |
| bm25 | 0/1/15 (1.94) | 3/3 | 0/16 | 17/18 | 8 | 3.5 s | $0.027 |
| hybrid_rerank | 0/0/16 (2.00) | 2/3 | 0/16 | 19/19 | 7 | 6.6 s | $0.081 |

Lỗi dev đã phân tích:
1. **Query lặp lại (dense: d01, d02, d15).** Agent search lại với truy vấn gần như giống hệt, dense trả cùng chunk sai, nên agent từ chối nhầm.
2. **Citation không ghi trong câu trả lời.** Toàn bộ 24 sự kiện `invalid_citations` (ở cả 3 cấu hình) đều là `not_inline`. Lượt sửa lỗi cứu được, nhưng tốn thêm một lượt gọi model.
3. **Lệch giữa nội dung và cờ từ chối (rerank: dn03).** Nội dung nói "không cung cấp" nhưng `abstain=false`.
4. **Đọc sai dòng bảng (d13: dense, bm25).** Agent nói 521.748 là số "sau dự phòng", trong khi đó là số trước dự phòng.

## Cải thiện 1: prompt v2 (`--prompt v2`)

- **Thay đổi:** thêm 4 quy tắc vào system prompt, mỗi quy tắc nhắm vào một lỗi ở trên: đổi từ khóa khi tìm lại, có ví dụ định dạng `[chunk_id]`, kết luận "không có" thì phải `abstain=true`, ghi rõ trước/sau dự phòng. Retriever, top-k và ngân sách giữ nguyên.
- **Giả thuyết:**
  - (a) `invalid_citations` giảm mạnh (24 xuống gần 0), nên số lượt gọi model và độ trễ giảm;
  - (b) dense từ chối nhầm ít hơn 3/16 nhờ đổi query;
  - (c) rerank từ chối đúng 3/3;
  - (d) d13 đúng ở bm25.
- **Rủi ro:** quy tắc 9 có thể làm tăng từ chối nhầm.

## Cải thiện 2: prompt v2 + filter người dùng + tool lấy đoạn lân cận (`--prompt v2 --use-filter --neighbors`)

- **Thay đổi:** harness áp `filter` (section) mà người dùng cung cấp cho d15 và d16, và agent được gọi `get_neighbors` để lấy đoạn trước/sau trên cùng trang.
- **Giả thuyết:**
  - (a) filter giúp dense ở d15, câu mà v1 từ chối nhầm;
  - (b) đoạn lân cận ít tác động vì dev đã gần trần với bm25/rerank, chủ yếu làm tăng context và chi phí.
- **Đo:** grounded answer, Context Evidence Rate, số ký tự context, chi phí.

## Kết quả (dev, chạy 2026-11-16)

Nhãn của baseline đã được học viên xác nhận. Nhãn của 6 cấu hình cải thiện là **bản nháp, chờ xác nhận** (`src/dev_review_draft.py`).

| Cấu hình | Grounded 0/1/2 (mean) | Citation hợp lệ | Từ chối đúng | Từ chối nhầm | Context Evidence Rate | invalid_citations | Lượt gọi model | Trung vị | Chi phí |
|---|---|---|---|---|---|---|---|---|---|
| dense v1 (baseline) | 4/1/11 (1.44) | 11/14 | 3/3 | 3/16 | 12/16 | 9 | 61 | 4.3 s | $0.037 |
| bm25 v1 | 0/1/15 (1.94) | 17/18 | 3/3 | 0/16 | 16/16 | 8 | 51 | 3.5 s | $0.027 |
| rerank v1 | 0/0/16 (2.00) | 19/19 | 2/3 | 0/16 | 16/16 | 7 | 47 | 6.6 s | $0.081 |
| dense v2 | 2/2/12 (1.63) | 13/15 | 3/3 | 2/16 | 13/16 | 4 | 55 | 4.1 s | $0.036 |
| **bm25 v2** | **0/0/16 (2.00)** | 18/18 | 3/3 | 0/16 | 16/16 | 4 | 45 | 4.2 s | **$0.027** |
| rerank v2 | 0/0/16 (2.00) | 20/21 | 2/3 | 0/16 | 16/16 | 5 | 48 | 37 s* | $0.095 |
| dense v2+filter+neighbors | 3/2/11 (1.50) | 13/16 | 3/3 | 3/16 | 12/16 | 5 | 62 | 4.1 s | $0.044 |
| bm25 v2+filter+neighbors | 0/0/16 (2.00) | 20/20 | 3/3 | 0/16 | 16/16 | 5 | 52 | 3.7 s | $0.036 |
| rerank v2+filter+neighbors | 0/0/16 (2.00) | 19/19 | 3/3 | 0/16 | 16/16 | 5 | 51 | 21 s* | $0.108 |

\* **Độ trễ của rerank v2 không đáng tin:** trong lúc chạy song song, lời gọi rerank mất 30–147 s và có `APIConnectionError` (1 câu ở v2, 5 câu ở v2fn). Các câu này đã được chạy lại bằng `--rerun-errors`, lỗi cũ vẫn giữ trong `previous_errors`. Lần chạy trước đó, rerank chỉ mất khoảng 2.5 s mỗi câu.

### Đối chiếu với giả thuyết

**Cải thiện 1, prompt v2:**
- (a) **Đúng một phần.** `invalid_citations` giảm khoảng một nửa (24 → 13), lượt gọi model giảm (bm25 51 → 45), nhưng không về 0.
- (b) **Đúng một phần.** Dense từ chối nhầm 3 → 2/16 (d02 được cứu nhờ đổi query), còn d01 và d15 vẫn trượt vì dense không lấy được trang gold dù query đã khác.
- (c) **Sai.** Rerank dn03 vẫn trả lời, lại còn tệ hơn: khẳng định lãi suất chứng chỉ tiền gửi là lãi suất tiết kiệm. Rerank đưa tr.44 lên đầu, và câu chữ gần chủ đề đủ để model "trả lời".
- (d) **Đúng.** d13 đúng ở bm25 v2 và rerank v2. Dense v2 cũng hết nói sai về dự phòng nhưng vẫn thiếu tiêu chí.

**Cải thiện 2, thêm filter và đoạn lân cận:**
- (a) **Sai.** Dense v2fn vẫn từ chối nhầm d15 dù đã lọc section (90 chunk). Dense v2fn lần này còn trượt cả d02, nên tổng lại là 3/16.
- (b) **Đúng.** Grounded answer không đổi với bm25 và rerank, context dài hơn (bm25: 2173 → 2535 ký tự) và chi phí tăng khoảng 33%. Đổi lại, rerank v2fn từ chối đúng dn03 (3/3), nhưng chỉ dựa trên một lần chạy.
- **Filter trong đánh giá retrieval:** không đổi Hit@1/Hit@3 ở cả 3 phương pháp, vì dev chỉ có 2 câu có filter (`starter/results/retrieval/dev-filter`).

### Chọn cấu hình theo tiêu chí đã chốt (benchmark/README.md §4)

1. **Grounded mean:** bm25 v2, rerank v2, bm25 v2fn, rerank v2fn và rerank v1 cùng đạt 2.00.
2. **Ràng buộc** từ chối đúng ≥ 2/3 và từ chối nhầm ≤ 2/16: cả 5 đều đạt.
3. **Hòa:**
   - Context Evidence Rate: cả 5 cùng 16/16;
   - Evidence Hit@3 dev: cùng 16/16;
   - **Hit@1 dev:** bm25 15/16 > rerank 14/16, nên còn lại bm25 v2 và bm25 v2fn (Hit@1 bằng nhau, có filter hay không).
4. **Thời gian và chi phí:**
   - bm25 v2: $0.027 và 4.2 s;
   - bm25 v2fn: $0.036 và 3.7 s.

   Hai tiêu chí ngược chiều nhau. Chênh 0.5 s nằm trong nhiễu mạng (cùng cấu hình bm25 v1 đo được 3.5 s), còn chênh chi phí 33% thì ổn định. Thêm nữa, filter và tool đoạn lân cận không làm tăng chất lượng trên dev.

   **Đề xuất: chọn bm25 + prompt v2** (top-3, tối đa 4 lượt search, ngân sách 6000 ký tự, không filter, không lấy đoạn lân cận). Baseline để so trên test là **dense + prompt v1**.

**Giới hạn:**
- Dev nhỏ (16 + 3 câu). Khác biệt giữa bm25 và rerank chỉ dựa trên 1 câu Hit@1, và mỗi cấu hình chỉ chạy 1 lần.
- Benchmark nghiêng về tìm theo từ khóa: câu hỏi chia sẻ trung bình 61% unigram và bigram với chunk gold.

## Test: chạy một lần sau khi FROZEN (2026-11-16)

Nhãn test là **bản nháp, chờ học viên xác nhận** (`src/test_review_draft.py`). Không có câu nào bị lỗi, nên không phải chạy lại.

| Cấu hình | Hit@1 | Evidence Hit@3 | Context Evidence Rate | Context 0/1/2 | Grounded 0/1/2 (mean) | Citation hợp lệ | Từ chối đúng | Từ chối nhầm | invalid_citations | Lượt gọi model | Trung vị | Chi phí |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline: dense + v1 | 4/6 | 6/6 | 6/6 | 0/0/6 | 0/0/6 (2.00) | 6/6 | 3/3 | 0/6 | 4 | 26 | 4.0 s | $0.0150 |
| Chọn: bm25 + v2 | 6/6 | 6/6 | 6/6 | 0/0/6 | 0/0/6 (2.00) | 6/6 | 3/3 | 0/6 | 0 | 23 | 2.6 s | $0.0144 |

- Hit@1 và Hit@3 lấy từ `python -m src.evaluate_retrieval --split test --methods dense,bm25 --tag final`, chạy trên câu hỏi gốc.
- Context Evidence Rate và điểm context lấy từ context cuối mà agent gửi model.
- Đã đọc cả 6 câu có đáp án và 3 câu thiếu bằng chứng cho mỗi cấu hình.

**Nhận xét:**
- **Test không phân biệt được chất lượng câu trả lời.** Cả hai cấu hình đều đạt điểm tối đa. Đúng như rủi ro đã ghi trong benchmark/README.md: dense đạt Evidence Hit@3 6/6 trên test ngay từ Day 6, và các chủ đề test đều có từ khóa rõ.
- **Mức chênh 0.56 điểm grounded giữa dense và bm25 trên dev không lặp lại trên test.** Khác biệt còn lại nằm ở:
  - Hit@1: 4/6 so với 6/6;
  - lỗi citation sai định dạng: 4 so với 0, khớp với giả thuyết của prompt v2;
  - số lượt gọi model: 26 so với 23;
  - độ trễ: 4.0 s so với 2.6 s.
  - Chi phí gần bằng nhau.
- **Câu thiếu bằng chứng:** cả hai đều từ chối 3/3 mà không thêm khẳng định. Các câu test này không có tài liệu gần chủ đề nguy hiểm như tr.44 ở dn03.
- **Giới hạn:** test chỉ có 6 + 3 câu và mỗi cấu hình chạy 1 lần, nên kết quả không đủ để kết luận cấu hình chọn tốt hơn baseline về chất lượng câu trả lời. Kết luận chính vẫn dựa trên dev, có ghi rõ rủi ro chọn quá khớp với dev.
