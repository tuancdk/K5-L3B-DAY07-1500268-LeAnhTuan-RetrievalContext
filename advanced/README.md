# Thử thách nâng cao: Báo cáo thường niên 2025 của MB

## 1. Tài liệu

| Mục | Giá trị |
|---|---|
| Tài liệu | Báo cáo thường niên 2025, Ngân hàng TMCP Quân đội (MB), bản tiếng Việt |
| Nguồn | https://webcdn.mbbank.com.vn/public/media/786b2697-ad56-44c1-be57-496c7a0f2d34.pdf (truy cập 2026-11-16) |
| sha256 | `f96d9d44bca12a7ce91528a862d7642c7edd4def673174021687d6566b0c7dc2` (27.090.201 byte) |
| Phiên bản | PDF xuất từ Adobe InDesign 21.2, ngày tạo 2026-04-07 |
| Số trang | 186 trang PDF: trang 1 là bìa đơn, 185 trang còn lại là **trang đôi**, tổng cộng **371 trang in**. Trang PDF *i* ≥ 2 chứa trang in 2(*i*−1) bên trái và 2(*i*−1)+1 bên phải; quy tắc này khớp với mọi header có số trang. |
| Quyền sử dụng | Tài liệu công bố thông tin công khai của doanh nghiệp niêm yết. Không tìm thấy giấy phép tái phân phối, nên **không commit PDF**, chỉ ghi URL kèm sha256. Người chấm tải lại bản gốc và kiểm tra sha256. |

Bảy chương được xác định theo các trang mở đầu chương (trang PDF 7, 28, 50, 63, 69, 107, 139). Chương 7 là BCTC hợp nhất đã kiểm toán, chiếm 96 trang in.

## 2. Pipeline index (`src/advanced/`)

| Bước | Cách làm | Kết quả |
|---|---|---|
| Text | Lớp text của PDF (không cần OCR). Bỏ dải header 40pt và lề dưới; bỏ khối text nằm trong vùng bảng; gom đoạn thành chunk tối đa khoảng 1000 ký tự theo từng trang in | 798 chunk, 484 nghìn ký tự |
| Bảng | `find_tables()` của PyMuPDF trên **cả trang đôi**, để giữ được bảng vắt qua hai trang (ghi cả hai số trang, ví dụ "338, 339"). Hàng tiêu đề bị dồn vào một ô nên được **dựng lại** bằng cách gán từng chữ vào cột theo tọa độ x. Tiêu đề và đơn vị lấy từ dòng ngay phía trên bảng. Bảng dài được chia nhỏ, mỗi phần lặp lại tiêu đề | 315 bảng, 371 chunk |
| Hình | Mỗi trang in thuộc chương 0–6 (và các trang BCTC có ảnh) được render ở 130 dpi rồi gửi `gpt-4.1-mini` kèm lớp text của trang. Model trả về danh sách biểu đồ, sơ đồ, infographic và ảnh có thông tin, mỗi phần tử gồm loại, tiêu đề, bbox, mô tả và số liệu. Ảnh trang trí bị bỏ qua. Vùng cắt (bbox mở rộng 6%) được lưu để đối chiếu | 286 trang, 371 chunk hình: 147 infographic, 114 ảnh, 66 sơ đồ, 1 sơ đồ tổ chức, 1 bản đồ, 42 biểu đồ (13 cột, 23 kết hợp, 4 đường, 2 tròn) |
| Index | BM25 (âm tiết + bigram), dense (`text-embedding-3-small`, 1536 chiều, cosine exact bằng numpy), hybrid RRF và LLM rerank. Dùng lại mã của phần cơ bản | 1540 chunk |

Mỗi chunk lưu `page` (trang **in**), `pdf_page`, `chapter` và `kind` (text/table/loại hình). Chunk bảng và hình có thêm `bbox` (đơn vị pt, tính trên toàn trang PDF). Chunk hình có thêm `crop` và `extracted_by`. Nhờ đó citation xác định được trang và vùng evidence.

## 3. Kiểm tra nội dung trích xuất với bản gốc

