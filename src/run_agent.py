"""Run the agent on a benchmark split and save traces + automatic metrics.

    python -m src.run_agent --split dev --retriever dense --tag dense
    python -m src.run_agent --split dev --retriever hybrid_rerank --neighbors --tag rerank-nb

Outputs (starter/results/agent/<split>-<tag>/):
  traces.json         per question: query_id, status, answer, citations, events, context, usage
                      (compatible with starter/agent_metrics.py)
  summary.json/.md    automatic metrics only: tool use, #searches, Context Evidence Rate,
                      citations-in-context, status counts, latency, tokens, cost
  review.json         one row per question for MANUAL grading (answer_grade, citation_support,
                      abstention_correct are null until a human fills them)
Gold is used only after the agent has answered, to label context evidence.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone

from .agent import Agent
from .day6 import ROOT, load_env
from .evaluate_retrieval import is_hit
from .retrieval import build_retrievers

RESULTS = ROOT / "starter" / "results" / "agent"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Chạy agent trên benchmark")
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--retriever", choices=["dense", "bm25", "hybrid", "hybrid_rerank"], default="dense")
    p.add_argument("--model", default=None)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--max-searches", type=int, default=4)
    p.add_argument("--budget", type=int, default=6000, help="tổng ký tự chunk đưa cho model")
    p.add_argument("--neighbors", action="store_true")
    p.add_argument("--prompt", choices=["v1", "v2"], default="v1")
    p.add_argument("--use-filter", action="store_true")
    p.add_argument("--no-bigrams", action="store_true")
    p.add_argument("--ids", default="", help="chỉ chạy các query id này (debug)")
    p.add_argument("--tag", required=True)
    p.add_argument("--rerun-errors", action="store_true",
                   help="chỉ chạy lại các câu status=error trong traces.json hiện có, giữ lại lỗi cũ")
    args = p.parse_args()

    load_env()
    questions = [q for q in json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
                 if q["split"] == args.split and (not args.ids or q["id"] in args.ids.split(","))]
    retrievers = build_retrievers(bigrams=not args.no_bigrams)
    retriever = retrievers[args.retriever]
    chunks = retrievers["bm25"].chunks
    agent = Agent(retriever, chunks, model=args.model, top_k=args.top_k, max_searches=args.max_searches,
                  budget=args.budget, neighbors=args.neighbors, use_filter=args.use_filter, prompt=args.prompt)
    rerank = retrievers["hybrid_rerank"]
    emb = retrievers["dense"].embedder

    out = RESULTS / f"{args.split}-{args.tag}"
    prior: dict[str, dict] = {}
    if args.rerun_errors:
        prior = {t["query_id"]: t for t in json.loads((out / "traces.json").read_text(encoding="utf-8"))}
    # Warm-up: on this machine the first TLS connection to the API takes ~25 s and can fail
    # (APIConnectionError). Open the connection once, outside the measured per-question latency.
    t_warm = time.perf_counter()
    for attempt in range(3):
        try:
            agent.client.models.retrieve(agent.model)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"warm-up attempt {attempt + 1} failed: {type(exc).__name__}")
    warmup_seconds = round(time.perf_counter() - t_warm, 1)
    traces, t_start = [], time.perf_counter()
    for q in questions:
        if prior and prior[q["id"]]["status"] != "error":
            traces.append(prior[q["id"]])
            continue
        rr_before = dict(rerank.usage)
        try:
            r = agent.run(q["question"], q.get("filter"))
        except Exception as exc:  # provider / store error: record, never fake
            r = {"status": "error", "answer": "", "citations": [], "events": [],
                 "error": f"{type(exc).__name__}: {exc}", "context_ids": [], "context_chars": 0,
                 "searches": 0, "usage": {}, "elapsed_ms": None}
        if args.retriever == "hybrid_rerank":
            r["rerank_usage"] = {k: rerank.usage[k] - rr_before[k] for k in rerank.usage}
        trace = {"query_id": q["id"], "split": q["split"], "answerable": q["answerable"],
                 "question": q["question"], "config": args.tag, **r}
        if q["id"] in prior:  # keep the transient error on record
            trace["previous_errors"] = prior[q["id"]].get("previous_errors", []) + [prior[q["id"]].get("error")]
        if q["answerable"] and r["status"] != "error":
            ctx = [agent.by_id[i] for i in r["context_ids"]]
            trace["context_evidence"] = any(is_hit(c, q["gold"]) for c in ctx)
            trace["cited_evidence"] = any(is_hit(agent.by_id[i], q["gold"]) for i in r["citations"])
        traces.append(trace)
        print(f"{q['id']:5} {r['status']:9} searches={r['searches']} ctx={'Y' if trace.get('context_evidence') else ('-' if not q['answerable'] else 'N')} "
              f"{(r.get('answer') or r.get('error', ''))[:110]!r}", flush=True)

    ok = [t for t in traces if t["status"] != "error"]
    ans = [t for t in ok if t["answerable"]]
    una = [t for t in ok if not t["answerable"]]
    n_ans = sum(t["answerable"] for t in traces)
    cites = [(t, c) for t in ok for c in t["citations"]]
    agent_cost = sum(t["usage"].get("cost_usd", 0) for t in ok)
    rerank_cost = (sum(t.get("rerank_usage", {}).get("input_tokens", 0) for t in ok) * 0.40 +
                   sum(t.get("rerank_usage", {}).get("output_tokens", 0) for t in ok) * 1.60) / 1e6
    summary = {
        "tool_use": f"{sum(t['searches'] > 0 for t in ok)}/{len(ok)}",
        "searches_distribution": dict(sorted(Counter(t["searches"] for t in ok).items())),
        "context_evidence_rate": f"{sum(t['context_evidence'] for t in ans)}/{n_ans}",
        "cited_gold_evidence": f"{sum(t['cited_evidence'] for t in ans)}/{n_ans}",
        "citations_in_context": f"{sum(c in t['context_ids'] for t, c in cites)}/{len(cites)}",
        "answered_with_citation": f"{sum(bool(t['citations']) for t in ok if t['status'] == 'answered')}/"
                                  f"{sum(t['status'] == 'answered' for t in ok)}",
        "abstain_on_unanswerable": f"{sum(t['status'] == 'abstain' for t in una)}/{sum(not t['answerable'] for t in traces)}",
        "abstain_on_answerable": f"{sum(t['status'] == 'abstain' for t in ans)}/{n_ans}",
        "invalid_citation_events": sum(e["event"] == "invalid_citations" for t in ok for e in t["events"]),
        "errors": [t["query_id"] for t in traces if t["status"] == "error"],
        "median_ms": round(statistics.median(t["elapsed_ms"] for t in ok), 1) if ok else None,
        "mean_context_chars": round(statistics.mean(t["context_chars"] for t in ok), 1) if ok else None,
        "tokens": {"agent_input": sum(t["usage"].get("input_tokens", 0) for t in ok),
                   "agent_output": sum(t["usage"].get("output_tokens", 0) for t in ok),
                   "embedding": emb.total_tokens},
        "cost_usd": {"agent": round(agent_cost, 5), "rerank": round(rerank_cost, 5),
                     "embedding": round(emb.total_tokens * 0.02 / 1e6, 6),
                     "total": round(agent_cost + rerank_cost + emb.total_tokens * 0.02 / 1e6, 5)},
        "note": "Grounded answer, citation support và abstention đúng cần chấm tay trong review.json.",
    }
    meta = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "split": args.split,
            "tag": args.tag, "model": agent.model, "retriever": args.retriever, "index": "B",
            "top_k": args.top_k, "max_searches": args.max_searches, "budget_chars": args.budget,
            "prompt": args.prompt, "neighbors": args.neighbors, "use_filter": args.use_filter, "bm25_bigrams": not args.no_bigrams,
            "questions": len(questions), "wall_seconds": round(time.perf_counter() - t_start, 1)}

    meta["warmup_seconds"] = warmup_seconds
    meta["rerun_errors"] =[t["query_id"] for t in traces if t.get("previous_errors")]
    out.mkdir(parents=True, exist_ok=True)
    (out / "traces.json").write_text(json.dumps(traces, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    review = []
    for t, q in zip(traces, questions):
        review.append({"query_id": t["query_id"], "answerable": q["answerable"], "question": q["question"],
                       "expected": q.get("expected_answer") or q.get("absence_reason"),
                       "status": t["status"], "answer": t["answer"],
                       "cited": [{"id": c, "page": agent.by_id[c]["page"], "text": agent.by_id[c]["text"]}
                                 for c in t["citations"] if c in agent.by_id],
                       "answer_grade": None if q["answerable"] else None,
                       "citation_support": [None] * len(t["citations"]),
                       "abstention_correct": None, "reason": ""})
    (out / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + json.dumps({"meta": meta, "summary": summary}, ensure_ascii=False, indent=1))
    print(f"-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
