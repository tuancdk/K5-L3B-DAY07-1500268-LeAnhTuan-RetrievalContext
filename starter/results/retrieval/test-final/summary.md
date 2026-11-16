# Retrieval test final

{"run_at": "2026-11-16T04:41:07+00:00", "split": "test", "index": "B", "top_k": 3, "budget_chars": 4000, "candidates": 20, "rrf_k": 60, "bm25_bigrams": true, "use_filter": false, "questions": 9, "answerable": 6, "embedding_usage": {"model": "text-embedding-3-small", "dimensions": 1536, "api_calls": 9, "total_tokens": 365, "estimated_cost_usd": 7e-06}, "note": "latency of hybrid_rerank includes its hybrid first stage; dense/hybrid share a cached query embedding"}

| Method | Hit@1 | Evidence Hit@3 | MRR@10 | Context Evidence Rate | Candidate recall | Median ms | Errors | Misses@3 |
|---|---|---|---|---|---|---|---|---|
| dense | 4/6 | 6/6 | 0.833 | 6/6 | n/a | 276.3 | 0 | - |
| bm25 | 6/6 | 6/6 | 1.0 | 6/6 | n/a | 1.1 | 0 | - |
