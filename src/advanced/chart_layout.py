"""Deterministic chart label extraction from the PDF text layer (no model).

Charts in this report are vector graphics whose value labels are real PDF text. For every
x-axis row of period labels (e.g. "2023 2024 2025" or "2022 ... Kế hoạch 2026") we assign
each numeric label above the axis to the column whose label is horizontally closest, and list
them top-to-bottom. This cross-checks the vision model, which sometimes swaps label/value
pairs (seen on p.91 with gpt-4.1).
"""
from __future__ import annotations

import re

import pymupdf

from .extract import norm

YEAR = re.compile(r"^(19|20)\d{2}$")
NUM = re.compile(r"^[+\-~≥≤]?\d[\d.,]*%?$")


def axis_rows(words):
    """Rows (same baseline) holding >= 3 year tokens with increasing x."""
    rows = {}
    for w in words:
        if YEAR.match(w[4]):
            rows.setdefault(round(w[3] / 3), []).append(w)
    out = []
    for ws in rows.values():
        ws = sorted(ws, key=lambda w: w[0])
        if len(ws) >= 3:
            out.append(ws)
    return out


def chart_labels(page: pymupdf.Page, clip: pymupdf.Rect, max_height: float = 330) -> list[str]:
    words = [(x0, y0, x1, y1, norm(t)) for x0, y0, x1, y1, t, *_ in page.get_text("words", clip=clip)]
    lines = []
    for axis in axis_rows(words):
        y_axis = min(w[1] for w in axis)
        xs = [((w[0] + w[2]) / 2) for w in axis]
        gap = min(b - a for a, b in zip(xs, xs[1:])) if len(xs) > 1 else 50
        labels = []
        for w in axis:  # "Kế hoạch 2026": keep a preceding word on the same line close to the year
            prev = [v for v in words if abs(v[3] - w[3]) < 2 and 0 < w[0] - v[2] < 6 and not YEAR.match(v[4])]
            labels.append((" ".join(v[4] for v in prev) + " " + w[4]).strip())
        cols = {lab: [] for lab in labels}
        for w in words:
            if not NUM.match(w[4]) or YEAR.match(w[4]) or not (y_axis - max_height < w[3] <= y_axis):
                continue
            # chart value labels stand alone; numbers inside prose share their line with letters
            neighbours = [v for v in words if abs(v[3] - w[3]) < 2 and v is not w and abs(v[0] - w[0]) < 120]
            if any(re.search(r"[^\W\d_]{2,}", v[4]) for v in neighbours):
                continue
            xc = (w[0] + w[2]) / 2
            k = min(range(len(xs)), key=lambda j: abs(xs[j] - xc))
            if abs(xs[k] - xc) <= gap / 2:
                cols[labels[k]].append((w[1], w[4]))
        if sum(len(v) for v in cols.values()) >= len(labels):
            lines.append(" | ".join(f"{lab}: " + ", ".join(t for _, t in sorted(v)) for lab, v in cols.items()))
    return lines


if __name__ == "__main__":
    import sys
    from .extract import PDF, halves
    sys.stdout.reconfigure(encoding="utf-8")
    doc = pymupdf.open(PDF)
    for pp in map(int, sys.argv[1].split(",")):
        i = pp // 2 + 1
        for side, p, clip in halves(doc[i - 1], i):
            if p == pp:
                print(pp, chart_labels(doc[i - 1], clip))