- **Bảng:** đã đối chiếu tiêu đề dựng lại và các dòng đầu của 4 bảng với ảnh trang: tr.85 (tình hình tài chính so với kế hoạch), tr.96 (lịch sử tăng vốn), tr.97 (lịch sử cổ tức), tr.338–339 (thay đổi vốn chủ sở hữu, 12 cột). Tiêu đề cột và giá trị đúng. **Hạn chế:** ở bảng 12 cột tr.338–339 có một cột tiêu đề rỗng do ô gộp.
- **Hình, vòng 1** (`gpt-4.1-mini`, prompt v1): số liệu biểu đồ tr.91, 92, 118 và infographic tr.121 khớp ảnh gốc. Text thuần ghép sai cặp ROE/ROA ở tr.121, còn mô tả của model ghép đúng. Tuy vậy model **suy diễn** ý nghĩa nhãn phụ: tr.91 hiểu "+20%" là tăng trưởng 2024→2025, trong khi đoạn văn ghi 22%; tr.92 viết "vượt kế hoạch 10%".
- **Hình, vòng 2** (prompt v2): bổ sung quy tắc chép nguyên văn nhãn phụ kèm vị trí, không suy diễn giai đoạn, không trộn đoạn văn xung quanh. Chạy lại 27 trang có biểu đồ bằng `gpt-4.1` và `gpt-4.1-mini`.
- **Kiểm tra chéo tự động, không dùng model** (`src/advanced/chart_layout.py`): nhãn số của biểu đồ là text thật trong PDF. Với mỗi cặp năm–giá trị model đọc được, kiểm tra (a) con số có trong lớp text của trang, (b) con số nằm trong cột của đúng năm khi căn theo trục.

| Bản trích biểu đồ (27 trang) | Nhất quán | Sai cột | Số không có trong lớp text |
|---|---|---|---|
| gpt-4.1-mini, prompt v1 | 105 | 1 | 2 |
| gpt-4.1, prompt v2 | 150 | **14** (ví dụ tr.91 đảo 4,1/4,4) | 8 |
| **gpt-4.1-mini, prompt v2 (dùng cho index)** | 137 | 1* | 0 |

\* Trường hợp duy nhất (tr.89, "2023 – KHCN 45%") đã được đối chiếu với ảnh: **model đúng**, bộ căn cột sai vì nhãn đặt lệch sang phải cột. Bản `gpt-4.1` và bản prompt v1 được lưu riêng (`starter/data/advanced/vision_gpt41/`, `vision_mini_v1/`) để tham chiếu.

**Giới hạn của bước kiểm tra:**
- Mô tả sơ đồ, infographic và ảnh chỉ được kiểm tra theo mẫu (tr.16, 17, 119, 121).
- bbox do model ước lượng nên chỉ gần đúng; vùng cắt được mở rộng 6% để vẫn chứa phần tử.
- Câu benchmark nào dựa vào hình đều được chấm bằng cách đối chiếu ảnh gốc, không dựa vào mô tả của model.

## 4. Phần chưa xử lý

| Trang in | Lý do | Ảnh hưởng |
|---|---|---|
| 1, 3 | Bìa: khẩu hiệu "Tăng tốc – Vững chắc – Hiệu quả" dạng ảnh, không có lớp text; model coi là ảnh trang trí | Không có thông tin nghiệp vụ |
| 2, 371 | Trang trắng | Không có |
| Trang BCTC (chương 7) không có ảnh | Không chạy bước đọc ảnh, chỉ dùng text và bảng | Chương này không có biểu đồ |

Bảng không có đường kẻ (KPI trình bày dạng infographic) không được `find_tables()` nhận ra, nhưng đã được bước đọc ảnh bao phủ.

## 5. Chi phí và lệnh chạy

- **Chi phí:**
  - Đọc ảnh: vòng 1 khoảng $0.62 (286 trang); vòng 2 gồm `gpt-4.1` khoảng $0.26 và `gpt-4.1-mini` khoảng $0.07 (27 trang).
  - Embedding: 536 nghìn token, khoảng $0.011.
  - **Tổng index khoảng $0.97.**
- **Lệnh chạy** (cần `pymupdf>=1.26`):

```bash
curl -L -o starter/data/advanced/mb_ar_2025.pdf "<URL ở trên>"   # kiểm tra sha256
python -m src.advanced.extract                 # text + bảng
python -m src.advanced.vision --all            # đọc ảnh, có cache theo trang
python -m src.advanced.vision --pages <các trang có biểu đồ> --force   # prompt v2
python -m src.advanced.index build             # gộp + embedding
```

## 6. Benchmark (`advanced/benchmark.json`, sinh từ `src/advanced/make_benchmark.py`)

**Trạng thái: FROZEN 2026-11-16.** Học viên đã kiểm tra và xác nhận. Benchmark được chốt **trước mọi lần chạy retrieval hay agent** trên tài liệu này (cả dev lẫn test). sha256 của `advanced/benchmark.json` = `3679b0948382e72d5d21604ac1bb241a271a4b3863657e205c95593c6703d799`. Sau mốc này không sửa câu hỏi, đáp án hay evidence.

