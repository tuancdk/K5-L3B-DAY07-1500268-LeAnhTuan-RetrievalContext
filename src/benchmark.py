"""Build and validate the Day 7 benchmark (see benchmark/README.md).

    python -m src.benchmark build      # Day 6 answerable + benchmark/unanswerable.json
    python -m src.benchmark validate   # counts, evidence-in-chunk, absence checks

Outputs:
  benchmark/questions.json        canonical Day 7 benchmark (Day 6 evidence kept verbatim)
  benchmark/cases.json            id/split/answerable for starter/agent_metrics.py
  starter/data/day6/questions.json answerable only, evidence = exact chunk substring so the
                                  starter's verbatim `hit()` agrees with the normalized hit.

No retrieval is run here; gold never leaves these files.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from .day6 import ROOT, day6_dir, normalize, _exact_span

BENCH = ROOT / "benchmark"
CHUNKS = ROOT / "starter" / "data" / "day6" / "chunks.json"
MIN_COUNTS = {("dev", True): 15, ("dev", False): 2, ("test", True): 5, ("test", False): 2}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def ocr_pages() -> dict[int, str]:
    """Full OCR text of every PDF page (incl. the 2 excluded cover-letter pages)."""
    pattern = str(day6_dir() / "starter" / "data" / "ocr" / "mbb_q3_2026" / "page_*.json")
    pages = {}
    for f in sorted(glob.glob(pattern)):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        pages[d["page"]] = unicodedata.normalize("NFC", d["text"])
    if not pages:
        raise SystemExit(f"không tìm thấy OCR: {pattern}")
    return pages


def term_hits(term: str, pages: dict[int, str]) -> list[int]:
    rx = re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, term.split())) + r"(?!\w)", re.IGNORECASE)
    return [p for p, t in pages.items() if rx.search(t)]


def build(_args) -> None:
    d6 = _read(day6_dir() / "benchmark" / "questions.json")
    questions = []
    for q in d6["questions"]:
        item = {"id": q["id"], "split": q["split"], "type": q["type"], "question": q["question"],
                "answerable": True, "expected_answer": q["expected_answer"],
                "gold": [{"source_id": q["gold_source_id"], "page": p, "evidence": q["evidence_quote"]}
                         for p in q["gold_pages"]],
                "gold_mode": "any"}  # gold entries are alternatives; one is enough
        if q.get("filter"):
            item["filter"] = q["filter"]
        questions.append(item)
    for q in _read(BENCH / "unanswerable.json"):
        questions.append({**q, "type": "thieu_bang_chung"})
    questions.sort(key=lambda q: (q["split"] != "dev", q["id"]))
    _write(BENCH / "questions.json", questions)
    _write(BENCH / "cases.json", [{"id": q["id"], "split": q["split"], "answerable": q["answerable"]}
                                  for q in questions])
    # starter-compatible copy: answerable only, exact chunk substring as evidence
    chunks = _read(CHUNKS)
    starter = []
    for q in questions:
        if not q["answerable"]:
            continue
        gold = []
        for g in q["gold"]:
            on_page = [c for c in chunks if c["source_id"] == g["source_id"] and c["page"] == g["page"]]
            span = _exact_span(g["evidence"], on_page)
            if span:
                gold.append({**g, "evidence": span})
        starter.append({k: q[k] for k in ("id", "split", "question", "expected_answer")} |
                       {"gold": gold} | ({"filter": q["filter"]} if "filter" in q else {}))
    _write(CHUNKS.parent / "questions.json", starter)
    print(f"built {len(questions)} questions -> benchmark/questions.json, cases.json, "
          f"{CHUNKS.parent.relative_to(ROOT)}/questions.json")
    validate(_args)


def validate(_args) -> None:
    questions = _read(BENCH / "questions.json")
    chunks = _read(CHUNKS)
    pages = ocr_pages()
    errors, report = [], []

    ids = [q["id"] for q in questions]
    if len(ids) != len(set(ids)):
        errors.append("ID trùng")
    counts = Counter((q["split"], q["answerable"]) for q in questions)
    for key, minimum in MIN_COUNTS.items():
        if counts[key] < minimum:
            errors.append(f"{key}: {counts[key]} < {minimum}")
    norm_q = Counter(normalize(q["question"]) for q in questions)
    errors += [f"câu hỏi trùng: {t}" for t, n in norm_q.items() if n > 1]

    for q in questions:
        if q["answerable"]:
            ok = [g for g in q["gold"] if any(
                c["source_id"] == g["source_id"] and c["page"] == g["page"]
                and normalize(g["evidence"]) in normalize(c["text"]) for c in chunks)]
            if not ok:
                errors.append(f"{q['id']}: evidence không nằm trọn trong chunk nào của index")
            elif len(ok) < len(q["gold"]):
                report.append(f"{q['id']}: chỉ {len(ok)}/{len(q['gold'])} gold nằm trọn trong chunk")
        else:
            for k in ("absence_reason", "expected_behavior", "absent_terms"):
                if not q.get(k):
                    errors.append(f"{q['id']}: thiếu {k}")
            found = {t: term_hits(t, pages) for t in q.get("absent_terms", [])}
            bad = {t: p for t, p in found.items() if p}
            if bad:
                errors.append(f"{q['id']}: thuật ngữ 'vắng mặt' lại xuất hiện trong OCR: {bad}")
            report.append(f"{q['id']} ({q['split']}): " + ", ".join(f"{t!r} {len(p)}/{len(pages)} trang" for t, p in found.items()))

    print("counts:", {f"{s}/{'có đáp án' if a else 'thiếu evidence'}": n for (s, a), n in sorted(counts.items())})
    print("\n".join(report))
    if errors:
        print("LỖI:\n  " + "\n  ".join(errors))
        raise SystemExit(1)
    print("OK: benchmark hợp lệ")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Benchmark Day 7")
    parser.add_argument("cmd", choices=["build", "validate"])
    args = parser.parse_args()
    {"build": build, "validate": validate}[args.cmd](args)


if __name__ == "__main__":
    main()
