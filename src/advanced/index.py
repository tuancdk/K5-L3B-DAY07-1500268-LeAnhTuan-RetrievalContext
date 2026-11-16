"""Build the multimodal corpus + indexes for the annual report and expose retrievers.

    python -m src.advanced.index build     # merge text/table/visual chunks, embed, save
    python -m src.advanced.index stats

Chunks (starter/data/advanced/chunks_all.json) share the Day 7 schema
(id, text, source_id, source, page, metadata). `page` is the PRINTED page number.
Visual chunks carry kind (bar_chart/diagram/...), bbox in PDF points and a crop path so a
citation identifies the page AND the region.
Dense vectors: text-embedding-3-small (1536 dims), stored as .npy, exact cosine in numpy.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from .extract import DATA, ROOT, SOURCE_ID, SOURCE_URL, _base, chapter_of
from .vision import VISION_DIR

ALL = DATA / "chunks_all.json"
EMB = DATA / "embeddings.npy"
KIND_VI = {"bar_chart": "Biểu đồ cột", "line_chart": "Biểu đồ đường", "pie_chart": "Biểu đồ tròn",
           "combo_chart": "Biểu đồ kết hợp", "diagram": "Sơ đồ", "org_chart": "Sơ đồ tổ chức",
           "infographic": "Infographic", "map": "Bản đồ", "photo": "Ảnh"}


def visual_chunks() -> tuple[list[dict], list[int]]:
    out, errors = [], []
    for f in sorted(VISION_DIR.glob("p*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        if "error" in rec:
            errors.append(rec["printed_page"])
            continue
        printed, pdf_page = rec["printed_page"], rec["pdf_page"]
        chap, title = chapter_of(pdf_page)
        for k, v in enumerate(rec["visuals"]):
            data = "; ".join(f"{d['label']}: {d['value']}" for d in v["data"])
            text = (f"[{KIND_VI[v['kind']]} - trang {printed}] {v['title']}\n{v['description']}"
                    + (f"\nSố liệu: {data}" if data else ""))
            out.append(_base(f"{SOURCE_ID}:p{printed:03d}:visual{k}", text, printed, pdf_page, chap, title,
                             kind=v["kind"], bbox=v.get("bbox_pdf_pt"), bbox_unit="pt, toàn trang PDF (spread)",
                             crop=v.get("crop"), extracted_by=rec["model"]))
    return out, errors


def build() -> None:
    from openai import OpenAI
    from dotenv import load_dotenv
    import os
    load_dotenv(ROOT / ".env")
    text = json.loads((DATA / "chunks_text.json").read_text(encoding="utf-8"))
    table = json.loads((DATA / "chunks_table.json").read_text(encoding="utf-8"))
    visual, errors = visual_chunks()
    chunks = text + table + visual
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids)), "duplicate chunk ids"
    ALL.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=3, timeout=120)
    vecs, tokens = [], 0
    for s in range(0, len(chunks), 128):
        batch = [c["text"][:8000] for c in chunks[s:s + 128]]
        r = client.embeddings.create(model="text-embedding-3-small", input=batch)
        tokens += r.usage.total_tokens
        vecs += [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
    m = np.array(vecs, dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    np.save(EMB, m)
    (DATA / "index_manifest.json").write_text(json.dumps({
        "source_id": SOURCE_ID, "source": SOURCE_URL, "chunks": len(chunks),
        "by_kind": Counter(c["metadata"]["kind"] for c in chunks), "vision_errors": errors,
        "embedding": {"model": "text-embedding-3-small", "dims": m.shape[1], "tokens": tokens,
                      "cost_usd": round(tokens * 0.02 / 1e6, 5)}}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(chunks)} chunks {dict(Counter(c['metadata']['kind'] for c in chunks))}; "
          f"embedding tokens {tokens}; vision errors {errors}")


class DenseLocal:
    """Exact cosine over the saved matrix; same output format as the Day 7 retrievers."""
    name = "dense"

    def __init__(self, chunks: list[dict], matrix: np.ndarray, embedder) -> None:
        self.chunks, self.m, self.embedder = chunks, matrix, embedder
        self._cache: dict[str, np.ndarray] = {}

    def search(self, query, *, filters=None, top_k=3):
        from ..retrieval import _match_filters
        if query not in self._cache:
            v = np.array(self.embedder.embed(query), dtype=np.float32)
            self._cache[query] = v / np.linalg.norm(v)
        s = self.m @ self._cache[query]
        order = np.argsort(-s)
        out = []
        for i in order:
            c = self.chunks[i]
            if _match_filters(c, filters):
                out.append({**c, "score": round(float(s[i]), 6), "rank": len(out) + 1, "retriever": "dense"})
                if len(out) == top_k:
                    break
        return out


def build_retrievers(candidates: int = 20, rrf_k: int = 60, rerank_model: str | None = None):
    from ..day6 import Embedder
    from ..retrieval import BM25, HybridRRF, LLMRerank
    chunks = json.loads(ALL.read_text(encoding="utf-8"))
    dense = DenseLocal(chunks, np.load(EMB), Embedder())
    bm25 = BM25(chunks, bigrams=True)
    hybrid = HybridRRF(dense, bm25, k=rrf_k, candidates=candidates)
    return {"dense": dense, "bm25": bm25, "hybrid": hybrid,
            "hybrid_rerank": LLMRerank(hybrid, model=rerank_model, candidates=candidates)}, chunks


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["build"]:
        build()
    else:
        print((DATA / "index_manifest.json").read_text(encoding="utf-8"))