| Split | Bảng | Ảnh, sơ đồ | Biểu đồ | Multi-hop | Text | Thiếu bằng chứng | Tổng |
|---|---|---|---|---|---|---|---|
| dev | 4 | 3 | 4 | 3 | 3 | 4 | 21 (17 + 4) |
| test | 6 | 6 | 6 | 4 | 4 | 6 | **32** (26 + 6) |

Yêu cầu tối thiểu: dev 15 + 3; test 24 + 6, trong đó bảng ≥6, ảnh ≥5, biểu đồ ≥5, multi-hop ≥4, text ≥4. Test có dư 2 câu, và mọi câu đã công bố đều tính vào mẫu số.

- **Cách soạn:**
  - Mọi đáp án được đối chiếu với **ảnh trang gốc** (render từ PDF), không lấy từ mô tả của model.
  - Mỗi câu ghi trang in, trang PDF, loại vùng, vị trí (dòng/cột của bảng, cột/điểm của biểu đồ, ô của sơ đồ) và trích dẫn.
  - Câu multi-hop có từ 2 nhóm evidence trên các trang khác nhau, và phải cite đủ **mọi** nhóm. Trong một nhóm, các vị trí là evidence thay thế (ví dụ cùng số liệu xuất hiện ở tr.59 và tr.85).
- **Loại trừ có chủ đích:**
  - Tài liệu **tự mâu thuẫn** về số giờ đào tạo: tr.77 ghi 70,73 giờ, tăng 38%; tr.188 ghi 82,91 giờ, tăng 17%.
  - CAR có hai giá trị khác nhau (11,0% và 11,1%).
  - Sơ đồ tr.26 không cho thấy rõ 5 ủy ban trực thuộc HĐQT hay Tổng Giám đốc.
  - Tr.104–105 có số liệu tăng trưởng giá cổ phiếu bất thường.
  - Các câu này không được dùng để tránh đáp án không duy nhất.
- **Chia dev/test** trước khi chạy: dev và test dùng **các hình, bảng và đoạn văn khác nhau**. Chỉ một số trang có cả hai, nhưng hỏi về các ô khác nhau: tr.188 (dev hỏi độ tuổi, có thể lấy từ biểu đồ tr.77; test hỏi lương và số lao động), tr.21 và tr.97 (cùng dùng trong dev).
- **Câu thiếu bằng chứng:**
  - Đều gần chủ đề, mỗi câu kèm trang gần chủ đề.
  - Kiểm tra bằng từ khóa trên **toàn bộ lớp text 371 trang** (khớp ranh giới từ) và mô tả hình; `validate` báo lỗi nếu từ khóa xuất hiện.
  - Đã loại các ứng viên **có** đáp án: xếp hạng Moody's/Fitch (tr.66), LDR (tr.57, 86, 134), thù lao HĐQT.
  - Đã loại số người dùng app hoạt động hàng tháng (MAU), vì tài liệu có "35 triệu người dùng kênh số", dễ gây tranh cãi khi chấm.

### Cách chấm (chốt trước khi chạy, theo ADVANCED.md §3)

- **Câu có đáp án = đạt** khi thỏa cả ba điều kiện:
  1. Câu trả lời chứa **mọi** ý trong `required`, đúng con số, đơn vị và điều kiện (chấp nhận cách viết tương đương như 0,6 hay 0,6%; "(4%)" tương đương "giảm 4%").
  2. Citation trỏ tới chunk nằm trên trang evidence, đúng loại vùng (bảng, hình hay đoạn văn), cho **mỗi** nhóm evidence.
  3. Nội dung chunk được cite thực sự hỗ trợ toàn bộ câu trả lời.

  Đúng một phần, sai citation hoặc từ chối đều là **không đạt**. Thêm khẳng định sai ngoài các ý bắt buộc cũng là không đạt.
- **Câu thiếu bằng chứng = đạt** khi agent từ chối hoặc nói rõ không đủ bằng chứng, không đưa ra số liệu suy đoán.
- **Lỗi hệ thống, timeout hoặc không có kết quả** = không đạt, báo riêng và không loại khỏi mẫu số. Lỗi kết nối được phép chạy lại theo `--rerun-errors`, lỗi cũ vẫn ghi trong trace.
- **Tỷ lệ đạt** = số câu đạt / 32; cần **≥ 29/32** (90,6%) để đạt ngưỡng 90%, không làm tròn.
- **Chọn cấu hình trên dev:**
  - (1) tỷ lệ đạt dev trên 21 câu;
  - (2) nếu hòa, tỷ lệ đạt của câu biểu đồ + ảnh;
  - (3) số câu thiếu bằng chứng làm đúng;
  - (4) trung vị thời gian, rồi chi phí.

  Test chỉ chạy một lần với cấu hình đã chốt.

