"""Connect Day 7 to the Day 6 corpus, embeddings and pgvector store (read-only).

Day 6 facts (see Day 6 starter/results/ingest_report.json):
  * corpus  : mbb-bctc-hn-q3-2026, 59 content pages (scanned PDF -> OCR)
  * embedder: OpenAI text-embedding-3-small, 1536 dims, symmetric (no query prefix)
  * store   : PostgreSQL + pgvector, table `chunks`, exact cosine scan
  * indexes : "A" fixed 500/50 (297 chunks), "B" paragraph max 1000 (194 chunks)

Usage (from repo root, DB started with `docker compose -p day7_retrieval up -d`):
    python -m src.day6 check            # DB + index + embedder sanity check, one real query
    python -m src.day6 export           # write chunks/questions to starter/data/day6/

This module never writes to the database and never falls back to fake vectors.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAY6 = ROOT.parents[1] / "VinUni-Day6" / "K5-L3B-DAY06-LeAnhTuan-2A202603792-DataIngestion"
EXPORT_DIR = ROOT / "starter" / "data" / "day6"

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
PRICE_PER_MILLION_TOKENS = 0.02  # USD, OpenAI pricing for text-embedding-3-small
DEFAULT_INDEX = "B"  # best Day 6 dev strategy (Evidence Hit@3 12/16 vs A 9/16)
FILTERABLE = {"section", "document_id", "page", "report_period", "report_type"}


def load_env() -> None:
    load_dotenv(ROOT / ".env")


def day6_dir() -> Path:
    return Path(os.getenv("DAY6_DIR") or DEFAULT_DAY6)


def normalize(text: str) -> str:
    """Day 6 hit normalization: NFC, collapse whitespace, casefold."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


class Embedder:
    """Query embedder compatible with the Day 6 index (same model, same dims)."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("EMBEDDING_MODEL") or EMBEDDING_MODEL
        if self.model != EMBEDDING_MODEL:
            raise ValueError(f"Day 6 index was built with {EMBEDDING_MODEL}; got {self.model}")
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY missing in .env")
        self.client = OpenAI(api_key=key, max_retries=3, timeout=60)
        self.total_tokens = 0
        self.api_calls = 0

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("cannot embed empty text")
        resp = self.client.embeddings.create(model=self.model, input=[text])
        self.api_calls += 1
        self.total_tokens += resp.usage.total_tokens
        vec = resp.data[0].embedding
        if len(vec) != EMBEDDING_DIMS:
            raise RuntimeError(f"expected {EMBEDDING_DIMS} dims, got {len(vec)}")
        return vec

    def usage(self) -> dict[str, Any]:
        return {"model": self.model, "dimensions": EMBEDDING_DIMS, "api_calls": self.api_calls,
                "total_tokens": self.total_tokens,
                "estimated_cost_usd": round(self.total_tokens / 1e6 * PRICE_PER_MILLION_TOKENS, 6)}


def _row_to_chunk(r: tuple) -> dict[str, Any]:
    chunk_id, document_id, source, page, section, text, metadata = r[:7]
    metadata = metadata if isinstance(metadata, dict) else json.loads(metadata)
    return {"id": chunk_id, "text": text, "source_id": document_id, "source": source,
            "page": page, "metadata": {**metadata, "section": section}}


class Day6Store:
    """Read-only access to the Day 6 `chunks` table."""

    def __init__(self, database_url: str | None = None, index: str = DEFAULT_INDEX) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise RuntimeError("DATABASE_URL missing in .env")
        self.index = index

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, connect_timeout=5)

    def info(self) -> dict[str, Any]:
        with self.connect() as conn:
            pg = conn.execute("SHOW server_version").fetchone()[0]
            ext = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
            dims = conn.execute("SELECT atttypmod FROM pg_attribute WHERE attrelid='chunks'::regclass "
                                "AND attname='embedding'").fetchone()[0]
            rows = conn.execute("SELECT strategy, count(*), count(DISTINCT page), "
                                "count(DISTINCT document_id) FROM chunks GROUP BY strategy "
                                "ORDER BY strategy").fetchall()
        return {"postgres": pg, "pgvector": ext[0] if ext else None, "embedding_dims": dims,
                "indexes": {s: {"chunks": n, "pages": p, "documents": d} for s, n, p, d in rows}}

    def all_chunks(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT chunk_id, document_id, source, page, section, text, metadata "
                                "FROM chunks WHERE strategy = %s ORDER BY page, chunk_id",
                                (self.index,)).fetchall()
        return [_row_to_chunk(r) for r in rows]

    def dense_search(self, query_vector: list[float], top_k: int = 3,
                     filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Exact cosine search, filter applied in SQL before ranking (same as Day 6)."""
        if len(query_vector) != EMBEDDING_DIMS:
            raise ValueError(f"query vector must have {EMBEDDING_DIMS} dims")
        where, params = ["strategy = %s"], [self.index]
        for col, val in (filters or {}).items():
            if col not in FILTERABLE:
                raise ValueError(f"filter on '{col}' not allowed; use {sorted(FILTERABLE)}")
            if isinstance(val, (list, tuple, set)):
                where.append(f"{col} = ANY(%s)")
                params.append(list(val))
            else:
                where.append(f"{col} = %s")
                params.append(val)
        vec = "[" + ",".join(f"{x:.8f}" for x in query_vector) + "]"
        sql = ("SELECT chunk_id, document_id, source, page, section, text, metadata, "
               "1 - (embedding <=> %s::vector) AS score FROM chunks "
               f"WHERE {' AND '.join(where)} ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s")
        with self.connect() as conn:
            rows = conn.execute(sql, [vec, *params, vec, top_k]).fetchall()
        out = []
        for rank, r in enumerate(rows, 1):
            chunk = _row_to_chunk(r)
            chunk.update({"score": round(float(r[7]), 6), "rank": rank, "retriever": "dense"})
            out.append(chunk)
        return out


