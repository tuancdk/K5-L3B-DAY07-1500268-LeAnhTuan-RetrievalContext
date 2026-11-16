# Code

## Kết nối dữ liệu Day 6 (`src/day6.py`)

Day 7 dùng lại nguyên corpus, embedding và vector store Day 6, không ingest hay embed lại:

| Thành phần | Giá trị |
|---|---|
| Corpus | `mbb-bctc-hn-q3-2026`: BCTC hợp nhất Q3/2026 của MB, 59 trang nội dung (scan, đã OCR) |
| Embedding | OpenAI `text-embedding-3-small`, 1536 chiều, query và document dùng cùng model, không có prefix |
| Vector store | PostgreSQL 16 + pgvector 0.8.7, bảng `chunks`, cosine exact scan (không ANN) |
| Index dùng mặc định | `B`: chia theo đoạn, tối đa 1000 ký tự, 194 chunk (index `A`: cố định 500/50, 297 chunk) |

```bash
pip install -r requirements.txt
cp .env.example .env               # điền OPENAI_API_KEY
docker compose -p day7_retrieval up -d --wait   # mount volume Day 6 `day6_student_starter_pg_data`
python -m src.day6 check           # kiểm tra DB, số chiều, chạy 1 query thật
python -m src.day6 export          # -> starter/data/day6/{chunks,questions,manifest}.json
```

- Docker map cổng host **15433**, không dùng 55433 của Day 6: sau khi khởi động lại máy, Windows/Hyper-V có thể giữ dải 55330–55729. Mỗi lúc chỉ chạy một container trên volume này.
- `export` đổi benchmark Day 6 sang schema Day 7: mỗi trang trong `gold_pages` thành một phần tử `gold`. Với 15/22 câu, evidence chỉ khớp sau khi chuẩn hóa khoảng trắng (đúng định nghĩa hit của Day 6). Khi đó evidence được thay bằng chuỗi nguyên văn trong chunk để hàm `hit()` của starter, vốn so khớp nguyên văn, cho cùng kết quả. Danh sách nằm ở `manifest.json → conversion_notes`.
- Kiểm tra tái lập: dense trên index B, dev, top-3 cho Hit@1 **7/16**, Evidence Hit@3 **12/16**, trùng `metrics_dev.md` Day 6.