## 7. Thử nghiệm trên dev và chọn cấu hình (2026-11-16, trước khi chạy test)

Lệnh chạy: `python -m src.advanced.run_agent --split dev --retriever <r> --prompt <p> [--model gpt-4.1] [--verify] --tag <tag>`. Mọi cấu hình dùng top-5, tối đa 5 lượt search, ngân sách 12.000 ký tự. Nhãn trong bảng là nhãn **đọc tay** (`starter/results/advanced/dev-*/labels.json` cho A/B/C). Bộ chấm nháp tự động chỉ dùng để gợi ý.

| Lần | Agent | Retriever | Prompt / kiểm tra | Đạt (21) | Ghi chú |
|---|---|---|---|---|---|
| 1 | gpt-4.1-mini | bm25 | ar | ~19 (ước tính) | ad08 bịa đơn vị "nghìn tỷ"; ad13 chỉ 1 lượt search, sai năm |
| 2 | gpt-4.1-mini | bm25 / rerank | ar2 | kém hơn | từ chối nhầm ad01/ad03; bịa "nghỉ việc 5,3%" (adn2, rerank) |
| 3 | gpt-4.1 | bm25 | ar / ar2 | ~19 / ~19 | ar thiếu citation tr.21 (ad13); ar2 vẫn ghi "nghìn tỷ" ở ad08 |
| 4 | gpt-4.1-mini | bm25 | ar2 + kiểm tra | 12 (nháp) | dao động mạnh: từ chối 4 câu dễ, nên loại `gpt-4.1-mini` |
| — | **Sửa index**: mô tả biểu đồ tr.64 tự ghi "giá trị thể hiện bằng nghìn tỷ đồng" | | | | prompt đọc ảnh **v3** (không suy đoán đơn vị), chạy lại 29 trang biểu đồ/đơn vị nghi vấn; kiểm tra chéo số: 110 nhất quán, 0 lỗi mới |
| **A** | **gpt-4.1** | **bm25** | **ar2 + kiểm tra** | **20/21 (20/20 hợp lệ)** | trung vị 4,1 s; $0,45 |
| B | gpt-4.1 | hybrid_rerank | ar2 + kiểm tra | 20/21 (20/20) | trung vị 12,2 s; $0,60 |
| C | gpt-4.1 | bm25 | ar + kiểm tra | 19/21 (19/20) | ad13 thiếu citation năm niêm yết |

- **Prompt `ar2`:** không tự thêm đơn vị; câu nhiều vế phải search riêng từng vế.
- **Kiểm tra (`--verify`):** harness đối chiếu mọi con số và đơn vị trong câu trả lời với chunk được cite; số đứng sau "=" hoặc "≈" được miễn. Nếu vi phạm, agent được sửa đúng một lần. Kiểm tra này không bao giờ ép agent trả lời hay từ chối.
- **Lỗi nhãn adn1:** xem `benchmark_errata.json`. Câu này bị loại khỏi tiêu chí chọn. Mọi cấu hình đều trả lời bằng khoảng lãi suất ở tr.316, đúng với tài liệu.

**Làm rõ quy tắc chấm** (quyết định sau khi chấm dev, **trước** khi chạy test, áp dụng cho test):
1. Citation tới vùng khác trên **cùng trang** evidence được chấp nhận nếu chính vùng đó chứa đúng giá trị cần (ví dụ bảng KPI dạng hình hay đoạn văn nêu lại số của biểu đồ).
2. Citation tới **trang không có trong danh sách** chỉ được chấp nhận khi người chấm đối chiếu bản gốc và thấy trang đó chứa đúng thông tin; ghi rõ trong nhãn.
3. Câu hỏi "tăng bao nhiêu" chấp nhận mức tăng tuyệt đối hoặc phần trăm, miễn đúng với nguồn. Cách viết tương đương được chấp nhận ("thứ nhất" = "thứ 1", "25%" = "25,0%").
4. Mọi khẳng định thêm mà sai (ví dụ đơn vị sai) đều làm câu **không đạt**.

**Cấu hình chọn theo tiêu chí §6:**
- (1) A và B hòa 20/20 câu hợp lệ;
- (2) cùng 7/7 câu biểu đồ và ảnh;
- (3) cùng làm đúng 3/3 câu thiếu bằng chứng hợp lệ;
- (4) A có trung vị nhanh hơn khoảng 3 lần và rẻ hơn.