class DenseRetriever:
    """Day 7 `Retriever` protocol over the Day 6 vector store."""

    def __init__(self, store: Day6Store | None = None, embedder: Embedder | None = None) -> None:
        self.store = store or Day6Store()
        self.embedder = embedder or Embedder()

    def search(self, query: str, *, filters: dict[str, Any] | None = None,
               top_k: int = 3) -> list[dict[str, Any]]:
        return self.store.dense_search(self.embedder.embed(query), top_k=top_k, filters=filters)


def convert_questions(day6_questions: list[dict], chunks: list[dict]) -> tuple[list[dict], list[str]]:
    """Day 6 benchmark -> Day 7 schema; one gold entry per gold page (alternatives).

    Evidence is kept verbatim from Day 6. If it is only found after Day 6 normalization
    (whitespace/case), the exact chunk substring is used so that the starter's verbatim
    `hit()` agrees with Day 6's definition; such cases are reported in `notes`.
    """
    out, notes = [], []
    for q in day6_questions:
        if q.get("answerable") is False:
            out.append({k: q[k] for k in ("id", "split", "question") } |
                       {"answerable": False, "expected_behavior": "search_and_abstain",
                        "absence_reason": q.get("absence_reason", "")})
            continue
        gold = []
        for page in q["gold_pages"]:
            evidence = q["evidence_quote"]
            on_page = [c for c in chunks if c["source_id"] == q["gold_source_id"] and c["page"] == page]
            if not any(evidence in c["text"] for c in on_page):
                exact = _exact_span(evidence, on_page)
                if exact:
                    notes.append(f"{q['id']} p{page}: evidence khớp sau chuẩn hóa -> dùng chuỗi gốc trong chunk")
                    evidence = exact
                else:
                    notes.append(f"{q['id']} p{page}: evidence KHÔNG nằm trọn trong chunk nào của index")
                    continue
            gold.append({"source_id": q["gold_source_id"], "page": page, "evidence": evidence})
        item = {"id": q["id"], "split": q["split"], "question": q["question"],
                "expected_answer": q["expected_answer"], "gold": gold, "type": q.get("type")}
        if q.get("filter"):
            item["filter"] = q["filter"]
        out.append(item)
    return out, notes


def _exact_span(evidence: str, chunks: list[dict]) -> str | None:
    """Find the verbatim substring of a chunk that normalizes to `evidence`."""
    target = normalize(evidence)
    words = target.split(" ")
    pattern = r"\s+".join(re.escape(w) for w in words)
    for c in chunks:
        m = re.search(pattern, unicodedata.normalize("NFC", c["text"]), flags=re.IGNORECASE)
        if m:
            return m.group(0)
    return None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_check(args: argparse.Namespace) -> None:
    store = Day6Store(index=args.index)
    info = store.info()
    print(json.dumps(info, ensure_ascii=False, indent=2))
    if info["embedding_dims"] != EMBEDDING_DIMS:
        raise SystemExit(f"index dims {info['embedding_dims']} != {EMBEDDING_DIMS}")
    retriever = DenseRetriever(store)
    t0 = time.perf_counter()
    results = retriever.search(args.query, top_k=3)
    ms = (time.perf_counter() - t0) * 1000
    print(f"\nQuery: {args.query}  (index {args.index}, {ms:.0f} ms)")
    for r in results:
        print(f"  #{r['rank']} {r['score']:.4f} {r['id']} p{r['page']}: {r['text'][:110]!r}")
    print("embedding usage:", retriever.embedder.usage())


def cmd_export(args: argparse.Namespace) -> None:
    d6 = day6_dir()
    bench_path = d6 / "benchmark" / "questions.json"
    bench = json.loads(bench_path.read_text(encoding="utf-8"))
    store = Day6Store(index=args.index)
    chunks = store.all_chunks()
    questions, notes = convert_questions(bench["questions"], chunks)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    (out / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ingest = json.loads((d6 / "starter" / "results" / "ingest_report.json").read_text(encoding="utf-8"))
    manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "day6_dir": str(d6), "index": args.index,
        "chunking": {k: v for k, v in ingest["indexes"][args.index].items() if k in ("chunking", "size", "overlap", "max_size", "min_size")},
        "store": store.info(), "embedding": ingest["embedding"],
        "day6_benchmark": {"path": str(bench_path), "sha256": sha256(bench_path),
                           "version": bench["meta"].get("version"), "status": bench["meta"].get("status")},
        "counts": {"chunks": len(chunks), "pages": len({c["page"] for c in chunks}),
                   "questions": {s: sum(q["split"] == s for q in questions) for s in ("dev", "test")}},
        "conversion_notes": notes,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], ensure_ascii=False))
    print("\n".join(notes) or "Mọi evidence nằm nguyên văn trong chunk.")
    print(f"-> {out.relative_to(ROOT)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    parser = argparse.ArgumentParser(description="Kết nối dữ liệu Day 6")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--index", default=DEFAULT_INDEX, choices=["A", "B"])
    p.add_argument("--query", default="Vốn điều lệ của Ngân hàng tại ngày 30 tháng 9 năm 2026 là bao nhiêu?")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("export")
    p.add_argument("--index", default=DEFAULT_INDEX, choices=["A", "B"])
    p.add_argument("--output", type=Path, default=EXPORT_DIR)
    p.set_defaults(fn=cmd_export)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
