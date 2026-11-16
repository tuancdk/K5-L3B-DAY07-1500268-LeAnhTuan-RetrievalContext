# Retrieval dev

{"run_at": "2026-11-16T02:50:48+00:00", "split": "dev", "index": "B", "top_k": 3, "budget_chars": 4000, "candidates": 20, "rrf_k": 60, "bm25_bigrams": true, "use_filter": false, "questions": 19, "answerable": 16, "embedding_usage": {"model": "text-embedding-3-small", "dimensions": 1536, "api_calls": 19, "total_tokens": 759, "estimated_cost_usd": 1.5e-05}, "note": "latency of hybrid_rerank includes its hybrid first stage; dense/hybrid share a cached query embedding"}

| Method | Hit@1 | Evidence Hit@3 | MRR@10 | Context Evidence Rate | Candidate recall | Median ms | Errors | Misses@3 |
|---|---|---|---|---|---|---|---|---|
| dense | 7/16 | 12/16 | 0.583 | 12/16 | n/a | 387.5 | 0 | d01, d02, d03, d08 |
| bm25 | 15/16 | 16/16 | 0.969 | 16/16 | n/a | 3.2 | 0 | - |
| hybrid | 12/16 | 14/16 | 0.802 | 14/16 | 16/16 | 54.2 | 0 | d01, d08 |
| hybrid_rerank | 14/16 | 16/16 | 0.938 | 16/16 | 16/16 | 2456.8 | 0 | - |
