# Retrieval dev bm25-unigram

{"run_at": "2026-11-16T02:51:25+00:00", "split": "dev", "index": "B", "top_k": 3, "budget_chars": 4000, "candidates": 20, "rrf_k": 60, "bm25_bigrams": false, "use_filter": false, "questions": 19, "answerable": 16, "embedding_usage": {"model": "text-embedding-3-small", "dimensions": 1536, "api_calls": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}, "note": "latency of hybrid_rerank includes its hybrid first stage; dense/hybrid share a cached query embedding"}

| Method | Hit@1 | Evidence Hit@3 | MRR@10 | Context Evidence Rate | Candidate recall | Median ms | Errors | Misses@3 |
|---|---|---|---|---|---|---|---|---|
| bm25 | 14/16 | 14/16 | 0.875 | 14/16 | n/a | 0.9 | 0 | d10, d15 |
