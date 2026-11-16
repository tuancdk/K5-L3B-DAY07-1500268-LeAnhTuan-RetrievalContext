"""Run the agent on the advanced benchmark and draft pass/fail labels.

    python -m src.advanced.run_agent --split dev --retriever bm25 --tag bm25-k5
    python -m src.advanced.run_agent --split dev --retriever bm25 --tag bm25-k5 --rerun-errors

Outputs starter/results/advanced/<split>-<tag>/: traces.json, grading_draft.json, summary.json.
The draft grade is an AID for the human reviewer (ADVANCED.md requires reading every test item):
  facts_ok    every `required` fact appears in the answer (normalized; number formats tolerant)
  cites_ok    for every evidence group, some cited chunk lies on one of its pages with a
              compatible kind (table->table, visual->any visual kind, text->text/table)
  draft_pass  answerable: answered and facts_ok and cites_ok; unanswerable: status == abstain
Gold/benchmark fields never enter the agent.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone

from ..agent import Agent
from ..day6 import load_env
from .extract import ROOT
from .index import build_retrievers

RESULTS = ROOT / "starter" / "results" / "advanced"
VISUAL = {"bar_chart", "line_chart", "pie_chart", "combo_chart", "diagram", "org_chart", "infographic", "map", "photo"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).casefold()
    s = s.replace(" ", " ").replace("–", "-")
    return re.sub(r"\s+", " ", s)


def fact_in(fact: str, answer: str) -> bool:
    a, f = norm(answer), norm(fact)
    if f in a:
        return True
    # numbers: tolerate missing % / spaces, e.g. "37,8" vs "37,8%"
    nums = re.findall(r"\d[\d.,]*", f)
    if nums and all(re.search(r"(?<![\d.,])" + re.escape(n) + r"(?![\d])", a) for n in nums) and not re.sub(r"[\d.,%\s]", "", f.replace("≤", "").replace("~", "")):
        return True
    return False


def kind_ok(ev_kind: str, chunk_kind: str) -> bool:
    if ev_kind in VISUAL:
        return chunk_kind in VISUAL
    if ev_kind == "table":
        return chunk_kind == "table"
    return chunk_kind in ("text", "table")


def draft_grade(q: dict, trace: dict, by_id: dict) -> dict:
    if trace["status"] == "error":
        return {"draft_pass": False, "reason": "system error"}
    if not q["answerable"]:
        return {"draft_pass": trace["status"] == "abstain", "reason": f"status={trace['status']}"}
    if trace["status"] != "answered":
        return {"draft_pass": False, "facts_ok": False, "cites_ok": False, "reason": "abstained on answerable"}
    missing = [f for f in q["required"] if not fact_in(f, trace["answer"])]
    cited = [by_id[c] for c in trace["citations"] if c in by_id]
    groups = []
    for grp in q["evidence"]:
        ok = any(any((c["page"] == e["page"] or e["page"] in c["metadata"].get("pages", []))
                     and kind_ok(e["kind"], c["metadata"]["kind"]) for c in cited) for e in grp)
        groups.append(ok)
    # clarified rule (after dev, before test): same page other region, or unlisted page, may be
    # accepted ONLY after the reviewer checks the original -> flagged here, never auto-accepted
    flags = []
    for gi, (grp, ok) in enumerate(zip(q["evidence"], groups)):
        if ok:
            continue
        pages = {e["page"] for e in grp}
        same_page = [c["id"] for c in cited if c["page"] in pages]
        other = [c["id"] for c in cited if c["page"] not in pages]
        if same_page:
            flags.append(f"group{gi}: same page, other region {same_page}")
        elif other:
            flags.append(f"group{gi}: unlisted page(s) {other}")
    return {"draft_pass": not missing and all(groups), "facts_ok": not missing, "missing_facts": missing,
            "review_flags": flags,
            "cites_ok": all(groups), "evidence_groups_cited": groups,
            "cited": [{"id": c["id"], "page": c["page"], "kind": c["metadata"]["kind"]} for c in cited]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--retriever", choices=["dense", "bm25", "hybrid", "hybrid_rerank"], default="bm25")
    p.add_argument("--model", default=None)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--max-searches", type=int, default=5)
    p.add_argument("--budget", type=int, default=12000)
    p.add_argument("--neighbors", action="store_true")
    p.add_argument("--prompt", choices=["ar", "ar2"], default="ar")
    p.add_argument("--verify", action="store_true", help="harness grounding self-check (numbers/units in cited chunks)")
    p.add_argument("--ids", default="")
    p.add_argument("--tag", required=True)
    p.add_argument("--rerun-errors", action="store_true")
    args = p.parse_args()
    load_env()
    bench = [q for q in json.loads((ROOT / "advanced" / "benchmark.json").read_text(encoding="utf-8"))
             if q["split"] == args.split and (not args.ids or q["id"] in args.ids.split(","))]
    retrievers, chunks = build_retrievers()
    retriever = retrievers[args.retriever]
    agent = Agent(retriever, chunks, model=args.model, top_k=args.top_k, max_searches=args.max_searches,
                  budget=args.budget, neighbors=args.neighbors, prompt=args.prompt, verify=args.verify)
    rerank = retrievers["hybrid_rerank"]
    out = RESULTS / f"{args.split}-{args.tag}"
    prior = {}
    if args.rerun_errors:
        prior = {t["query_id"]: t for t in json.loads((out / "traces.json").read_text(encoding="utf-8"))}
    t_warm = time.perf_counter()
    for _ in range(3):
        try:
            agent.client.models.retrieve(agent.model)
            break
        except Exception as exc:  # noqa: BLE001
            print("warm-up failed:", type(exc).__name__)
    warm = round(time.perf_counter() - t_warm, 1)
    traces, grades = [], []
    for q in bench:
        if prior and prior[q["id"]]["status"] != "error":
            t = prior[q["id"]]
        else:
            rr0 = dict(rerank.usage)
            try:
                r = agent.run(q["question"])
            except Exception as exc:  # record, never fake
                r = {"status": "error", "answer": "", "citations": [], "events": [], "searches": 0,
                     "context_ids": [], "context_chars": 0, "usage": {}, "elapsed_ms": None,
                     "error": f"{type(exc).__name__}: {exc}"}
            r["rerank_usage"] = {k: rerank.usage[k] - rr0[k] for k in rerank.usage}
            t = {"query_id": q["id"], "split": q["split"], "group": q["group"], "answerable": q["answerable"],
                 "question": q["question"], "config": args.tag, **r}
            if q["id"] in prior:
                t["previous_errors"] = prior[q["id"]].get("previous_errors", []) + [prior[q["id"]].get("error")]
        g = {"query_id": q["id"], "group": q["group"], **draft_grade(q, t, agent.by_id)}
        traces.append(t)
        grades.append(g)
        print(f"{q['id']:5} {q['group']:16} {t['status']:9} s={t['searches']} draft={'PASS' if g['draft_pass'] else 'fail'} "
              f"{(t.get('answer') or t.get('error', ''))[:100]!r}", flush=True)
    ok = [t for t in traces if t["status"] != "error"]
    cost_agent = sum(t["usage"].get("cost_usd", 0) for t in ok)
    cost_rr = sum((t.get("rerank_usage", {}).get("input_tokens", 0) * 0.40 +
                   t.get("rerank_usage", {}).get("output_tokens", 0) * 1.60) / 1e6 for t in ok)
    by_group = {}
    for g in grades:
        b = by_group.setdefault(g["group"], [0, 0])
        b[0] += g["draft_pass"]
        b[1] += 1
    summary = {"draft_pass": f"{sum(g['draft_pass'] for g in grades)}/{len(grades)}",
               "by_group": {k: f"{a}/{n}" for k, (a, n) in by_group.items()},
               "errors": [t["query_id"] for t in traces if t["status"] == "error"],
               "searches": dict(sorted(Counter(t["searches"] for t in ok).items())),
               "median_ms": round(statistics.median(t["elapsed_ms"] for t in ok), 1) if ok else None,
               "mean_context_chars": round(statistics.mean(t["context_chars"] for t in ok), 1) if ok else None,
               "cost_usd": {"agent": round(cost_agent, 4), "rerank": round(cost_rr, 4), "total": round(cost_agent + cost_rr, 4)}}
    meta = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "split": args.split, "tag": args.tag,
            "model": agent.model, "retriever": args.retriever, "top_k": args.top_k, "max_searches": args.max_searches,
            "budget_chars": args.budget, "neighbors": args.neighbors, "prompt": args.prompt, "verify": args.verify, "warmup_seconds": warm,
            "rerun_errors": [t["query_id"] for t in traces if t.get("previous_errors")]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "traces.json").write_text(json.dumps(traces, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "grading_draft.json").write_text(json.dumps(grades, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    print(f"-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
