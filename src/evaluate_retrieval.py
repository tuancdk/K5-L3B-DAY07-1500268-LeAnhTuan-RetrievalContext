"""Benchmark the retrieval methods on one split (definitions: benchmark/README.md §3).

    python -m src.evaluate_retrieval --split dev
    python -m src.evaluate_retrieval --split dev --methods bm25,hybrid --top-k 5 --tag k5

Per method: Hit@1, Evidence Hit@3, MRR@10, candidate Recall@N (hybrid/rerank),
Context Evidence Rate for the top-k packed into a char budget, latency and cost.
Gold is only read AFTER retrieval, to label results.
Outputs: starter/results/retrieval/<split>[-tag]/{summary.json,summary.md,traces.jsonl}
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .day6 import ROOT, load_env, normalize
from .retrieval import build_retrievers

RESULTS = ROOT / "starter" / "results" / "retrieval"
METHODS = ["dense", "bm25", "hybrid", "hybrid_rerank"]


def is_hit(chunk: dict, gold: list[dict]) -> bool:
    text = normalize(chunk["text"])
    return any(chunk["source_id"] == g["source_id"] and chunk["page"] == g["page"]
               and normalize(g["evidence"]) in text for g in gold)


def pack_context(results: list[dict], budget: int) -> tuple[list[dict], str]:
    """Greedy in rank order; a chunk that does not fit is skipped (same rule as starter)."""
    blocks, kept, used = [], [], 0
    for c in results:
        block = f"[{c['id']} | {c['source']} | trang {c['page']}]\n{c['text']}"
        extra = len(block) + (2 if blocks else 0)
        if used + extra <= budget:
            blocks.append(block)
            kept.append(c)
            used += extra
    return kept, "\n\n".join(blocks)


def run(args) -> None:
    load_env()
    questions = [q for q in json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
                 if q["split"] == args.split]
    methods = args.methods.split(",")
    retrievers = build_retrievers(index=args.index, candidates=args.candidates, rrf_k=args.rrf_k,
                                  bigrams=not args.no_bigrams, rerank_model=args.rerank_model)
    k = max(args.top_k, 3)
    traces, per_method = [], {m: [] for m in methods}
    for q in questions:
        filters = q.get("filter") if args.use_filter else None
        for m in methods:
            r = retrievers[m]
            t0 = time.perf_counter()
            err, results = None, []
            try:
                results = r.search(q["question"], filters=filters, top_k=k)
            except Exception as exc:  # report, never replace with fake results
                err = f"{type(exc).__name__}: {exc}"
            ms = (time.perf_counter() - t0) * 1000
            trace = {"query_id": q["id"], "split": q["split"], "answerable": q["answerable"],
                     "method": m, "question": q["question"], "filter": filters, "top_k": args.top_k,
                     "elapsed_ms": round(ms, 1), "error": err}
            if hasattr(r, "last_candidates") and m == "hybrid_rerank":
                trace["candidates"] = [{"id": c["id"], "page": c["page"], "rank": c["rank"]}
                                       for c in r.last_candidates]
            if q["answerable"] and not err:
                gold = q["gold"]
                marks = [is_hit(c, gold) for c in results]
                first = next((i for i, h in enumerate(marks, 1) if h), None)
                ctx, ctx_text = pack_context(results[:args.top_k], args.budget)
                cand = trace.get("candidates") or (
                    [{"id": i} for i in r.last_lists["dense"] + r.last_lists["bm25"]] if m == "hybrid" else None)
                cand_ids = {c["id"] for c in cand} if cand else None
                trace.update({
                    "hit1": bool(marks and marks[0]), "hit3": any(marks[:3]), "first_hit_rank": first,
                    "rr": 1 / first if first else 0.0,
                    "context_hit": any(is_hit(c, gold) for c in ctx),
                    "context_ids": [c["id"] for c in ctx], "context_chars": len(ctx_text),
                    "candidate_recall": (any(is_hit(c, gold) for c in results) or any(
                        is_hit(c, gold) for c in retrievers["hybrid"].bm25.chunks if c["id"] in cand_ids))
                    if cand_ids is not None else None,
                    "gold_pages": [g["page"] for g in gold]})
            trace["results"] = [{k2: c.get(k2) for k2 in ("id", "page", "rank", "score", "pre_rank", "source_ranks")
                                 if c.get(k2) is not None} | {"hit": is_hit(c, q["gold"]) if q["answerable"] else None}
                                for c in results]
            traces.append(trace)
            per_method[m].append(trace)
        print(f"{q['id']}: " + " ".join(
            f"{t['method']}={'E' if t['error'] else ('-' if not t['answerable'] else ('1' if t['hit1'] else ('3' if t['hit3'] else 'x')))}"
            for t in traces[-len(methods):]), flush=True)

    emb = retrievers["dense"].embedder.usage()
    rr = retrievers["hybrid_rerank"]
    summary = {}
    for m, ts in per_method.items():
        ans = [t for t in ts if t["answerable"] and not t["error"]]
        n = sum(t["answerable"] for t in ts)
        frac = lambda key: f"{sum(bool(t.get(key)) for t in ans)}/{n}"
        cr = [t for t in ans if t.get("candidate_recall") is not None]
        summary[m] = {
            "hit_at_1": frac("hit1"), "evidence_hit_at_3": frac("hit3"),
            "mrr_at_10": round(sum(t["rr"] for t in ans) / n, 3) if n else None,
            "context_evidence_rate": frac("context_hit"),
            "candidate_recall": f"{sum(t['candidate_recall'] for t in cr)}/{n}" if cr else "n/a",
            "mean_context_chars": round(statistics.mean(t["context_chars"] for t in ans), 1) if ans else None,
            "median_ms": round(statistics.median(t["elapsed_ms"] for t in ts), 1),
            "errors": sum(bool(t["error"]) for t in ts),
            "misses_at_3": [t["query_id"] for t in ans if not t["hit3"]],
        }
    if "hybrid_rerank" in summary:
        summary["hybrid_rerank"]["llm"] = {"model": rr.model, **rr.usage, "cost_usd": round(rr.cost_usd(), 5)}
    meta = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "split": args.split,
            "index": args.index, "top_k": args.top_k, "budget_chars": args.budget,
            "candidates": args.candidates, "rrf_k": args.rrf_k, "bm25_bigrams": not args.no_bigrams,
            "use_filter": args.use_filter, "questions": len(questions),
            "answerable": sum(q["answerable"] for q in questions), "embedding_usage": emb,
            "note": "latency of hybrid_rerank includes its hybrid first stage; dense/hybrid share a cached query embedding"}
    out = RESULTS / (args.split + (f"-{args.tag}" if args.tag else ""))
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "traces.jsonl").open("w", encoding="utf-8") as fh:
        for t in traces:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")
    rows = ["| Method | Hit@1 | Evidence Hit@3 | MRR@10 | Context Evidence Rate | Candidate recall | Median ms | Errors | Misses@3 |",
            "|---|---|---|---|---|---|---|---|---|"]
    for m in methods:
        s = summary[m]
        rows.append(f"| {m} | {s['hit_at_1']} | {s['evidence_hit_at_3']} | {s['mrr_at_10']} | {s['context_evidence_rate']} "
                    f"| {s['candidate_recall']} | {s['median_ms']} | {s['errors']} | {', '.join(s['misses_at_3']) or '-'} |")
    table = "\n".join(rows)
    (out / "summary.md").write_text(
        f"# Retrieval {args.split}{' ' + args.tag if args.tag else ''}\n\n{json.dumps(meta, ensure_ascii=False)}\n\n{table}\n",
        encoding="utf-8")
    print("\n" + table)
    print(f"\nembedding: {emb}")
    if "hybrid_rerank" in summary:
        print("rerank:", summary["hybrid_rerank"]["llm"])
    print(f"-> {out.relative_to(ROOT)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Benchmark retrieval methods")
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--methods", default=",".join(METHODS))
    p.add_argument("--index", default="B", choices=["A", "B"])
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--budget", type=int, default=4000, help="context budget in characters")
    p.add_argument("--candidates", type=int, default=20)
    p.add_argument("--rrf-k", type=int, default=60)
    p.add_argument("--no-bigrams", action="store_true")
    p.add_argument("--use-filter", action="store_true", help="apply user-provided `filter` of a question")
    p.add_argument("--rerank-model", default=None)
    p.add_argument("--tag", default="")
    args = p.parse_args()
    if args.split == "test" and not args.tag:
        print("Chú ý: chạy test — chỉ làm sau khi đã chốt cấu hình trên dev.")
    run(args)


if __name__ == "__main__":
    main()