**Chốt cấu hình A:** `gpt-4.1` + BM25 (âm tiết + bigram) + top-5 + tối đa 5 lượt search + 12.000 ký tự + prompt `ar2` + `--verify`. Test chỉ chạy **một lần** với cấu hình này.

**Giới hạn:**
- Kết quả dev dao động giữa các lần chạy, đặc biệt với `gpt-4.1-mini`.
- Dev chỉ có 20 câu hợp lệ, nên 20/20 không bảo đảm đạt 29/32 trên test.
- Mô tả hình đã được sửa một lần sau khi thấy lỗi trên dev; đây là thay đổi pipeline áp dụng cho toàn bộ tài liệu, không phải thay đổi theo câu test.

## 8. Kết quả test (chạy một lần, 2026-11-16)

- **Lệnh:** `python -m src.advanced.run_agent --split test --retriever bm25 --prompt ar2 --model gpt-4.1 --verify --tag A-final`
- **Lỗi hệ thống:** 0, không phải chạy lại câu nào.
- **Trace:** `starter/results/advanced/test-A-final/traces.json`.
- **Nhãn từng câu kèm lý do:** `labels.json`.
- **Cách chấm:** mọi câu được chấm tay bằng cách đọc câu trả lời, nội dung chunk được cite và bbox. Đáp án chuẩn đã được kiểm tra trên ảnh trang gốc khi soạn.

| Nhóm test | Đạt / tổng | Tỷ lệ | Lỗi / nhận xét |
|---|---|---|---|
| Bảng | 6/6 | 100% | at02 cite mô tả hình của cùng bảng (bbox phủ 100% vùng bảng) |
| Ảnh, sơ đồ | 6/6 | 100% | |
| Biểu đồ | 5/6 | 83,3% | **at15**: đảo nhãn CIR hợp nhất/riêng lẻ (26,0 và 29,1) |
| Multi-hop | 4/4 | 100% | at20 đạt nhờ làm rõ (2), xem bên dưới |
| Text | 3/4 | 75% | **at24**: bỏ đơn vị và ghi sai "(không ghi đơn vị)" cho "88.868 tỷ", do tác dụng phụ của bộ tự kiểm tra |
| Thiếu bằng chứng | 6/6 | 100% | Từ chối đúng, không suy đoán |
| **Toàn bộ** | **30/32** | **93,75%** | Ngưỡng ≥ 90% (≥ 29/32): **đạt** |

**Thời gian và chi phí:** trung vị 5,1 s/câu; số lượt search mỗi câu từ 1 đến 5; chi phí agent $0,94. Toàn bộ chi phí phần nâng cao (index, thử nghiệm dev, test) khoảng $5,0.

**Độ nhạy theo cách chấm:**
- **at20:** câu trả lời đúng, nhưng vế "vốn điều lệ cuối 2024 → cuối 2025" cite bảng tr.96 (trang này tự chứa 53.063.241 → 80.550.000) thay vì tr.85/57 trong danh sách. Nếu chỉ chấp nhận trang có trong danh sách: **29/32 = 90,6%**, vẫn đạt.
- **at02, at20, at22:** cite chunk *hình* thay vì chunk *bảng*, nhưng bbox của chunk hình phủ 100% vùng bảng, tức cùng vùng vật lý trên trang. Nếu không chấp nhận khác "loại chunk": 27/32 = 84,4%, **không đạt**. Kết quả vì vậy phụ thuộc vào làm rõ (1); làm rõ này đã được học viên chấp thuận trước khi chạy test.

**Lỗi và giới hạn:**
- **at15 (đảo nhãn):** lỗi đọc chú giải biểu đồ mà bộ tự kiểm tra không bắt được, vì cả hai con số đều có trong nguồn.
- **at24:** bộ tự kiểm tra so khớp chuỗi đơn vị cứng ("tỷ đồng" ≠ "tỷ") nên gợi ý sai cho agent. Cách sửa đúng là chuẩn hóa đơn vị trước khi so; mình **không sửa sau khi đã thấy test**.
- Kết quả là **một lần chạy**; trên dev, kết quả dao động giữa các lần chạy.
- Benchmark do AI soạn và đã được đối chiếu với bản gốc; có một câu dev bị gán nhãn sai (`benchmark_errata.json`).
- Một số câu multi-hop (at20) thực ra trả lời được chỉ từ một bảng.
- Nhãn do AI đề xuất, học viên xác nhận, chưa có người chấm thứ hai.
