"""Text + table extraction for the MB Annual Report 2025 (advanced challenge).

The PDF (186 pages) is exported from InDesign as two-page spreads: PDF page i (i >= 2) holds
printed pages 2(i-1) (left) and 2(i-1)+1 (right); this matches every running header that has
a page number. Page 1 is the single cover. Chapters are taken from the 7 chapter divider pages.

Outputs (starter/data/advanced/, gitignored):
  units.json        one record per printed page: pdf_page, side, printed_page, chapter, chars
  chunks_text.json  text chunks (paragraph packing, max ~1000 chars), tables removed
  chunks_table.json one chunk per detected table (rebuilt header + rows), split if long

    python -m src.advanced.extract
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "starter" / "data" / "advanced"
PDF = DATA / "mb_ar_2025.pdf"
SOURCE_ID = "mb-ar-2025"
SOURCE_URL = "https://webcdn.mbbank.com.vn/public/media/786b2697-ad56-44c1-be57-496c7a0f2d34.pdf"
HEADER_H, FOOTER_H = 40, 20  # points; running header band / bottom margin
# chapter divider PDF pages -> chapter title (from the divider pages themselves)
CHAPTERS = [
    (1, "0", "Bìa, mục lục, thông điệp"),
    (7, "1", "Tổng quan về MB năm 2025"),
    (28, "2", "Tình hình hoạt động của MB năm 2025"),
    (50, "3", "Báo cáo và đánh giá của Ban Điều hành"),
    (63, "4", "Đánh giá của HĐQT về hoạt động của Ngân hàng"),
    (69, "5", "Báo cáo phát triển bền vững"),
    (107, "6", "Quản trị Công ty"),
    (139, "7", "Báo cáo tài chính hợp nhất đã kiểm toán"),
]
MAX_CHUNK = 1000
MAX_TABLE = 1800


def norm(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def chapter_of(pdf_page: int) -> tuple[str, str]:
    cur = CHAPTERS[0]
    for start, num, title in CHAPTERS:
        if pdf_page >= start:
            cur = (start, num, title)
    return cur[1], cur[2]


def halves(page: pymupdf.Page, pdf_page: int):
    W, H = page.rect.width, page.rect.height
    if W < 900:
        yield "S", 1, pymupdf.Rect(0, 0, W, H)
        return
    yield "L", 2 * (pdf_page - 1), pymupdf.Rect(0, 0, W / 2, H)
    yield "R", 2 * (pdf_page - 1) + 1, pymupdf.Rect(W / 2, 0, W, H)


def rebuild_header(page: pymupdf.Page, table) -> list[str]:
    """Assign words of the header row to columns by x-centre (find_tables merges them)."""
    rows = [r for r in table.rows if r.bbox]
    if len(rows) < 2:
        return []
    cols = []
    for r in rows[1:]:
        cells = [c for c in r.cells]
        if sum(c is not None for c in cells) == len(cells):
            cols = [(c[0], c[2]) for c in cells]
            break
    if not cols:
        return []
    hb = pymupdf.Rect(rows[0].bbox)
    words = page.get_text("words", clip=hb)
    out = [[] for _ in cols]
    for x0, y0, x1, y1, w, *_ in sorted(words, key=lambda w: (round(w[1]), w[0])):
        xc = (x0 + x1) / 2
        k = min(range(len(cols)), key=lambda j: 0 if cols[j][0] <= xc <= cols[j][1]
                else min(abs(xc - cols[j][0]), abs(xc - cols[j][1])))
        out[k].append(norm(w))
    return [" ".join(ws) for ws in out]


def table_title(page: pymupdf.Page, bbox: pymupdf.Rect) -> str:
    """Nearest text line(s) just above the table, plus a unit line if present."""
    above = pymupdf.Rect(bbox.x0, max(HEADER_H, bbox.y0 - 60), bbox.x1, bbox.y0)
    t = re.sub(r"\s+", " ", norm(page.get_text(clip=above))).strip()
    return t[-200:]


def cell(v) -> str:
    return re.sub(r"\s+", " ", norm(v or "")).strip()


def extract() -> None:
    doc = pymupdf.open(PDF)
    units, text_chunks, table_chunks = [], [], []
    for i, page in enumerate(doc, 1):
        chap_num, chap_title = chapter_of(i)
        W = page.rect.width
        tables = page.find_tables().tables
        tboxes = [pymupdf.Rect(t.bbox) for t in tables]
        # ---- tables (detected on the whole spread; may span both printed pages)
        for k, t in enumerate(tables):
            bb = pymupdf.Rect(t.bbox)
            pages = [p for side, p, clip in halves(page, i) if clip.intersects(bb)
                     and (min(bb.x1, clip.x1) - max(bb.x0, clip.x0)) > 20]
            if not pages:  # narrow table: assign by centre
                xc = (bb.x0 + bb.x1) / 2
                pages = [p for side, p, clip in halves(page, i) if clip.x0 <= xc <= clip.x1][:1]
            header = rebuild_header(page, t)
            rows = t.extract()[1:] if header else t.extract()
            rows = [[cell(c) for c in r] for r in rows]
            rows = [r for r in rows if any(r)]
            title = table_title(page, bb)
            head = f"Bảng (trang {', '.join(map(str, pages))}): {title}\nCột: " + " | ".join(header or [])
            lines, part = [], 0
            for r in rows:
                line = " | ".join(c if c else "-" for c in r)
                if lines and len(head) + sum(len(x) + 1 for x in lines) + len(line) > MAX_TABLE:
                    table_chunks.append(_table_chunk(i, k, part, pages, chap_num, chap_title, bb, head, lines, len(rows)))
                    lines, part = [], part + 1
                lines.append(line)
            if lines:
                table_chunks.append(_table_chunk(i, k, part, pages, chap_num, chap_title, bb, head, lines, len(rows)))
        # ---- text per printed page, excluding header band and table areas
        for side, printed, clip in halves(page, i):
            body = pymupdf.Rect(clip.x0, HEADER_H if side != "S" else 0, clip.x1, clip.y1 - FOOTER_H)
            blocks = []
            for b in page.get_text("blocks", clip=body, sort=True):
                rb = pymupdf.Rect(b[:4])
                if b[6] != 0 or any(rb.intersects(tb) and (rb & tb).get_area() > 0.5 * rb.get_area() for tb in tboxes):
                    continue
                txt = re.sub(r"[ \t]+", " ", norm(b[4])).strip()
                if txt:
                    blocks.append(txt)
            units.append({"pdf_page": i, "side": side, "printed_page": printed, "chapter": chap_num,
                          "chapter_title": chap_title, "text_chars": sum(len(b) for b in blocks),
                          "tables": sum(1 for tb in tboxes if (min(tb.x1, clip.x1) - max(tb.x0, clip.x0)) > 20)})
            buf, n = [], 0
            for b in blocks:
                if buf and sum(len(x) + 1 for x in buf) + len(b) > MAX_CHUNK:
                    text_chunks.append(_text_chunk(i, side, printed, n, chap_num, chap_title, buf))
                    buf, n = [], n + 1
                while len(b) > MAX_CHUNK:  # very long block: hard split on sentence/space
                    cut = b.rfind(". ", 0, MAX_CHUNK) + 1 or b.rfind(" ", 0, MAX_CHUNK)
                    text_chunks.append(_text_chunk(i, side, printed, n, chap_num, chap_title, [b[:cut]]))
                    b, n = b[cut:].strip(), n + 1
                buf.append(b)
            if buf:
                text_chunks.append(_text_chunk(i, side, printed, n, chap_num, chap_title, buf))
    DATA.mkdir(parents=True, exist_ok=True)
    for name, data in (("units.json", units), ("chunks_text.json", text_chunks), ("chunks_table.json", table_chunks)):
        (DATA / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"printed pages {len(units)} | text chunks {len(text_chunks)} | table chunks {len(table_chunks)} "
          f"| tables {len({(c['metadata']['pdf_page'], c['metadata']['table_index']) for c in table_chunks})}")
    empty = [u["printed_page"] for u in units if u["text_chars"] < 100 and u["tables"] == 0]
    print("printed pages with <100 text chars and no table:", empty)


def _base(cid: str, text: str, page: int, pdf_page: int, chap: str, title: str, **meta) -> dict:
    return {"id": cid, "text": text, "source_id": SOURCE_ID, "source": SOURCE_URL, "page": page,
            "metadata": {"pdf_page": pdf_page, "chapter": chap, "section": f"chuong_{chap}",
                         "chapter_title": title, "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
                         **meta}}


def _text_chunk(pdf_page, side, printed, n, chap, title, buf):
    return _base(f"{SOURCE_ID}:p{printed:03d}:text:{n:02d}", "\n".join(buf), printed, pdf_page, chap, title,
                 kind="text", side=side)


def _table_chunk(pdf_page, k, part, pages, chap, title, bb, head, lines, nrows):
    text = head + "\n" + "\n".join(lines)
    return _base(f"{SOURCE_ID}:p{pages[0]:03d}:table{k}:{part}", text, pages[0], pdf_page, chap, title,
                 kind="table", table_index=k, part=part, pages=pages, rows=nrows,
                 bbox=[round(x, 1) for x in bb], bbox_unit="pt, toàn trang PDF (spread)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    extract()
